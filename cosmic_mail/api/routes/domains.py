from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from cosmic_mail.api.auth import AuthContext, authorize_domain, authorize_organization_access
from cosmic_mail.api.deps import get_auth_context, get_dns_verifier, get_mail_engine, get_session, get_settings
from cosmic_mail.core.config import Settings
from cosmic_mail.domain.models import Domain
from cosmic_mail.domain.schemas import (
    BlacklistCheckRead,
    DeliverabilityCheckRead,
    DomainConnectionProfileRead,
    DomainCreate,
    DomainDeliverabilityRead,
    DomainDeliverabilityUpdate,
    DomainDkimRotate,
    DomainRead,
    DomainVerificationRead,
    MailServiceEndpointRead,
)
from cosmic_mail.services.dns import (
    DNSVerifier,
    ExternalDnsVerifier,
    build_dns_records,
    check_ip_blacklists,
    resolve_mx_ip,
    verify_dns_records,
)
from cosmic_mail.services.domains import (
    DomainConflictError,
    DomainDeliverabilityError,
    DomainNotFoundError,
    DomainService,
    OrganizationNotFoundError,
)
from cosmic_mail.services.mail_engine import MailEngine

router = APIRouter(prefix="/domains", tags=["domains"])


@router.post("", response_model=DomainRead, status_code=status.HTTP_201_CREATED)
def create_domain(
    payload: DomainCreate,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    mail_engine: Annotated[MailEngine, Depends(get_mail_engine)],
    dns_verifier: Annotated[DNSVerifier, Depends(get_dns_verifier)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> DomainRead:
    authorize_organization_access(auth, payload.organization_id)
    service = DomainService(session, settings, mail_engine, dns_verifier)
    try:
        domain = service.create(payload)
    except OrganizationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DomainConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return _build_domain_read(domain, settings)


@router.get("", response_model=list[DomainRead])
def list_domains(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    mail_engine: Annotated[MailEngine, Depends(get_mail_engine)],
    dns_verifier: Annotated[DNSVerifier, Depends(get_dns_verifier)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[DomainRead]:
    service = DomainService(session, settings, mail_engine, dns_verifier)
    domains = service.list()
    if not auth.is_admin:
        domains = [domain for domain in domains if domain.organization_id == auth.organization_id]
    start = (page - 1) * per_page
    return [_build_domain_read(domain, settings) for domain in domains[start : start + per_page]]


@router.post("/{domain_id}/verify-dns", response_model=DomainVerificationRead)
def verify_domain_dns(
    domain_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    mail_engine: Annotated[MailEngine, Depends(get_mail_engine)],
    dns_verifier: Annotated[DNSVerifier, Depends(get_dns_verifier)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> DomainVerificationRead:
    authorize_domain(session, auth, domain_id)
    service = DomainService(session, settings, mail_engine, dns_verifier)
    try:
        return service.verify_dns(domain_id)
    except DomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{domain_id}/deliverability", response_model=DomainDeliverabilityRead)
def get_domain_deliverability(
    domain_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    mail_engine: Annotated[MailEngine, Depends(get_mail_engine)],
    dns_verifier: Annotated[DNSVerifier, Depends(get_dns_verifier)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> DomainDeliverabilityRead:
    authorize_domain(session, auth, domain_id)
    service = DomainService(session, settings, mail_engine, dns_verifier)
    try:
        domain = service.get(domain_id)
    except DomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _build_domain_deliverability(domain, settings)


@router.patch("/{domain_id}/deliverability", response_model=DomainDeliverabilityRead)
def update_domain_deliverability(
    domain_id: str,
    payload: DomainDeliverabilityUpdate,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    mail_engine: Annotated[MailEngine, Depends(get_mail_engine)],
    dns_verifier: Annotated[DNSVerifier, Depends(get_dns_verifier)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> DomainDeliverabilityRead:
    authorize_domain(session, auth, domain_id)
    service = DomainService(session, settings, mail_engine, dns_verifier)
    try:
        domain = service.update_deliverability(domain_id, payload)
    except DomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DomainDeliverabilityError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _build_domain_deliverability(domain, settings)


@router.post("/{domain_id}/rotate-dkim", response_model=DomainDeliverabilityRead)
def rotate_domain_dkim(
    domain_id: str,
    payload: DomainDkimRotate,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    mail_engine: Annotated[MailEngine, Depends(get_mail_engine)],
    dns_verifier: Annotated[DNSVerifier, Depends(get_dns_verifier)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> DomainDeliverabilityRead:
    authorize_domain(session, auth, domain_id)
    service = DomainService(session, settings, mail_engine, dns_verifier)
    try:
        domain = service.rotate_dkim(domain_id, selector=payload.selector)
    except DomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DomainDeliverabilityError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _build_domain_deliverability(domain, settings)


@router.get("/{domain_id}/deliverability/check", response_model=DeliverabilityCheckRead)
def check_domain_deliverability(
    domain_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    mail_engine: Annotated[MailEngine, Depends(get_mail_engine)],
    dns_verifier: Annotated[DNSVerifier, Depends(get_dns_verifier)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> DeliverabilityCheckRead:
    """Run an external deliverability check for a domain.

    Resolves all DNS records via a public resolver (8.8.8.8), resolves the MX
    hostname to an IP, and checks that IP against common DNSBL blacklists.
    """
    authorize_domain(session, auth, domain_id)
    service = DomainService(session, settings, mail_engine, dns_verifier)
    try:
        domain = service.get(domain_id)
    except DomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    ext_verifier = ExternalDnsVerifier()
    records = build_dns_records(domain, settings)
    dns_checks = verify_dns_records(records, ext_verifier)
    all_dns_ok = all(check.matched for check in dns_checks)

    mx_ip = resolve_mx_ip(domain.mx_target)
    blacklists: list[BlacklistCheckRead] = []
    if mx_ip:
        for zone, listed in check_ip_blacklists(mx_ip):
            blacklists.append(BlacklistCheckRead(zone=zone, listed=listed))

    return DeliverabilityCheckRead(
        domain_id=domain.id,
        mx_hostname=domain.mx_target,
        mx_ip=mx_ip,
        dns_checks=dns_checks,
        all_dns_ok=all_dns_ok,
        blacklists=blacklists,
        any_blacklisted=any(b.listed for b in blacklists),
    )


def _build_domain_read(domain: Domain, settings: Settings) -> DomainRead:
    return DomainRead(
        id=domain.id,
        organization_id=domain.organization_id,
        name=domain.name,
        status=domain.status,
        james_domain_created=domain.james_domain_created,
        created_at=domain.created_at,
        updated_at=domain.updated_at,
        dns_records=build_dns_records(domain, settings),
    )


def _build_domain_deliverability(domain: Domain, settings: Settings) -> DomainDeliverabilityRead:
    public_host = settings.public_mail_hostname
    submission_host = settings.public_submission_hostname or public_host
    imap_host = settings.public_imap_hostname or public_host
    return DomainDeliverabilityRead(
        domain_id=domain.id,
        status=domain.status,
        james_domain_created=domain.james_domain_created,
        mx_target=domain.mx_target,
        mx_priority=domain.mx_priority,
        spf_value=domain.spf_value,
        dmarc_value=domain.dmarc_value,
        dkim_selector=domain.dkim_selector,
        dkim_public_key=domain.dkim_public_key,
        dns_records=build_dns_records(domain, settings),
        connection_profile=DomainConnectionProfileRead(
            submission=MailServiceEndpointRead(
                host=submission_host,
                port=settings.public_submission_port,
                security="starttls" if settings.public_submission_use_starttls else "none",
                auth_required=True,
            ),
            imap=MailServiceEndpointRead(
                host=imap_host,
                port=settings.public_imap_port,
                security="ssl" if settings.public_imap_use_ssl else "none",
                auth_required=True,
            ),
        ),
    )
