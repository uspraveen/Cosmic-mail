from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

def _dialect_name(session: Session) -> str:
    try:
        bind = session.get_bind()
        return bind.dialect.name
    except Exception:
        return "unknown"


from cosmic_mail.domain.models import (
    AgentMailboxLink,
    AgentProfile,
    ApprovalStatus,
    Domain,
    MailAttachment,
    MailDraft,
    MailMessage,
    MailThread,
    MailboxIdentity,
    MailboxStatus,
    Organization,
    OrganizationApiKey,
    OutboundApproval,
    Webhook,
)


class OrganizationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, organization: Organization) -> Organization:
        self.session.add(organization)
        self.session.flush()
        return organization

    def list(self) -> list[Organization]:
        return list(self.session.scalars(select(Organization).order_by(Organization.created_at)))

    def get(self, organization_id: str) -> Organization | None:
        return self.session.get(Organization, organization_id)

    def get_by_slug(self, slug: str) -> Organization | None:
        return self.session.scalar(select(Organization).where(Organization.slug == slug))


class DomainRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, domain: Domain) -> Domain:
        self.session.add(domain)
        self.session.flush()
        return domain

    def list(self) -> list[Domain]:
        return list(self.session.scalars(select(Domain).order_by(Domain.created_at)))

    def list_for_organization(self, organization_id: str) -> list[Domain]:
        query = select(Domain).where(Domain.organization_id == organization_id).order_by(Domain.created_at)
        return list(self.session.scalars(query))

    def get(self, domain_id: str) -> Domain | None:
        return self.session.get(Domain, domain_id)

    def get_by_name(self, name: str) -> Domain | None:
        return self.session.scalar(select(Domain).where(Domain.name == name))


class AgentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, agent: AgentProfile) -> AgentProfile:
        self.session.add(agent)
        self.session.flush()
        return agent

    def list(self) -> list[AgentProfile]:
        return list(self.session.scalars(select(AgentProfile).order_by(AgentProfile.created_at)))

    def list_for_organization(self, organization_id: str) -> list[AgentProfile]:
        query = select(AgentProfile).where(AgentProfile.organization_id == organization_id).order_by(AgentProfile.created_at)
        return list(self.session.scalars(query))

    def get(self, agent_id: str) -> AgentProfile | None:
        return self.session.get(AgentProfile, agent_id)

    def get_by_slug(self, organization_id: str, slug: str) -> AgentProfile | None:
        query = select(AgentProfile).where(
            AgentProfile.organization_id == organization_id,
            AgentProfile.slug == slug,
        )
        return self.session.scalar(query)


class AgentMailboxLinkRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, link: AgentMailboxLink) -> AgentMailboxLink:
        self.session.add(link)
        self.session.flush()
        return link

    def get_by_agent_and_mailbox(self, agent_id: str, mailbox_id: str) -> AgentMailboxLink | None:
        query = select(AgentMailboxLink).where(
            AgentMailboxLink.agent_id == agent_id,
            AgentMailboxLink.mailbox_id == mailbox_id,
        )
        return self.session.scalar(query)

    def list_for_agent(self, agent_id: str) -> list[AgentMailboxLink]:
        query = select(AgentMailboxLink).where(AgentMailboxLink.agent_id == agent_id).order_by(
            AgentMailboxLink.is_primary.desc(),
            AgentMailboxLink.created_at.asc(),
        )
        return list(self.session.scalars(query))

    def list_for_mailbox(self, mailbox_id: str) -> list[AgentMailboxLink]:
        query = select(AgentMailboxLink).where(AgentMailboxLink.mailbox_id == mailbox_id).order_by(
            AgentMailboxLink.is_primary.desc(),
            AgentMailboxLink.created_at.asc(),
        )
        return list(self.session.scalars(query))

    def list_for_organization(self, organization_id: str) -> list[AgentMailboxLink]:
        query = select(AgentMailboxLink).where(AgentMailboxLink.organization_id == organization_id).order_by(
            AgentMailboxLink.created_at.asc()
        )
        return list(self.session.scalars(query))

    def delete(self, link: AgentMailboxLink) -> None:
        self.session.delete(link)


class MailboxRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, mailbox: MailboxIdentity) -> MailboxIdentity:
        self.session.add(mailbox)
        self.session.flush()
        return mailbox

    def list(self) -> list[MailboxIdentity]:
        return list(self.session.scalars(select(MailboxIdentity).order_by(MailboxIdentity.created_at)))

    def list_for_organization(self, organization_id: str) -> list[MailboxIdentity]:
        query = select(MailboxIdentity).where(MailboxIdentity.organization_id == organization_id).order_by(
            MailboxIdentity.created_at
        )
        return list(self.session.scalars(query))

    def list_sync_enabled(
        self,
        *,
        organization_id: str | None = None,
        limit: int | None = None,
    ) -> list[MailboxIdentity]:
        query = select(MailboxIdentity).where(
            MailboxIdentity.status == MailboxStatus.active.value,
            MailboxIdentity.inbound_sync_enabled.is_(True),
        )
        if organization_id:
            query = query.where(MailboxIdentity.organization_id == organization_id)
        query = query.order_by(
            MailboxIdentity.last_synced_at.asc().nullsfirst(),
            MailboxIdentity.created_at.asc(),
        )
        if limit is not None:
            query = query.limit(limit)
        return list(self.session.scalars(query))

    def get(self, mailbox_id: str) -> MailboxIdentity | None:
        return self.session.get(MailboxIdentity, mailbox_id)

    def get_by_address(self, address: str) -> MailboxIdentity | None:
        return self.session.scalar(select(MailboxIdentity).where(MailboxIdentity.address == address))


class ThreadRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, thread: MailThread) -> MailThread:
        self.session.add(thread)
        self.session.flush()
        return thread

    def get(self, thread_id: str) -> MailThread | None:
        return self.session.get(MailThread, thread_id)

    def list_for_mailbox(self, mailbox_id: str) -> list[MailThread]:
        query = select(MailThread).where(MailThread.mailbox_id == mailbox_id).order_by(MailThread.last_message_at.desc())
        return list(self.session.scalars(query))

    def search(
        self,
        query: str,
        *,
        organization_id: str | None = None,
        mailbox_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[int, list[MailThread]]:
        per_page = min(per_page, 100)
        offset = (page - 1) * per_page

        base = []
        if organization_id is not None:
            base.append(MailThread.organization_id == organization_id)
        if mailbox_id is not None:
            base.append(MailThread.mailbox_id == mailbox_id)
        if date_from is not None:
            base.append(MailThread.last_message_at >= date_from)
        if date_to is not None:
            base.append(MailThread.last_message_at <= date_to)

        dialect = _dialect_name(self.session)
        if dialect == "postgresql":
            tsvec = func.to_tsvector("english", func.coalesce(MailThread.subject, ""))
            tsquery = func.websearch_to_tsquery("english", query)
            search_cond = tsvec.op("@@")(tsquery)
            rank_expr = func.ts_rank_cd(tsvec, tsquery)
            count_stmt = select(func.count()).select_from(MailThread).where(*base, search_cond)
            results_stmt = (
                select(MailThread)
                .where(*base, search_cond)
                .order_by(rank_expr.desc(), MailThread.last_message_at.desc())
                .offset(offset)
                .limit(per_page)
            )
        else:
            pattern = f"%{query}%"
            search_cond = MailThread.subject.ilike(pattern)
            count_stmt = select(func.count()).select_from(MailThread).where(*base, search_cond)
            results_stmt = (
                select(MailThread)
                .where(*base, search_cond)
                .order_by(MailThread.last_message_at.desc())
                .offset(offset)
                .limit(per_page)
            )

        total = self.session.scalar(count_stmt) or 0
        threads = list(self.session.scalars(results_stmt))
        return total, threads


class OrganizationApiKeyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, api_key: OrganizationApiKey) -> OrganizationApiKey:
        self.session.add(api_key)
        self.session.flush()
        return api_key

    def get(self, api_key_id: str) -> OrganizationApiKey | None:
        return self.session.get(OrganizationApiKey, api_key_id)

    def get_active_by_token_hash(self, token_hash: str) -> OrganizationApiKey | None:
        query = select(OrganizationApiKey).where(
            OrganizationApiKey.token_hash == token_hash,
            OrganizationApiKey.revoked_at.is_(None),
        )
        return self.session.scalar(query)

    def list_for_organization(self, organization_id: str) -> list[OrganizationApiKey]:
        query = (
            select(OrganizationApiKey)
            .where(OrganizationApiKey.organization_id == organization_id)
            .order_by(OrganizationApiKey.created_at.desc())
        )
        return list(self.session.scalars(query))


class DraftRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, draft: MailDraft) -> MailDraft:
        self.session.add(draft)
        self.session.flush()
        return draft

    def get(self, draft_id: str) -> MailDraft | None:
        return self.session.get(MailDraft, draft_id)

    def list_for_mailbox(self, mailbox_id: str) -> list[MailDraft]:
        query = select(MailDraft).where(MailDraft.mailbox_id == mailbox_id).order_by(MailDraft.updated_at.desc())
        return list(self.session.scalars(query))


class MessageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, message: MailMessage) -> MailMessage:
        self.session.add(message)
        self.session.flush()
        return message

    def get(self, message_id: str) -> MailMessage | None:
        return self.session.get(MailMessage, message_id)

    def get_by_mailbox_and_internet_id(self, mailbox_id: str, internet_message_id: str) -> MailMessage | None:
        query = select(MailMessage).where(
            MailMessage.mailbox_id == mailbox_id,
            MailMessage.internet_message_id == internet_message_id,
        )
        return self.session.scalar(query)

    def get_by_mailbox_and_source_uid(self, mailbox_id: str, source_uid: int) -> MailMessage | None:
        query = select(MailMessage).where(
            MailMessage.mailbox_id == mailbox_id,
            MailMessage.source_uid == source_uid,
        )
        return self.session.scalar(query)

    def list_by_mailbox_and_internet_ids(
        self,
        mailbox_id: str,
        internet_message_ids: list[str],
    ) -> list[MailMessage]:
        if not internet_message_ids:
            return []
        query = select(MailMessage).where(
            MailMessage.mailbox_id == mailbox_id,
            MailMessage.internet_message_id.in_(internet_message_ids),
        )
        return list(self.session.scalars(query))

    def list_for_thread(self, thread_id: str) -> list[MailMessage]:
        query = select(MailMessage).where(MailMessage.thread_id == thread_id).order_by(MailMessage.created_at)
        return list(self.session.scalars(query))

    def list_for_mailbox(self, mailbox_id: str, *, limit: int = 50) -> list[MailMessage]:
        query = (
            select(MailMessage)
            .where(MailMessage.mailbox_id == mailbox_id)
            .order_by(MailMessage.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(query))

    def count_unread_for_mailbox(self, mailbox_id: str) -> int:
        from sqlalchemy import func as sqlfunc
        result = self.session.execute(
            select(sqlfunc.count()).select_from(MailMessage).where(
                MailMessage.mailbox_id == mailbox_id,
                MailMessage.is_read.is_(False),
            )
        )
        return result.scalar_one()

    def search(
        self,
        query: str,
        *,
        organization_id: str | None = None,
        mailbox_id: str | None = None,
        direction: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> tuple[int, list[MailMessage]]:
        per_page = min(per_page, 100)
        offset = (page - 1) * per_page

        base = []
        if organization_id is not None:
            base.append(MailMessage.organization_id == organization_id)
        if mailbox_id is not None:
            base.append(MailMessage.mailbox_id == mailbox_id)
        if direction is not None:
            base.append(MailMessage.direction == direction)
        if date_from is not None:
            base.append(MailMessage.created_at >= date_from)
        if date_to is not None:
            base.append(MailMessage.created_at <= date_to)

        dialect = _dialect_name(self.session)
        if dialect == "postgresql":
            # Weighted: subject (A) > from_address (B) > body (C)
            tsvec = (
                func.setweight(
                    func.to_tsvector("english", func.coalesce(MailMessage.subject, "")), "A"
                ).op("||")(
                    func.setweight(
                        func.to_tsvector("english", func.coalesce(MailMessage.from_address, "")), "B"
                    )
                ).op("||")(
                    func.setweight(
                        func.to_tsvector("english", func.coalesce(MailMessage.text_body, "")), "C"
                    )
                )
            )
            tsquery = func.websearch_to_tsquery("english", query)
            search_cond = tsvec.op("@@")(tsquery)
            rank_expr = func.ts_rank_cd(tsvec, tsquery)
            count_stmt = select(func.count()).select_from(MailMessage).where(*base, search_cond)
            results_stmt = (
                select(MailMessage)
                .where(*base, search_cond)
                .order_by(rank_expr.desc(), MailMessage.created_at.desc())
                .offset(offset)
                .limit(per_page)
            )
        else:
            pattern = f"%{query}%"
            search_cond = or_(
                MailMessage.subject.ilike(pattern),
                MailMessage.from_address.ilike(pattern),
                MailMessage.text_body.ilike(pattern),
            )
            count_stmt = select(func.count()).select_from(MailMessage).where(*base, search_cond)
            results_stmt = (
                select(MailMessage)
                .where(*base, search_cond)
                .order_by(MailMessage.created_at.desc())
                .offset(offset)
                .limit(per_page)
            )

        total = self.session.scalar(count_stmt) or 0
        messages = list(self.session.scalars(results_stmt))
        return total, messages


class AttachmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, attachment: MailAttachment) -> MailAttachment:
        self.session.add(attachment)
        self.session.flush()
        return attachment

    def get(self, attachment_id: str) -> MailAttachment | None:
        return self.session.get(MailAttachment, attachment_id)

    def list_for_message(self, message_id: str) -> list[MailAttachment]:
        query = select(MailAttachment).where(MailAttachment.message_id == message_id).order_by(MailAttachment.created_at)
        return list(self.session.scalars(query))

    def list_for_draft(self, draft_id: str) -> list[MailAttachment]:
        query = select(MailAttachment).where(MailAttachment.draft_id == draft_id).order_by(MailAttachment.created_at)
        return list(self.session.scalars(query))

    def delete(self, attachment: MailAttachment) -> None:
        self.session.delete(attachment)


class WebhookRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, webhook: Webhook) -> Webhook:
        self.session.add(webhook)
        self.session.flush()
        return webhook

    def get(self, webhook_id: str) -> Webhook | None:
        return self.session.get(Webhook, webhook_id)

    def list_for_organization(self, organization_id: str | None) -> list[Webhook]:
        query = select(Webhook).order_by(Webhook.created_at.desc())
        if organization_id is not None:
            query = query.where(Webhook.organization_id == organization_id)
        return list(self.session.scalars(query))

    def list_active_for_mailbox(self, organization_id: str, mailbox_id: str) -> list[Webhook]:
        """Return active webhooks that match this mailbox (mailbox-specific or org-wide)."""
        from sqlalchemy import or_
        query = select(Webhook).where(
            Webhook.organization_id == organization_id,
            Webhook.is_active.is_(True),
            or_(Webhook.mailbox_id == mailbox_id, Webhook.mailbox_id.is_(None)),
        )
        return list(self.session.scalars(query))

    def delete(self, webhook: Webhook) -> None:
        self.session.delete(webhook)


class OutboundApprovalRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, approval: OutboundApproval) -> OutboundApproval:
        self.session.add(approval)
        self.session.flush()
        return approval

    def get(self, approval_id: str) -> OutboundApproval | None:
        return self.session.get(OutboundApproval, approval_id)

    def get_pending_for_draft(self, draft_id: str) -> OutboundApproval | None:
        query = select(OutboundApproval).where(
            OutboundApproval.draft_id == draft_id,
            OutboundApproval.status == ApprovalStatus.pending.value,
        )
        return self.session.scalar(query)

    def list_for_organization(
        self,
        organization_id: str,
        *,
        status: str | None = None,
        agent_id: str | None = None,
        mailbox_id: str | None = None,
    ) -> list[OutboundApproval]:
        query = (
            select(OutboundApproval)
            .where(OutboundApproval.organization_id == organization_id)
            .order_by(OutboundApproval.created_at.desc())
        )
        if status is not None:
            query = query.where(OutboundApproval.status == status)
        if agent_id is not None:
            query = query.where(OutboundApproval.agent_id == agent_id)
        if mailbox_id is not None:
            query = query.where(OutboundApproval.mailbox_id == mailbox_id)
        return list(self.session.scalars(query))
