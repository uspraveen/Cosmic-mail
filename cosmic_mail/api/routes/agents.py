from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from cosmic_mail.api.auth import AuthContext, authorize_agent, authorize_organization_access
from cosmic_mail.api.deps import get_auth_context, get_session
from cosmic_mail.core.config import get_settings
from cosmic_mail.domain.schemas import AgentCreate, AgentMailboxBindingRead, AgentMailboxLinkCreate, AgentRead, AgentUpdate
from cosmic_mail.services.agents import (
    AgentConflictError,
    AgentDomainNotFoundError,
    AgentMailboxConflictError,
    AgentMailboxNotFoundError,
    AgentNotFoundError,
    AgentOrganizationNotFoundError,
    AgentProfileView,
    AgentService,
)

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreate,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AgentRead:
    authorize_organization_access(auth, payload.organization_id)
    service = AgentService(session)
    try:
        agent = service.create(payload)
    except AgentOrganizationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AgentDomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AgentConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _build_agent_read(agent)


@router.get("", response_model=list[AgentRead])
def list_agents(
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[AgentRead]:
    service = AgentService(session)
    agents = service.list(organization_id=None if auth.is_admin else auth.organization_id)
    start = (page - 1) * per_page
    return [_build_agent_read(agent) for agent in agents[start : start + per_page]]


@router.get("/{agent_id}", response_model=AgentRead)
def get_agent(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AgentRead:
    authorize_agent(session, auth, agent_id)
    service = AgentService(session)
    try:
        agent = service.get(agent_id)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _build_agent_read(agent)


@router.patch("/{agent_id}", response_model=AgentRead)
def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AgentRead:
    authorize_agent(session, auth, agent_id)
    service = AgentService(session)
    try:
        agent = service.update(agent_id, payload)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AgentDomainNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AgentConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _build_agent_read(agent)


@router.post("/{agent_id}/mailboxes", response_model=AgentRead)
def link_mailbox_to_agent(
    agent_id: str,
    payload: AgentMailboxLinkCreate,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AgentRead:
    authorize_agent(session, auth, agent_id)
    service = AgentService(session)
    try:
        agent = service.link_mailbox(agent_id, payload)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AgentMailboxNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AgentMailboxConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _build_agent_read(agent)


@router.delete("/{agent_id}/mailboxes/{mailbox_id}", response_model=AgentRead)
def unlink_mailbox_from_agent(
    agent_id: str,
    mailbox_id: str,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AgentRead:
    authorize_agent(session, auth, agent_id)
    service = AgentService(session)
    try:
        agent = service.unlink_mailbox(agent_id, mailbox_id)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AgentMailboxNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _build_agent_read(agent)


@router.post("/{agent_id}/avatar", response_model=AgentRead)
async def upload_agent_avatar(
    agent_id: str,
    file: Annotated[UploadFile, File(...)],
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AgentRead:
    authorize_agent(session, auth, agent_id)
    settings = get_settings()
    data = await file.read()
    max_bytes = settings.max_attachment_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"file exceeds {settings.max_attachment_size_mb}MB limit")
    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    service = AgentService(session)
    try:
        view = service.upload_avatar(agent_id, data, ext=ext, storage_path=settings.attachment_storage_path)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _build_agent_read(view)


@router.get("/{agent_id}/avatar")
def get_agent_avatar(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> FileResponse:
    authorize_agent(session, auth, agent_id)
    settings = get_settings()
    service = AgentService(session)
    try:
        path = service.get_avatar_path(agent_id, storage_path=settings.attachment_storage_path)
    except (AgentNotFoundError, FileNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="avatar not found") from exc
    return FileResponse(path)


@router.post("/{agent_id}/signature-graphic", response_model=AgentRead)
async def upload_signature_graphic(
    agent_id: str,
    file: Annotated[UploadFile, File(...)],
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AgentRead:
    authorize_agent(session, auth, agent_id)
    settings = get_settings()
    data = await file.read()
    max_bytes = settings.max_attachment_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"file exceeds {settings.max_attachment_size_mb}MB limit")
    ext = os.path.splitext(file.filename or "")[1].lower() or ".png"
    service = AgentService(session)
    try:
        view = service.upload_signature_graphic(agent_id, data, ext=ext, storage_path=settings.attachment_storage_path)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _build_agent_read(view)


@router.get("/{agent_id}/signature-graphic")
def get_signature_graphic(
    agent_id: str,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> FileResponse:
    authorize_agent(session, auth, agent_id)
    settings = get_settings()
    service = AgentService(session)
    try:
        path = service.get_signature_graphic_path(agent_id, storage_path=settings.attachment_storage_path)
    except (AgentNotFoundError, FileNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="signature graphic not found") from exc
    return FileResponse(path)


def _build_agent_read(view: AgentProfileView) -> AgentRead:
    return AgentRead(
        id=view.agent.id,
        organization_id=view.agent.organization_id,
        default_domain_id=view.agent.default_domain_id,
        default_domain_name=view.default_domain.name if view.default_domain else None,
        name=view.agent.name,
        slug=view.agent.slug,
        title=view.agent.title,
        persona_summary=view.agent.persona_summary,
        system_prompt=view.agent.system_prompt,
        signature=view.agent.signature,
        accent_color=view.agent.accent_color,
        avatar_url=view.agent.avatar_url,
        signature_graphic_url=view.agent.signature_graphic_url,
        approval_required=view.agent.approval_required,
        status=view.agent.status,
        created_at=view.agent.created_at,
        updated_at=view.agent.updated_at,
        mailboxes=[
            AgentMailboxBindingRead(
                mailbox_id=entry.mailbox.id,
                address=entry.mailbox.address,
                display_name=entry.mailbox.display_name,
                domain_id=entry.mailbox.domain_id,
                domain_name=entry.domain.name if entry.domain else entry.mailbox.address.split("@", 1)[-1],
                label=entry.link.label,
                is_primary=entry.link.is_primary,
                inbound_sync_enabled=entry.mailbox.inbound_sync_enabled,
                last_synced_at=entry.mailbox.last_synced_at,
                last_sync_error=entry.mailbox.last_sync_error,
            )
            for entry in view.mailboxes
        ],
    )
