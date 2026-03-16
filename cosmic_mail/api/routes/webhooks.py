from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from cosmic_mail.api.auth import AuthContext, authorize_organization_access
from cosmic_mail.api.deps import get_auth_context, get_session
from cosmic_mail.domain.models import Webhook
from cosmic_mail.domain.repositories import WebhookRepository
from cosmic_mail.domain.schemas import WebhookCreate, WebhookRead

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("", response_model=WebhookRead, status_code=status.HTTP_201_CREATED)
def create_webhook(
    payload: WebhookCreate,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> WebhookRead:
    org_id = auth.organization_id
    if org_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="org api key required")
    authorize_organization_access(auth, org_id)
    repo = WebhookRepository(session)
    webhook = Webhook(
        organization_id=org_id,
        mailbox_id=payload.mailbox_id,
        event_type=payload.event_type.value,
        url=str(payload.url),
        secret=payload.secret,
        is_active=True,
    )
    repo.add(webhook)
    session.commit()
    session.refresh(webhook)
    return WebhookRead.model_validate(webhook)


@router.get("", response_model=list[WebhookRead])
def list_webhooks(
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[WebhookRead]:
    repo = WebhookRepository(session)
    return [WebhookRead.model_validate(wh) for wh in repo.list_for_organization(None if auth.is_admin else auth.organization_id)]


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def delete_webhook(
    webhook_id: str,
    session: Annotated[Session, Depends(get_session)],
    auth: Annotated[AuthContext, Depends(get_auth_context)],
) -> None:
    repo = WebhookRepository(session)
    webhook = repo.get(webhook_id)
    if webhook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook not found")
    if not auth.is_admin:
        authorize_organization_access(auth, webhook.organization_id)
    repo.delete(webhook)
    session.commit()
