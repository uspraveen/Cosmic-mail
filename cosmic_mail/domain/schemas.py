from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cosmic_mail.domain.models import AgentStatus, DomainStatus, DraftStatus, MailboxStatus, MessageDirection, WebhookEventType


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str | None = Field(default=None, min_length=2, max_length=120)


class OrganizationRead(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationApiKeyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class OrganizationApiKeyRead(BaseModel):
    id: str
    organization_id: str
    name: str
    key_prefix: str
    last_used_at: datetime | None
    created_at: datetime
    revoked_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class OrganizationApiKeyCreateResult(BaseModel):
    api_key: OrganizationApiKeyRead
    plaintext_key: str


class DNSRecord(BaseModel):
    type: Literal["MX", "TXT"]
    host: str
    value: str
    priority: int | None = None
    ttl: int


class DomainCreate(BaseModel):
    organization_id: str
    domain: str = Field(min_length=3, max_length=253)


class DomainRead(BaseModel):
    id: str
    organization_id: str
    name: str
    status: DomainStatus
    james_domain_created: bool
    created_at: datetime
    updated_at: datetime
    dns_records: list[DNSRecord]


class DomainVerificationCheck(BaseModel):
    type: Literal["MX", "TXT"]
    host: str
    expected: str
    observed: list[str]
    matched: bool


class DomainVerificationRead(BaseModel):
    domain_id: str
    status: DomainStatus
    all_records_present: bool
    james_domain_created: bool
    checks: list[DomainVerificationCheck]


class MailServiceEndpointRead(BaseModel):
    host: str
    port: int
    security: Literal["none", "starttls", "ssl"]
    auth_required: bool


class DomainConnectionProfileRead(BaseModel):
    submission: MailServiceEndpointRead
    imap: MailServiceEndpointRead


class DomainDeliverabilityRead(BaseModel):
    domain_id: str
    status: DomainStatus
    james_domain_created: bool
    mx_target: str
    mx_priority: int
    spf_value: str
    dmarc_value: str
    dkim_selector: str
    dkim_public_key: str
    dns_records: list[DNSRecord]
    connection_profile: DomainConnectionProfileRead


class DomainDeliverabilityUpdate(BaseModel):
    spf_value: str | None = Field(default=None, max_length=512)
    dmarc_policy: Literal["none", "quarantine", "reject"] | None = None
    dmarc_subdomain_policy: Literal["none", "quarantine", "reject"] | None = None
    dmarc_aggregate_report_email: str | None = Field(default=None, max_length=320)


class DomainDkimRotate(BaseModel):
    selector: str | None = Field(default=None, min_length=1, max_length=64)


class MailboxCreate(BaseModel):
    domain_id: str
    local_part: str = Field(min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=12, max_length=256)
    quota_mb: int | None = Field(default=None, ge=1, le=1024 * 100)
    quota_messages: int | None = Field(default=None, ge=1, le=10_000_000)


class MailboxRead(BaseModel):
    id: str
    organization_id: str
    domain_id: str
    local_part: str
    address: str
    display_name: str | None
    status: MailboxStatus
    james_user_created: bool
    quota_mb: int
    quota_messages: int
    inbound_sync_enabled: bool
    last_synced_at: datetime | None
    last_sync_error: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MailboxCreateResult(MailboxRead):
    issued_password: str | None = None


class AttachmentRead(BaseModel):
    id: str
    message_id: str | None
    draft_id: str | None
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentCreate(BaseModel):
    organization_id: str
    name: str = Field(min_length=2, max_length=255)
    slug: str | None = Field(default=None, min_length=2, max_length=120)
    title: str | None = Field(default=None, max_length=255)
    persona_summary: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, max_length=8000)
    signature: str | None = Field(default=None, max_length=2000)
    default_domain_id: str | None = None
    accent_color: str | None = Field(default=None, max_length=24)
    avatar_url: str | None = Field(default=None, max_length=512)


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    slug: str | None = Field(default=None, min_length=2, max_length=120)
    title: str | None = Field(default=None, max_length=255)
    persona_summary: str | None = Field(default=None, max_length=2000)
    system_prompt: str | None = Field(default=None, max_length=8000)
    signature: str | None = Field(default=None, max_length=2000)
    default_domain_id: str | None = None
    accent_color: str | None = Field(default=None, max_length=24)
    avatar_url: str | None = Field(default=None, max_length=512)
    status: AgentStatus | None = None


class AgentMailboxLinkCreate(BaseModel):
    mailbox_id: str
    label: str | None = Field(default=None, max_length=255)
    is_primary: bool = False


