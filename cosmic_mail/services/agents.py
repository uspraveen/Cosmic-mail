from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cosmic_mail.domain.models import AgentMailboxLink, AgentProfile, AgentStatus, Domain, MailboxIdentity, Organization
from cosmic_mail.domain.repositories import (
    AgentMailboxLinkRepository,
    AgentRepository,
    DomainRepository,
    MailboxRepository,
    OrganizationRepository,
)
from cosmic_mail.domain.schemas import AgentCreate, AgentMailboxLinkCreate, AgentUpdate
from cosmic_mail.domain.validation import slugify


HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class AgentConflictError(ValueError):
    pass


class AgentNotFoundError(ValueError):
    pass


class AgentOrganizationNotFoundError(ValueError):
    pass


class AgentDomainNotFoundError(ValueError):
    pass


class AgentMailboxNotFoundError(ValueError):
    pass


class AgentMailboxConflictError(ValueError):
    pass


@dataclass(frozen=True)
class AgentMailboxLinkView:
    link: AgentMailboxLink
    mailbox: MailboxIdentity
    domain: Domain | None


@dataclass(frozen=True)
class AgentProfileView:
    agent: AgentProfile
    organization: Organization | None
    default_domain: Domain | None
    mailboxes: list[AgentMailboxLinkView]


