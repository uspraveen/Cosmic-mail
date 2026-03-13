from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from cosmic_mail.api.auth import AuthContext, authorize_domain, authorize_organization_access
from cosmic_mail.api.deps import get_auth_context, get_dns_verifier, get_mail_engine, get_session, get_settings
from cosmic_mail.core.config import Settings
from cosmic_mail.domain.models import Domain
from cosmic_mail.domain.schemas import (
    DomainConnectionProfileRead,
    DomainCreate,
    DomainDeliverabilityRead,
    DomainDeliverabilityUpdate,
    DomainDkimRotate,
    DomainRead,
    DomainVerificationRead,
    MailServiceEndpointRead,
)
from cosmic_mail.services.dns import DNSVerifier, build_dns_records
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
) -> list[DomainRead]:
    service = DomainService(session, settings, mail_engine, dns_verifier)
    domains = service.list()
    if not auth.is_admin:
        domains = [domain for domain in domains if domain.organization_id == auth.organization_id]
    return [_build_domain_read(domain, settings) for domain in domains]


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
