from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from cosmic_mail.api.auth import AuthContext, authorize_draft, authorize_mailbox, authorize_thread
from cosmic_mail.api.deps import get_auth_context, get_inbound_client, get_outbound_sender, get_session, get_settings
from cosmic_mail.core.config import Settings
from cosmic_mail.domain.repositories import AttachmentRepository
from cosmic_mail.domain.schemas import AttachmentRead, MailDraftCreate, MailDraftRead, MailDraftSendResult, MailMessageRead, MailThreadRead
from cosmic_mail.services.conversations import (
    ApprovalNotFoundError,
    ConversationService,
    DraftNotFoundError,
    DraftStateError,
    DraftThreadMismatchError,
    MailTransportError,
    MailboxCredentialsError,
    MailboxNotFoundError,
    OutboundFilterBlockedError,
    ThreadNotFoundError,
)
from cosmic_mail.services.inbound import InboundMailboxClient
from cosmic_mail.services.outbound import OutboundMailSender

router = APIRouter(prefix="/drafts", tags=["drafts"])


def _build_message_read(message, session) -> MailMessageRead:
    attachments = [
        AttachmentRead.model_validate(a)
        for a in AttachmentRepository(session).list_for_message(message.id)
    ]
    data = MailMessageRead.model_validate(message)
    data.attachments = attachments
    return data


@router.post("", response_model=MailDraftRead, status_code=status.HTTP_201_CREATED)
def create_draft(
    payload: MailDraftCreate,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    outbound_sender: Annotated[OutboundMailSender, Depends(get_outbound_sender)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> MailDraftRead:
    authorize_mailbox(session, auth, payload.mailbox_id)
    if payload.thread_id:
        authorize_thread(session, auth, payload.thread_id)
    service = ConversationService(session, settings, outbound_sender, inbound_client)
    try:
        draft = service.create_draft(payload)
    except MailboxNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ThreadNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return MailDraftRead.model_validate(draft)


@router.get("", response_model=list[MailDraftRead])
def list_drafts(
    mailbox_id: Annotated[str, Query(min_length=1)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    outbound_sender: Annotated[OutboundMailSender, Depends(get_outbound_sender)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[MailDraftRead]:
    authorize_mailbox(session, auth, mailbox_id)
    service = ConversationService(session, settings, outbound_sender, inbound_client)
    try:
        drafts = service.list_drafts(mailbox_id)
    except MailboxNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [MailDraftRead.model_validate(draft) for draft in drafts]


@router.post("/{draft_id}/send", response_model=MailDraftSendResult)
def send_draft(
    draft_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    outbound_sender: Annotated[OutboundMailSender, Depends(get_outbound_sender)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> MailDraftSendResult:
    authorize_draft(session, auth, draft_id)
    service = ConversationService(session, settings, outbound_sender, inbound_client)
    try:
        draft, thread, message, approval = service.send_draft(draft_id)
    except (DraftNotFoundError, ThreadNotFoundError, MailboxNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DraftThreadMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DraftStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (MailTransportError, MailboxCredentialsError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except OutboundFilterBlockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"blocked": [{"email": v.email, "reason": v.reason, "scope": v.scope} for v in exc.args[0]]},
        ) from exc

    if approval is not None:
        return MailDraftSendResult(
            draft=MailDraftRead.model_validate(draft),
            queued_for_approval=True,
            approval_id=approval.id,
        )
    return MailDraftSendResult(
        draft=MailDraftRead.model_validate(draft),
        thread=MailThreadRead.model_validate(thread),
        message=_build_message_read(message, session),
    )
