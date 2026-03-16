from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from cosmic_mail.api.auth import AuthContext
from cosmic_mail.api.deps import get_auth_context, get_session
from cosmic_mail.domain.models import MessageDirection
from cosmic_mail.domain.repositories import AttachmentRepository, MessageRepository, ThreadRepository
from cosmic_mail.domain.schemas import (
    AttachmentRead,
    MailMessageRead,
    MailThreadRead,
    MessageSearchResult,
    ThreadSearchResult,
)

router = APIRouter(prefix="/search", tags=["search"])

_VALID_DIRECTIONS = {MessageDirection.inbound.value, MessageDirection.outbound.value}


@router.get("/messages", response_model=MessageSearchResult)
def search_messages(
    q: Annotated[str, Query(min_length=1, max_length=500, description="Search query — supports AND, OR, phrases, and negation (-word)")],
    mailbox_id: Annotated[str | None, Query(description="Restrict to a specific mailbox")] = None,
    direction: Annotated[str | None, Query(description="Filter by direction: inbound | outbound")] = None,
    date_from: Annotated[datetime | None, Query(description="Earliest created_at (ISO 8601)")] = None,
    date_to: Annotated[datetime | None, Query(description="Latest created_at (ISO 8601)")] = None,
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Results per page (max 100)")] = 20,
    session: Annotated[Session, Depends(get_session)] = ...,
    auth: Annotated[AuthContext, Depends(get_auth_context)] = ...,
) -> MessageSearchResult:
    if not auth.is_admin and auth.organization_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not authorized")

    if direction is not None and direction not in _VALID_DIRECTIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"direction must be one of: {', '.join(sorted(_VALID_DIRECTIONS))}",
        )

    organization_id = None if auth.is_admin else auth.organization_id

    repo = MessageRepository(session)
    total, messages = repo.search(
        q,
        organization_id=organization_id,
        mailbox_id=mailbox_id,
        direction=direction,
        date_from=date_from,
        date_to=date_to,
        page=page,
        per_page=per_page,
    )

    att_repo = AttachmentRepository(session)
    results: list[MailMessageRead] = []
    for msg in messages:
        atts = att_repo.list_for_message(msg.id)
        msg_read = MailMessageRead.model_validate(msg)
        msg_read.attachments = [AttachmentRead.model_validate(a) for a in atts]
        results.append(msg_read)

    return MessageSearchResult(total=total, page=page, per_page=per_page, results=results)


@router.get("/threads", response_model=ThreadSearchResult)
def search_threads(
    q: Annotated[str, Query(min_length=1, max_length=500, description="Search query — supports AND, OR, phrases, and negation (-word)")],
    mailbox_id: Annotated[str | None, Query(description="Restrict to a specific mailbox")] = None,
    date_from: Annotated[datetime | None, Query(description="Earliest last_message_at (ISO 8601)")] = None,
    date_to: Annotated[datetime | None, Query(description="Latest last_message_at (ISO 8601)")] = None,
    page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Results per page (max 100)")] = 20,
    session: Annotated[Session, Depends(get_session)] = ...,
    auth: Annotated[AuthContext, Depends(get_auth_context)] = ...,
) -> ThreadSearchResult:
    if not auth.is_admin and auth.organization_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not authorized")

    organization_id = None if auth.is_admin else auth.organization_id

    repo = ThreadRepository(session)
    total, threads = repo.search(
        q,
        organization_id=organization_id,
        mailbox_id=mailbox_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        per_page=per_page,
    )

    results = [MailThreadRead.model_validate(t) for t in threads]
    return ThreadSearchResult(total=total, page=page, per_page=per_page, results=results)
