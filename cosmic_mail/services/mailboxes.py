from __future__ import annotations

import secrets

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cosmic_mail.core.config import Settings
from cosmic_mail.core.security import SecretBox
from cosmic_mail.domain.models import DomainStatus, MailboxIdentity, MailboxStatus
from cosmic_mail.domain.repositories import DomainRepository, MailboxRepository
from cosmic_mail.domain.schemas import MailboxCreate
from cosmic_mail.domain.validation import normalize_local_part
from cosmic_mail.services.mail_engine import MailEngine


class MailboxConflictError(ValueError):
    pass


class MailboxDomainInactiveError(ValueError):
    pass


class MailboxDomainNotFoundError(ValueError):
    pass


class MailboxService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        mail_engine: MailEngine,
    ) -> None:
        self._session = session
        self._settings = settings
        self._mail_engine = mail_engine
        self._domains = DomainRepository(session)
        self._mailboxes = MailboxRepository(session)
        self._secret_box = SecretBox(settings.secret_key)

    def create(self, payload: MailboxCreate) -> tuple[MailboxIdentity, str | None]:
        domain = self._domains.get(payload.domain_id)
        if domain is None:
            raise MailboxDomainNotFoundError("domain not found")
        if domain.status != DomainStatus.active.value:
            raise MailboxDomainInactiveError("domain is not active")

        local_part = normalize_local_part(payload.local_part)
        address = f"{local_part}@{domain.name}"
        issued_password = payload.password or secrets.token_urlsafe(24)
        quota_mb = payload.quota_mb or self._settings.default_mailbox_quota_mb
        quota_messages = payload.quota_messages or self._settings.default_mailbox_quota_messages

        self._mail_engine.ensure_user(address, issued_password)
        self._mail_engine.configure_mailbox(
            address,
            quota_mb=quota_mb,
            quota_messages=quota_messages,
        )

        mailbox = MailboxIdentity(
            organization_id=domain.organization_id,
            domain_id=domain.id,
            local_part=local_part,
            address=address,
            display_name=payload.display_name.strip() if payload.display_name else None,
            status=MailboxStatus.active.value,
            james_user_created=True,
            password_ciphertext=self._secret_box.encrypt_text(issued_password),
            quota_mb=quota_mb,
            quota_messages=quota_messages,
            inbound_sync_enabled=True,
        )
        try:
            self._mailboxes.add(mailbox)
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise MailboxConflictError("mailbox already exists") from exc
        self._session.refresh(mailbox)
        return mailbox, issued_password

    def list(self) -> list[MailboxIdentity]:
        return self._mailboxes.list()