class AgentService:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._organizations = OrganizationRepository(session)
        self._domains = DomainRepository(session)
        self._mailboxes = MailboxRepository(session)
        self._agents = AgentRepository(session)
        self._agent_mailboxes = AgentMailboxLinkRepository(session)

    def create(self, payload: AgentCreate) -> AgentProfileView:
        organization = self._organizations.get(payload.organization_id)
        if organization is None:
            raise AgentOrganizationNotFoundError("organization not found")

        default_domain = self._resolve_default_domain(payload.organization_id, payload.default_domain_id)
        slug = payload.slug or slugify(payload.name)
        accent_color = self._normalize_accent_color(payload.accent_color)

        agent = AgentProfile(
            organization_id=payload.organization_id,
            default_domain_id=default_domain.id if default_domain else None,
            name=payload.name.strip(),
            slug=slug,
            title=payload.title.strip() if payload.title else None,
            persona_summary=payload.persona_summary.strip() if payload.persona_summary else None,
            system_prompt=payload.system_prompt.strip() if payload.system_prompt else None,
            signature=payload.signature.strip() if payload.signature else None,
            accent_color=accent_color,
            avatar_url=payload.avatar_url.strip() if payload.avatar_url else None,
            signature_graphic_url=payload.signature_graphic_url.strip() if payload.signature_graphic_url else None,
            approval_required=payload.approval_required,
            status=AgentStatus.active.value,
        )
        try:
            self._agents.add(agent)
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise AgentConflictError("agent slug already exists") from exc
        self._session.refresh(agent)
        return self._build_view(agent, organization=organization)

    def list(self, *, organization_id: str | None = None) -> list[AgentProfileView]:
        if organization_id is not None:
            agents = self._agents.list_for_organization(organization_id)
        else:
            agents = self._agents.list()
        return [self._build_view(agent) for agent in agents]

    def get(self, agent_id: str) -> AgentProfileView:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentNotFoundError("agent not found")
        return self._build_view(agent)

    def update(self, agent_id: str, payload: AgentUpdate) -> AgentProfileView:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentNotFoundError("agent not found")

        updates = payload.model_dump(exclude_unset=True)
        if "name" in updates and payload.name is not None:
            agent.name = payload.name.strip()
        if "slug" in updates:
            if payload.slug is None:
                agent.slug = slugify(agent.name)
            else:
                agent.slug = payload.slug.strip().lower()
        if "title" in updates:
            agent.title = payload.title.strip() if payload.title else None
        if "persona_summary" in updates:
            agent.persona_summary = payload.persona_summary.strip() if payload.persona_summary else None
        if "system_prompt" in updates:
            agent.system_prompt = payload.system_prompt.strip() if payload.system_prompt else None
        if "signature" in updates:
            agent.signature = payload.signature.strip() if payload.signature else None
        if "accent_color" in updates:
            agent.accent_color = self._normalize_accent_color(payload.accent_color)
        if "avatar_url" in updates:
            agent.avatar_url = payload.avatar_url.strip() if payload.avatar_url else None
        if "signature_graphic_url" in updates:
            agent.signature_graphic_url = payload.signature_graphic_url.strip() if payload.signature_graphic_url else None
        if "approval_required" in updates and payload.approval_required is not None:
            agent.approval_required = payload.approval_required
        if "status" in updates and payload.status is not None:
            agent.status = payload.status.value
        if "default_domain_id" in updates:
            default_domain = self._resolve_default_domain(agent.organization_id, payload.default_domain_id)
            agent.default_domain_id = default_domain.id if default_domain else None

        try:
            self._session.add(agent)
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise AgentConflictError("agent slug already exists") from exc
        self._session.refresh(agent)
        return self._build_view(agent)

    def link_mailbox(self, agent_id: str, payload: AgentMailboxLinkCreate) -> AgentProfileView:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentNotFoundError("agent not found")

        mailbox = self._mailboxes.get(payload.mailbox_id)
        if mailbox is None:
            raise AgentMailboxNotFoundError("mailbox not found")
        if mailbox.organization_id != agent.organization_id:
            raise AgentMailboxNotFoundError("mailbox not found")
        if self._agent_mailboxes.get_by_agent_and_mailbox(agent.id, mailbox.id):
            raise AgentMailboxConflictError("mailbox is already linked to the agent")

        existing_links = self._agent_mailboxes.list_for_agent(agent.id)
        is_primary = payload.is_primary or not existing_links
        if is_primary:
            for link in existing_links:
                link.is_primary = False
                self._session.add(link)

        link = AgentMailboxLink(
            organization_id=agent.organization_id,
            agent_id=agent.id,
            mailbox_id=mailbox.id,
            label=payload.label.strip() if payload.label else None,
            is_primary=is_primary,
        )
        try:
            self._agent_mailboxes.add(link)
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise AgentMailboxConflictError("mailbox is already linked to the agent") from exc
        return self.get(agent.id)

    def unlink_mailbox(self, agent_id: str, mailbox_id: str) -> AgentProfileView:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentNotFoundError("agent not found")

        link = self._agent_mailboxes.get_by_agent_and_mailbox(agent.id, mailbox_id)
        if link is None:
            raise AgentMailboxNotFoundError("agent mailbox link not found")

        removed_primary = link.is_primary
        self._agent_mailboxes.delete(link)
        self._session.flush()

        if removed_primary:
            remaining = self._agent_mailboxes.list_for_agent(agent.id)
            if remaining:
                remaining[0].is_primary = True
                self._session.add(remaining[0])

        self._session.commit()
        return self.get(agent.id)

    def upload_avatar(self, agent_id: str, data: bytes, *, ext: str, storage_path: str) -> AgentProfileView:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentNotFoundError("agent not found")
        import os
        dir_path = os.path.join(storage_path, "avatars", agent_id)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, f"avatar{ext}")
        with open(file_path, "wb") as fh:
            fh.write(data)
        agent.avatar_url = f"/v1/agents/{agent_id}/avatar"
        self._session.add(agent)
        self._session.commit()
        self._session.refresh(agent)
        return self._build_view(agent)

    def get_avatar_path(self, agent_id: str, *, storage_path: str) -> str:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentNotFoundError("agent not found")
        import glob, os
        matches = glob.glob(os.path.join(storage_path, "avatars", agent_id, "avatar.*"))
        if not matches:
            raise FileNotFoundError("avatar not found")
        return matches[0]

    def upload_signature_graphic(self, agent_id: str, data: bytes, *, ext: str, storage_path: str) -> AgentProfileView:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentNotFoundError("agent not found")
        import os
        dir_path = os.path.join(storage_path, "sig-graphics", agent_id)
        os.makedirs(dir_path, exist_ok=True)
        file_path = os.path.join(dir_path, f"signature{ext}")
        with open(file_path, "wb") as fh:
            fh.write(data)
        agent.signature_graphic_url = f"/v1/agents/{agent_id}/signature-graphic"
        self._session.add(agent)
        self._session.commit()
        self._session.refresh(agent)
        return self._build_view(agent)

    def get_signature_graphic_path(self, agent_id: str, *, storage_path: str) -> str:
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentNotFoundError("agent not found")
        import glob, os
        matches = glob.glob(os.path.join(storage_path, "sig-graphics", agent_id, "signature.*"))
        if not matches:
            raise FileNotFoundError("signature graphic not found")
        return matches[0]

    def _build_view(self, agent: AgentProfile, *, organization: Organization | None = None) -> AgentProfileView:
        default_domain = self._domains.get(agent.default_domain_id) if agent.default_domain_id else None
        organization = organization or self._organizations.get(agent.organization_id)
        links = self._agent_mailboxes.list_for_agent(agent.id)
        mailboxes = []
        for link in links:
            mailbox = self._mailboxes.get(link.mailbox_id)
            if mailbox is None:
                continue
            domain = self._domains.get(mailbox.domain_id)
            mailboxes.append(AgentMailboxLinkView(link=link, mailbox=mailbox, domain=domain))
        return AgentProfileView(
            agent=agent,
            organization=organization,
            default_domain=default_domain,
            mailboxes=mailboxes,
        )

    def _resolve_default_domain(self, organization_id: str, domain_id: str | None) -> Domain | None:
        if domain_id is None:
            return None
        domain = self._domains.get(domain_id)
        if domain is None or domain.organization_id != organization_id:
            raise AgentDomainNotFoundError("default domain not found")
        return domain

    @staticmethod
    def _normalize_accent_color(value: str | None) -> str:
        if value is None:
            return "#ff8a1f"
        accent_color = value.strip()
        if not HEX_COLOR_RE.match(accent_color):
            raise AgentConflictError("accent color must be a hex value like #ff8a1f")
        return accent_color.lower()
