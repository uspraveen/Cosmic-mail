from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import UploadFile

from cosmic_mail.domain.models import MailAttachment


class AttachmentStorageError(RuntimeError):
    pass


class AttachmentTooLargeError(ValueError):
    pass


class AttachmentService:
    def __init__(self, storage_path: str, max_size_mb: int) -> None:
        self._root = Path(storage_path)
        self._max_bytes = max_size_mb * 1024 * 1024

    def save_upload(
        self,
        upload: UploadFile,
        *,
        organization_id: str,
        mailbox_id: str,
        draft_id: str | None = None,
        message_id: str | None = None,
    ) -> MailAttachment:
        attachment_id = str(uuid.uuid4())
        filename = upload.filename or "attachment"
        dest_dir = self._root / attachment_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        content = upload.file.read()
        if len(content) > self._max_bytes:
            raise AttachmentTooLargeError(
                f"attachment exceeds {self._max_bytes // (1024 * 1024)} MB limit"
            )

        try:
            dest_path.write_bytes(content)
        except OSError as exc:
            raise AttachmentStorageError(f"could not write attachment: {exc}") from exc

        return MailAttachment(
            id=attachment_id,
            organization_id=organization_id,
            mailbox_id=mailbox_id,
            message_id=message_id,
            draft_id=draft_id,
            filename=filename,
            content_type=upload.content_type or "application/octet-stream",
            size_bytes=len(content),
            storage_path=str(dest_path),
        )

    def save_inbound(
        self,
        *,
        filename: str,
        content_type: str,
        data: bytes,
        organization_id: str,
        mailbox_id: str,
        message_id: str,
    ) -> MailAttachment:
        if len(data) > self._max_bytes:
            raise AttachmentTooLargeError(
                f"attachment exceeds {self._max_bytes // (1024 * 1024)} MB limit"
            )
        attachment_id = str(uuid.uuid4())
        dest_dir = self._root / attachment_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / filename

        try:
            dest_path.write_bytes(data)
        except OSError as exc:
            raise AttachmentStorageError(f"could not write attachment: {exc}") from exc

        return MailAttachment(
            id=attachment_id,
            organization_id=organization_id,
            mailbox_id=mailbox_id,
            message_id=message_id,
            draft_id=None,
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            storage_path=str(dest_path),
        )

    def delete_file(self, attachment: MailAttachment) -> None:
        try:
            path = Path(attachment.storage_path)
            if path.is_file():
                path.unlink()
            parent = path.parent
            if parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
        except OSError:
            pass

    def get_file_path(self, attachment: MailAttachment) -> Path:
        return Path(attachment.storage_path)