class AgentMailboxBindingRead(BaseModel):
    mailbox_id: str
    address: str
    display_name: str | None
    domain_id: str
    domain_name: str
    label: str | None
    is_primary: bool
    inbound_sync_enabled: bool
    last_synced_at: datetime | None
    last_sync_error: str | None


class AgentRead(BaseModel):
    id: str
    organization_id: str
    default_domain_id: str | None
    default_domain_name: str | None
    name: str
    slug: str
    title: str | None
    persona_summary: str | None
    system_prompt: str | None
    signature: str | None
    accent_color: str
    avatar_url: str | None
    status: AgentStatus
    created_at: datetime
    updated_at: datetime
    mailboxes: list[AgentMailboxBindingRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class MailContact(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    name: str | None = Field(default=None, max_length=255)


class MailDraftCreate(BaseModel):
    mailbox_id: str
    thread_id: str | None = None
    reply_to_message_id: str | None = Field(default=None, max_length=998)
    subject: str = Field(min_length=1, max_length=998)
    to_recipients: list[MailContact] = Field(min_length=1)
    cc_recipients: list[MailContact] = Field(default_factory=list)
    bcc_recipients: list[MailContact] = Field(default_factory=list)
    text_body: str | None = None
    html_body: str | None = None


class MailDraftRead(BaseModel):
    id: str
    organization_id: str
    mailbox_id: str
    thread_id: str | None
    reply_to_message_id: str | None
    subject: str
    to_recipients: list[MailContact]
    cc_recipients: list[MailContact]
    bcc_recipients: list[MailContact]
    text_body: str | None
    html_body: str | None
    status: DraftStatus
    sent_message_id: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    sent_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class MailThreadRead(BaseModel):
    id: str
    organization_id: str
    mailbox_id: str
    subject: str
    normalized_subject: str
    snippet: str | None
    message_count: int
    last_message_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MailMessageRead(BaseModel):
    id: str
    organization_id: str
    mailbox_id: str
    thread_id: str
    draft_id: str | None
    internet_message_id: str
    source_uid: int | None
    direction: MessageDirection
    folder_name: str
    subject: str
    normalized_subject: str
    in_reply_to: str | None
    references: list[str]
    from_name: str | None
    from_address: str
    to_recipients: list[MailContact]
    cc_recipients: list[MailContact]
    bcc_recipients: list[MailContact]
    reply_to_recipients: list[MailContact]
    text_body: str | None
    html_body: str | None
    preview_text: str | None
    is_read: bool
    sent_at: datetime | None
    received_at: datetime | None
    created_at: datetime
    attachments: list[AttachmentRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ThreadReplyCreate(BaseModel):
    mailbox_id: str
    text_body: str | None = None
    html_body: str | None = None
    to_recipients: list[MailContact] | None = None
    cc_recipients: list[MailContact] = Field(default_factory=list)


class WebhookCreate(BaseModel):
    mailbox_id: str | None = None
    event_type: WebhookEventType = WebhookEventType.all
    url: str = Field(min_length=8, max_length=2048)
    secret: str | None = Field(default=None, max_length=256)


class WebhookRead(BaseModel):
    id: str
    organization_id: str
    mailbox_id: str | None
    event_type: WebhookEventType
    url: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MailDraftSendResult(BaseModel):
    draft: MailDraftRead
    thread: MailThreadRead
    message: MailMessageRead


class MailboxSyncResult(BaseModel):
    mailbox_id: str
    imported_count: int
    skipped_count: int
    last_inbound_uid: int
    synced_at: datetime


class MailboxSyncPolicyRead(BaseModel):
    mailbox_id: str
    enabled: bool
    last_synced_at: datetime | None
    last_sync_error: str | None


class MailboxSyncPolicyUpdate(BaseModel):
    enabled: bool


class SyncWorkerStatusRead(BaseModel):
    enabled: bool
    running: bool
    interval_seconds: int
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_run_mailbox_count: int
    last_run_imported_count: int
    last_run_failed_count: int
    last_error: str | None


class SyncRunResult(BaseModel):
    organization_id: str | None = None
    mailbox_count: int
    synced_mailboxes: int
    failed_mailboxes: int
    imported_count: int
    skipped_count: int
    completed_at: datetime
    errors: list[str]


class AuthContextRead(BaseModel):
    is_admin: bool
    organization_id: str | None
    api_key_id: str | None
    api_key_name: str | None


class HealthRead(BaseModel):
    status: str


class ReadyCheck(BaseModel):
    status: str
    details: dict[str, str]
