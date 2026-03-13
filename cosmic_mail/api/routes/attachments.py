from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from cosmic_mail.api.auth import AuthContext, authorize_draft
from cosmic_mail.api.deps import get_auth_context, get_session, get_settings
from cosmic_mail.core.config import Settings
from cosmic_mail.domain.repositories import AttachmentRepository
from cosmic_mail.domain.schemas import AttachmentRead
from cosmic_mail.services.attachments import AttachmentService, AttachmentTooLargeError

router = APIRouter(prefix="/attachments", tags=["attachments"])


def _get_attachment_service(settings: Settings) -> AttachmentService:
    return AttachmentService(settings.attachment_storage_path, settings.max_attachment_size_mb)


@router.post("/drafts/{draft_id}", response_model=AttachmentRead, status_code=status.HTTP_201_CREATED)
def upload_draft_attachment(
    draft_id: str,
    file: UploadFile,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AttachmentRead:
    draft = authorize_draft(session, auth, draft_id)
    attachment_service = _get_attachment_service(settings)
    repo = AttachmentRepository(session)

    try:
        attachment = attachment_service.save_upload(
            file,
            organization_id=draft.organization_id,
            mailbox_id=draft.mailbox_id,
            draft_id=draft_id,
        )
    except AttachmentTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc

    repo.add(attachment)
    session.commit()
    session.refresh(attachment)
    return AttachmentRead.model_validate(attachment)


@router.get("/{attachment_id}/download")
def download_attachment(
    attachment_id: str,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> FileResponse:
    repo = AttachmentRepository(session)
    attachment = repo.get(attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="attachment not found")

    # Auth: attachment belongs to a message or draft — check org access
    if not auth.is_admin and auth.organization_id != attachment.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="access denied")

    file_path = Path(attachment.storage_path)
    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="attachment file missing")

    return FileResponse(
        path=str(file_path),
        filename=attachment.filename,
        media_type=attachment.content_type,
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> None:
    repo = AttachmentRepository(session)
    attachment = repo.get(attachment_id)
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="attachment not found")

    if not auth.is_admin and auth.organization_id != attachment.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="access denied")

    # Only allow deleting draft attachments via API (message attachments are inbound-only)
    if attachment.draft_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cannot delete inbound attachment")

    attachment_service = _get_attachment_service(settings)
    attachment_service.delete_file(attachment)
    repo.delete(attachment)
    session.commit()
