from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from cosmic_mail.api.auth import AuthContext, authorize_organization, authorize_organization_access, require_admin
from cosmic_mail.api.deps import get_auth_context, get_inbound_client, get_session, get_settings
from cosmic_mail.core.config import Settings
from cosmic_mail.domain.schemas import (
    OrganizationApiKeyCreate,
    OrganizationApiKeyCreateResult,
    OrganizationApiKeyRead,
    OrganizationCreate,
    OrganizationRead,
    SyncRunResult,
)
from cosmic_mail.services.api_keys import (
    OrganizationApiKeyNotFoundError,
    OrganizationApiKeyOrganizationNotFoundError,
    OrganizationApiKeyService,
)
from cosmic_mail.services.inbound import InboundMailboxClient
from cosmic_mail.services.organizations import OrganizationConflictError, OrganizationService
from cosmic_mail.services.sync_manager import MailboxSyncService

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(
    payload: OrganizationCreate,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> OrganizationRead:
    require_admin(auth)
    service = OrganizationService(session)
    try:
        organization = service.create(payload)
    except OrganizationConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return OrganizationRead.model_validate(organization)


@router.get("", response_model=list[OrganizationRead])
def list_organizations(
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[OrganizationRead]:
    service = OrganizationService(session)
    organizations = service.list() if auth.is_admin else [authorize_organization(session, auth, auth.organization_id or "")]
    return [OrganizationRead.model_validate(item) for item in organizations]


@router.post("/{organization_id}/api-keys", response_model=OrganizationApiKeyCreateResult, status_code=status.HTTP_201_CREATED)
def create_organization_api_key(
    organization_id: str,
    payload: OrganizationApiKeyCreate,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> OrganizationApiKeyCreateResult:
    authorize_organization_access(auth, organization_id)
    service = OrganizationApiKeyService(session, settings)
    try:
        api_key, plaintext_key = service.create(organization_id, payload)
    except OrganizationApiKeyOrganizationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return OrganizationApiKeyCreateResult(
        api_key=OrganizationApiKeyRead.model_validate(api_key),
        plaintext_key=plaintext_key,
    )


@router.get("/{organization_id}/api-keys", response_model=list[OrganizationApiKeyRead])
def list_organization_api_keys(
    organization_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[OrganizationApiKeyRead]:
    authorize_organization_access(auth, organization_id)
    service = OrganizationApiKeyService(session, settings)
    try:
        api_keys = service.list_for_organization(organization_id)
    except OrganizationApiKeyOrganizationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return [OrganizationApiKeyRead.model_validate(api_key) for api_key in api_keys]


@router.delete("/{organization_id}/api-keys/{api_key_id}", response_model=OrganizationApiKeyRead)
def revoke_organization_api_key(
    organization_id: str,
    api_key_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> OrganizationApiKeyRead:
    authorize_organization_access(auth, organization_id)
    service = OrganizationApiKeyService(session, settings)
    try:
        api_key = service.revoke(organization_id, api_key_id)
    except OrganizationApiKeyOrganizationNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OrganizationApiKeyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return OrganizationApiKeyRead.model_validate(api_key)


@router.post("/{organization_id}/sync-mailboxes", response_model=SyncRunResult)
def sync_organization_mailboxes(
    organization_id: str,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    inbound_client: Annotated[InboundMailboxClient, Depends(get_inbound_client)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> SyncRunResult:
    authorize_organization_access(auth, organization_id)
    service = MailboxSyncService(session, settings, inbound_client)
    report = service.run_organization_sync(organization_id)
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
