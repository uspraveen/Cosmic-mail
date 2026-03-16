from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from cosmic_mail.api.auth import AuthContext, authorize_approval
from cosmic_mail.api.deps import get_auth_context, get_inbound_client, get_outbound_sender, get_session, get_settings
from cosmic_mail.core.config import Settings
from cosmic_mail.domain.models import ApprovalStatus
from cosmic_mail.domain.repositories import AgentRepository, AttachmentRepository, DraftRepository, MailboxRepository, OutboundApprovalRepository
from cosmic_mail.domain.schemas import (
    ApprovalDraftEdit,
    ApprovalRejectBody,
    AttachmentRead,
    MailDraftRead,
    MailDraftSendResult,
    MailMessageRead,
    MailThreadRead,
    OutboundApprovalRead,
)
from cosmic_mail.services.conversations import (
    ApprovalNotFoundError,
    ApprovalStateError,
    ConversationService,
    DraftNotFoundError,
    MailTransportError,
    MailboxCredentialsError,
    MailboxNotFoundError,
)
from cosmic_mail.services.inbound import InboundMailboxClient
from cosmic_mail.services.outbound import OutboundMailSender

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _build_approval_read(approval, session: Session) -> OutboundApprovalRead:
    agent = AgentRepository(session).get(approval.agent_id) if approval.agent_id else None
    mailbox = MailboxRepository(session).get(approval.mailbox_id)
    draft = DraftRepository(session).get(approval.draft_id) if approval.draft_id else None
    draft_read = MailDraftRead.model_validate(draft) if draft else None
    return OutboundApprovalRead(
        id=approval.id,
        organization_id=approval.organization_id,
        agent_id=approval.agent_id,
        agent_name=agent.name if agent else None,
        mailbox_id=approval.mailbox_id,
        mailbox_address=mailbox.address if mailbox else "",
        draft_id=approval.draft_id,
        draft=draft_read,
        status=ApprovalStatus(approval.status),
        reviewer_note=approval.reviewer_note,
        created_at=approval.created_at,
        reviewed_at=approval.reviewed_at,
    )


def _build_message_read(message, session) -> MailMessageRead:
    attachments = [
        AttachmentRead.model_validate(a)
        for a in AttachmentRepository(session).list_for_message(message.id)
    ]
    data = MailMessageRead.model_validate(message)
    data.attachments = attachments
    return data


@router.get("", response_model=list[OutboundApprovalRead])
def list_approvals(
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    approval_status: Annotated[str | None, Query(alias="status")] = None,
    agent_id: Annotated[str | None, Query()] = None,
    mailbox_id: Annotated[str | None, Query()] = None,
    organization_id: Annotated[str | None, Query()] = None,
) -> list[OutboundApprovalRead]:
    from sqlalchemy import select
    from cosmic_mail.domain.models import OutboundApproval
    query = select(OutboundApproval).order_by(OutboundApproval.created_at.desc())
    if not auth.is_admin:
        query = query.where(OutboundApproval.organization_id == auth.organization_id)
    elif organization_id:
        query = query.where(OutboundApproval.organization_id == organization_id)
    if approval_status:
        query = query.where(OutboundApproval.status == approval_status)
    if agent_id:
        query = query.where(OutboundApproval.agent_id == agent_id)
    if mailbox_id:
        query = query.where(OutboundApproval.mailbox_id == mailbox_id)
    approvals = list(session.scalars(query))
    return [_build_approval_read(a, session) for a in approvals]


@router.get("/{approval_id}", response_model=OutboundApprovalRead)
def get_approval(
    approval_id: str,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> OutboundApprovalRead:
    authorize_approval(session, auth, approval_id)
    approval = OutboundApprovalRepository(session).get(approval_id)
    return _build_approval_read(approval, session)


@router.patch("/{approval_id}", response_model=OutboundApprovalRead)
def edit_approval_draft(
    approval_id: str,
    payload: ApprovalDraftEdit,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    outbound_sender: Annotated[OutboundMailSender, Depends(get_outbound_sender)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> OutboundApprovalRead:
    authorize_approval(session, auth, approval_id)
    service = ConversationService(session, settings, outbound_sender, inbound_client)
    to_recipients = [r.model_dump() for r in payload.to_recipients] if payload.to_recipients is not None else None
    cc_recipients = [r.model_dump() for r in payload.cc_recipients] if payload.cc_recipients is not None else None
    try:
        approval, _ = service.edit_approval_draft(
            approval_id,
            subject=payload.subject,
            text_body=payload.text_body,
            html_body=payload.html_body,
            to_recipients=to_recipients,
            cc_recipients=cc_recipients,
        )
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ApprovalStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _build_approval_read(approval, session)


@router.post("/{approval_id}/approve", response_model=MailDraftSendResult)
def approve_outbound(
    approval_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    outbound_sender: Annotated[OutboundMailSender, Depends(get_outbound_sender)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> MailDraftSendResult:
    authorize_approval(session, auth, approval_id)
    service = ConversationService(session, settings, outbound_sender, inbound_client)
    try:
        _, draft, thread, message = service.approve_outbound(approval_id)
    except (ApprovalNotFoundError, DraftNotFoundError, MailboxNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ApprovalStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (MailTransportError, MailboxCredentialsError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return MailDraftSendResult(
        draft=MailDraftRead.model_validate(draft),
        thread=MailThreadRead.model_validate(thread),
        message=_build_message_read(message, session),
    )


@router.post("/{approval_id}/reject", response_model=OutboundApprovalRead)
def reject_outbound(
    approval_id: str,
    payload: ApprovalRejectBody,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    outbound_sender: Annotated[OutboundMailSender, Depends(get_outbound_sender)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> OutboundApprovalRead:
    authorize_approval(session, auth, approval_id)
    service = ConversationService(session, settings, outbound_sender, inbound_client)
    try:
        approval, _ = service.reject_outbound(approval_id, note=payload.note)
    except ApprovalNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ApprovalStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _build_approval_read(approval, session)
