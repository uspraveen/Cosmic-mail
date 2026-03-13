from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from cosmic_mail.api.auth import AuthContext, authorize_mailbox, authorize_thread
from cosmic_mail.api.deps import get_auth_context, get_inbound_client, get_outbound_sender, get_session, get_settings
from cosmic_mail.core.config import Settings
from cosmic_mail.domain.repositories import AttachmentRepository
from cosmic_mail.domain.schemas import AttachmentRead, MailDraftRead, MailDraftSendResult, MailMessageRead, MailThreadRead, ThreadReplyCreate
from cosmic_mail.services.conversations import (
    ConversationService,
    DraftStateError,
    MailboxNotFoundError,
    MailTransportError,
    ThreadNotFoundError,
)
from cosmic_mail.services.inbound import InboundMailboxClient
from cosmic_mail.services.outbound import OutboundMailSender

router = APIRouter(prefix="/threads", tags=["threads"])


def _build_message_read(message, session: Session) -> MailMessageRead:
    attachments = [
        AttachmentRead.model_validate(a)
        for a in AttachmentRepository(session).list_for_message(message.id)
    ]
    data = MailMessageRead.model_validate(message)
    data.attachments = attachments
    return data


@router.get("", response_model=list[MailThreadRead])
def list_threads(
    mailbox_id: Annotated[str, Query(min_length=1)],
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    outbound_sender: Annotated[OutboundMailSender, Depends(get_outbound_sender)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[MailThreadRead]:
    authorize_mailbox(session, auth, mailbox_id)
    service = ConversationService(session, settings, outbound_sender, inbound_client)
    try:
        threads = service.list_threads(mailbox_id)
    except MailboxNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [MailThreadRead.model_validate(thread) for thread in threads]


@router.get("/{thread_id}/messages", response_model=list[MailMessageRead])
def list_thread_messages(
    thread_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    outbound_sender: Annotated[OutboundMailSender, Depends(get_outbound_sender)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[MailMessageRead]:
    authorize_thread(session, auth, thread_id)
    service = ConversationService(session, settings, outbound_sender, inbound_client)
    try:
        messages = service.list_thread_messages(thread_id)
    except ThreadNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [_build_message_read(message, session) for message in messages]


@router.post("/{thread_id}/reply", response_model=MailDraftSendResult, status_code=status.HTTP_201_CREATED)
def reply_to_thread(
    thread_id: str,
    payload: ThreadReplyCreate,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    outbound_sender: Annotated[OutboundMailSender, Depends(get_outbound_sender)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> MailDraftSendResult:
    authorize_thread(session, auth, thread_id)
    service = ConversationService(session, settings, outbound_sender, inbound_client)
    try:
        draft, thread, message = service.reply_to_thread(thread_id, payload)
    except (ThreadNotFoundError, MailboxNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MailTransportError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return MailDraftSendResult(
        draft=MailDraftRead.model_validate(draft),
        thread=MailThreadRead.model_validate(thread),
        message=_build_message_read(message, session),
    )


@router.patch("/{thread_id}/messages/{message_id}/read", response_model=MailMessageRead)
def mark_message_read(
    thread_id: str,
    message_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    outbound_sender: Annotated[OutboundMailSender, Depends(get_outbound_sender)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> MailMessageRead:
    authorize_thread(session, auth, thread_id)
    service = ConversationService(session, settings, outbound_sender, inbound_client)
    try:
        message = service.mark_message_read(message_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _build_message_read(message, session)
