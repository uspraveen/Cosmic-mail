from __future__ import annotations

import re
import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cosmic_mail.core.config import Settings
from cosmic_mail.core.security import SecretBox
from cosmic_mail.domain.models import Domain, DomainStatus
from cosmic_mail.domain.repositories import DomainRepository, OrganizationRepository
from cosmic_mail.domain.schemas import DomainCreate, DomainDeliverabilityUpdate, DomainVerificationRead
from cosmic_mail.domain.validation import normalize_domain_name
from cosmic_mail.services.dkim import generate_dkim_key_pair
from cosmic_mail.services.dns import DNSVerifier, build_dns_records, verify_dns_records
from cosmic_mail.services.mail_engine import MailEngine


class DomainConflictError(ValueError):
    pass


class DomainNotFoundError(ValueError):
    pass


class OrganizationNotFoundError(ValueError):
    pass


class DomainDeliverabilityError(ValueError):
    pass


class DomainService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        mail_engine: MailEngine,
        dns_verifier: DNSVerifier,
    ) -> None:
        self._session = session
        self._settings = settings
        self._mail_engine = mail_engine
        self._dns_verifier = dns_verifier
        self._domains = DomainRepository(session)
        self._organizations = OrganizationRepository(session)
        self._secret_box = SecretBox(settings.secret_key)

    def create(self, payload: DomainCreate) -> Domain:
        organization = self._organizations.get(payload.organization_id)
        if organization is None:
            raise OrganizationNotFoundError("organization not found")

        key_pair = generate_dkim_key_pair()
        domain_name = normalize_domain_name(payload.domain)
        dmarc_parts = [
            "v=DMARC1",
            f"p={self._settings.dmarc_policy}",
            f"sp={self._settings.dmarc_subdomain_policy}",
            "adkim=r",
            "aspf=r",
            "pct=100",
        ]
        if self._settings.dmarc_rua:
            dmarc_parts.append(f"rua=mailto:{self._settings.dmarc_rua}")

        domain = Domain(
            organization_id=organization.id,
            name=domain_name,
            status=DomainStatus.pending_dns.value,
            mx_target=self._settings.public_mail_hostname,
            mx_priority=self._settings.default_mx_priority,
            spf_value="v=spf1 mx include:amazonses.com -all",
            dmarc_value="; ".join(dmarc_parts),
            dkim_selector=self._settings.default_dkim_selector,
            dkim_public_key=key_pair.public_key,
            dkim_private_key_ciphertext=self._secret_box.encrypt_text(key_pair.private_key_pem),
        )
        try:
            self._domains.add(domain)
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise DomainConflictError("domain already exists") from exc
        self._session.refresh(domain)
        return domain

    def get(self, domain_id: str) -> Domain:
        domain = self._domains.get(domain_id)
        if domain is None:
            raise DomainNotFoundError("domain not found")
        return domain

    def list(self) -> list[Domain]:
        return self._domains.list()

    def verify_dns(self, domain_id: str) -> DomainVerificationRead:
        domain = self.get(domain_id)

        records = build_dns_records(domain, self._settings)
        checks = verify_dns_records(records, self._dns_verifier)
        all_records_present = all(check.matched for check in checks)

        if all_records_present and not domain.james_domain_created:
            self._mail_engine.ensure_domain(domain.name)
            domain.james_domain_created = True

        if all_records_present:
            domain.status = DomainStatus.active.value

        self._session.add(domain)
        self._session.commit()
        self._session.refresh(domain)

        return DomainVerificationRead(
            domain_id=domain.id,
            status=DomainStatus(domain.status),
            all_records_present=all_records_present,
            james_domain_created=domain.james_domain_created,
            checks=checks,
        )

    def update_deliverability(
        self,
        domain_id: str,
        payload: DomainDeliverabilityUpdate,
    ) -> Domain:
        domain = self.get(domain_id)
        fields_set = payload.model_fields_set
        changed = False

        if "spf_value" in fields_set:
            if payload.spf_value is None:
                raise DomainDeliverabilityError("spf_value cannot be null")
            normalized_spf_value = _normalize_spf_value(payload.spf_value)
            if normalized_spf_value != domain.spf_value:
                domain.spf_value = normalized_spf_value
                changed = True

        dmarc_policy, dmarc_subdomain_policy, rua = _parse_dmarc_value(
            domain.dmarc_value,
            self._settings,
        )
        if "dmarc_policy" in fields_set:
            if payload.dmarc_policy is None:
                raise DomainDeliverabilityError("dmarc_policy cannot be null")
            dmarc_policy = payload.dmarc_policy
        if "dmarc_subdomain_policy" in fields_set:
            if payload.dmarc_subdomain_policy is None:
                raise DomainDeliverabilityError("dmarc_subdomain_policy cannot be null")
            dmarc_subdomain_policy = payload.dmarc_subdomain_policy
        if "dmarc_aggregate_report_email" in fields_set:
            rua_value = (payload.dmarc_aggregate_report_email or "").strip().lower() or None
            if rua_value and "@" not in rua_value:
                raise DomainDeliverabilityError("dmarc_aggregate_report_email must be an email address")
            rua = rua_value

        updated_dmarc_value = _build_dmarc_value(
            dmarc_policy=dmarc_policy,
            dmarc_subdomain_policy=dmarc_subdomain_policy,
            rua=rua,
        )
        if updated_dmarc_value != domain.dmarc_value:
            domain.dmarc_value = updated_dmarc_value
            changed = True

        if changed:
            domain.status = DomainStatus.pending_dns.value
            self._session.add(domain)
            self._session.commit()
            self._session.refresh(domain)
        return domain

    def rotate_dkim(
        self,
        domain_id: str,
        *,
        selector: str | None,
    ) -> Domain:
        domain = self.get(domain_id)
        key_pair = generate_dkim_key_pair()
        domain.dkim_selector = _normalize_selector(selector or _default_rotated_selector(self._settings.default_dkim_selector))
        domain.dkim_public_key = key_pair.public_key
        domain.dkim_private_key_ciphertext = self._secret_box.encrypt_text(key_pair.private_key_pem)
        domain.status = DomainStatus.pending_dns.value
        self._session.add(domain)
        self._session.commit()
        self._session.refresh(domain)
        return domain


