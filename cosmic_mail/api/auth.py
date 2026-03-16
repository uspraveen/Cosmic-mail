from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from cosmic_mail.core.config import Settings
from cosmic_mail.core.security import compare_secret
from cosmic_mail.domain.models import AgentProfile, Domain, MailDraft, MailThread, MailboxIdentity, Organization, OrganizationApiKey, OutboundApproval
from cosmic_mail.domain.repositories import (
    AgentRepository,
    DomainRepository,
    DraftRepository,
    MailboxRepository,
    OrganizationRepository,
    OutboundApprovalRepository,
    ThreadRepository,
)
from cosmic_mail.services.api_keys import OrganizationApiKeyService


@dataclass(frozen=True)
class AuthContext:
    is_admin: bool
    organization_id: str | None = None
    api_key_id: str | None = None
    api_key_name: str | None = None


def authenticate_request(
    request: Request,
    session: Session,
    settings: Settings,
) -> AuthContext:
    plaintext_key = _extract_api_key(request)
    if plaintext_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing api key")

    if settings.admin_api_key and compare_secret(plaintext_key, settings.admin_api_key):
        return AuthContext(is_admin=True)

    api_key_service = OrganizationApiKeyService(session, settings)
    organization_api_key = api_key_service.authenticate(plaintext_key)
    if organization_api_key is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid api key")

    return AuthContext(
        is_admin=False,
        organization_id=organization_api_key.organization_id,
        api_key_id=organization_api_key.id,
        api_key_name=organization_api_key.name,
    )


def require_admin(auth: AuthContext) -> None:
    if not auth.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin api key required")


def authorize_organization_access(
    auth: AuthContext,
    organization_id: str,
) -> None:
    if auth.is_admin:
        return
    if auth.organization_id != organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="organization access denied")


def authorize_organization(
    session: Session,
    auth: AuthContext,
    organization_id: str,
) -> Organization:
    organization = OrganizationRepository(session).get(organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="organization not found")
    authorize_organization_access(auth, organization.id)
    return organization


def authorize_domain(
    session: Session,
    auth: AuthContext,
    domain_id: str,
) -> Domain:
    domain = DomainRepository(session).get(domain_id)
    if domain is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="domain not found")
    authorize_organization_access(auth, domain.organization_id)
    return domain


def authorize_agent(
    session: Session,
    auth: AuthContext,
    agent_id: str,
) -> AgentProfile:
    agent = AgentRepository(session).get(agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="agent not found")
    authorize_organization_access(auth, agent.organization_id)
    return agent


def authorize_mailbox(
    session: Session,
    auth: AuthContext,
    mailbox_id: str,
) -> MailboxIdentity:
    mailbox = MailboxRepository(session).get(mailbox_id)
    if mailbox is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mailbox not found")
    authorize_organization_access(auth, mailbox.organization_id)
    return mailbox


def authorize_thread(
    session: Session,
    auth: AuthContext,
    thread_id: str,
) -> MailThread:
    thread = ThreadRepository(session).get(thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="thread not found")
    authorize_organization_access(auth, thread.organization_id)
    return thread


def authorize_draft(
    session: Session,
    auth: AuthContext,
    draft_id: str,
) -> MailDraft:
    draft = DraftRepository(session).get(draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="draft not found")
    authorize_organization_access(auth, draft.organization_id)
    return draft


def authorize_approval(
    session: Session,
    auth: AuthContext,
    approval_id: str,
) -> OutboundApproval:
    approval = OutboundApprovalRepository(session).get(approval_id)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval not found")
    authorize_organization_access(auth, approval.organization_id)
    return approval


def _extract_api_key(request: Request) -> str | None:
    api_key = request.headers.get("x-api-key")
    if api_key:
        return api_key.strip()

    authorization = request.headers.get("authorization")
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()
