from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from cosmic_mail.api.auth import AuthContext, authorize_domain, authorize_mailbox
from cosmic_mail.api.deps import get_auth_context, get_inbound_client, get_mail_engine, get_session, get_settings
from cosmic_mail.core.config import Settings
from cosmic_mail.domain.schemas import (
    MailboxCreate,
    MailboxCreateResult,
    MailboxRead,
    MailboxSyncPolicyRead,
    MailboxSyncPolicyUpdate,
    MailboxSyncResult,
)
from cosmic_mail.services.conversations import MailboxCredentialsError, MailboxNotFoundError
from cosmic_mail.services.inbound import InboundMailboxClient, InboxSyncError
from cosmic_mail.services.mail_engine import MailEngine
from cosmic_mail.services.mailboxes import (
    MailboxConflictError,
    MailboxDomainInactiveError,
    MailboxDomainNotFoundError,
    MailboxService,
)
from cosmic_mail.services.sync_manager import MailboxSyncService

router = APIRouter(prefix="/mailboxes", tags=["mailboxes"])


@router.post("", response_model=MailboxCreateResult, status_code=status.HTTP_201_CREATED)
def create_mailbox(
    payload: MailboxCreate,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    mail_engine: Annotated[MailEngine, Depends(get_mail_engine)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> MailboxCreateResult:
    authorize_domain(session, auth, payload.domain_id)
    service = MailboxService(session, settings, mail_engine)
    try:
        mailbox, issued_password = service.create(payload)
    except MailboxDomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MailboxDomainInactiveError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MailboxConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return MailboxCreateResult.model_validate(mailbox).model_copy(update={"issued_password": issued_password})


@router.get("", response_model=list[MailboxRead])
def list_mailboxes(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    mail_engine: Annotated[MailEngine, Depends(get_mail_engine)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[MailboxRead]:
    service = MailboxService(session, settings, mail_engine)
    mailboxes = service.list()
    if not auth.is_admin:
        mailboxes = [mailbox for mailbox in mailboxes if mailbox.organization_id == auth.organization_id]
    return [MailboxRead.model_validate(mailbox) for mailbox in mailboxes]


@router.get("/{mailbox_id}/sync-policy", response_model=MailboxSyncPolicyRead)
def get_mailbox_sync_policy(
    mailbox_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> MailboxSyncPolicyRead:
    mailbox = authorize_mailbox(session, auth, mailbox_id)
    service = MailboxSyncService(session, settings, inbound_client)
    mailbox = service.get_policy(mailbox.id)
    return MailboxSyncPolicyRead(
        mailbox_id=mailbox.id,
        enabled=mailbox.inbound_sync_enabled,
        last_synced_at=mailbox.last_synced_at,
        last_sync_error=mailbox.last_sync_error,
    )


@router.patch("/{mailbox_id}/sync-policy", response_model=MailboxSyncPolicyRead)
def update_mailbox_sync_policy(
    mailbox_id: str,
    payload: MailboxSyncPolicyUpdate,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> MailboxSyncPolicyRead:
    mailbox = authorize_mailbox(session, auth, mailbox_id)
    service = MailboxSyncService(session, settings, inbound_client)
    mailbox = service.update_policy(mailbox.id, enabled=payload.enabled)
    return MailboxSyncPolicyRead(
        mailbox_id=mailbox.id,
        enabled=mailbox.inbound_sync_enabled,
        last_synced_at=mailbox.last_synced_at,
        last_sync_error=mailbox.last_sync_error,
    )


@router.post("/{mailbox_id}/sync-inbox", response_model=MailboxSyncResult)
def sync_mailbox_inbox(
    mailbox_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> MailboxSyncResult:
    authorize_mailbox(session, auth, mailbox_id)
    service = MailboxSyncService(session, settings, inbound_client)
    try:
        return service.sync_mailbox(mailbox_id)
    except MailboxNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (MailboxCredentialsError, InboxSyncError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