SELECTOR_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62})$")


def _normalize_spf_value(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise DomainDeliverabilityError("spf_value cannot be empty")
    if not normalized.lower().startswith("v=spf1"):
        raise DomainDeliverabilityError("spf_value must start with 'v=spf1'")
    return normalized


def _build_dmarc_value(
    *,
    dmarc_policy: str,
    dmarc_subdomain_policy: str,
    rua: str | None,
) -> str:
    parts = [
        "v=DMARC1",
        f"p={dmarc_policy}",
        f"sp={dmarc_subdomain_policy}",
        "adkim=r",
        "aspf=r",
        "pct=100",
    ]
    if rua:
        parts.append(f"rua=mailto:{rua}")
    return "; ".join(parts)


def _parse_dmarc_value(value: str, settings: Settings) -> tuple[str, str, str | None]:
    parts: dict[str, str] = {}
    for part in value.split(";"):
        item = part.strip()
        if "=" not in item:
            continue
        key, raw_value = item.split("=", maxsplit=1)
        parts[key.strip().lower()] = raw_value.strip()
    rua = parts.get("rua")
    if rua and rua.lower().startswith("mailto:"):
        rua = rua[7:]
    return (
        parts.get("p", settings.dmarc_policy),
        parts.get("sp", settings.dmarc_subdomain_policy),
        rua or None,
    )


def _normalize_selector(value: str) -> str:
    normalized = value.strip().lower()
    if not SELECTOR_RE.match(normalized):
        raise DomainDeliverabilityError("invalid dkim selector")
    return normalized


def _default_rotated_selector(prefix: str) -> str:
    base = _normalize_selector(prefix)
    return f"{base[:32]}-{secrets.token_hex(4)}"
