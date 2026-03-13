from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from cosmic_mail.api.auth import AuthContext, require_admin
from cosmic_mail.api.deps import get_auth_context, get_sync_worker
from cosmic_mail.domain.schemas import AuthContextRead, SyncRunResult, SyncWorkerStatusRead
from cosmic_mail.services.sync_manager import SyncWorker

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/auth-context", response_model=AuthContextRead)
def get_auth_context_snapshot(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> AuthContextRead:
    return AuthContextRead(
        is_admin=auth.is_admin,
        organization_id=auth.organization_id,
        api_key_id=auth.api_key_id,
        api_key_name=auth.api_key_name,
    )


@router.get("/sync-worker", response_model=SyncWorkerStatusRead)
def get_sync_worker_status(
    sync_worker: Annotated[SyncWorker, Depends(get_sync_worker)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> SyncWorkerStatusRead:
    require_admin(auth)
    snapshot = sync_worker.status()
    return SyncWorkerStatusRead(
        enabled=snapshot.enabled,
        running=snapshot.running,
        interval_seconds=snapshot.interval_seconds,
        last_started_at=snapshot.last_started_at,
        last_completed_at=snapshot.last_completed_at,
        last_run_mailbox_count=snapshot.last_run_mailbox_count,
        last_run_imported_count=snapshot.last_run_imported_count,
        last_run_failed_count=snapshot.last_run_failed_count,
        last_error=snapshot.last_error,
    )


@router.post("/sync-worker/run-once", response_model=SyncRunResult)
def run_sync_worker_once(
    sync_worker: Annotated[SyncWorker, Depends(get_sync_worker)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    organization_id: str | None = None,
) -> SyncRunResult:
    require_admin(auth)
    report = sync_worker.run_once(organization_id=organization_id)
    return SyncRunResult(
        organization_id=report.organization_id,
        mailbox_count=report.mailbox_count,
        synced_mailboxes=report.synced_mailboxes,
        failed_mailboxes=report.failed_mailboxes,
        imported_count=report.imported_count,
        skipped_count=report.skipped_count,
        completed_at=report.completed_at,
        errors=report.errors,
    )
