# Cosmic Mail Architecture

This document explains how Cosmic Mail is structured today, what sits inside the product boundary, what is delegated to the mail engine, and where future work should go.

## 1. System Intent

Cosmic Mail is an agent-first email platform.

The product should let operators and developers:

- onboard organizations
- link domains
- provision inboxes
- create agent identities with prompts, personas, signatures, and approval policies
- link inboxes to agents
- send and receive real email
- normalize mail into product-owned threads and messages
- queue agent outbound for human approval before delivery
- push mail events to external systems via webhooks
- operate the system through APIs first

The system is intentionally not designed as:

- a generic end-user webmail client
- a replacement for a mail server's protocol implementation
- a thin wrapper around a managed provider-specific abstraction

## 2. High-Level Shape

Cosmic Mail is split into two layers:

1. Product layer
- Python / FastAPI application
- product-owned models
- orchestration logic
- operator console
- sync worker

2. Mail-engine layer
- Apache James
- SMTP, IMAP, mailbox storage, protocol correctness
- WebAdmin provisioning

The product layer owns the business model.
The mail engine owns low-level mail protocol behavior.

## 3. Architectural Principle

The central architectural decision is this:

Cosmic Mail should expose its own stable model:

- `Organization`
- `Domain`
- `MailboxIdentity`
- `AgentProfile`
- `AgentMailboxLink`
- `MailThread`
- `MailMessage`
- `MailDraft`
- `MailAttachment`
- `OutboundApproval`
- `Webhook`

It should not expose Apache James internals directly as the product API.

That keeps us free to:

- change internal mail engine details later
- keep business logic in Python
- build agent-native abstractions without being boxed in by server internals

## 4. Major Components

### 4.1 FastAPI App

Entry point:

- `cosmic_mail/main.py`

Responsibilities:

- application startup and shutdown
- dependency wiring
- health and readiness endpoints
- static operator console mounting
- sync worker lifecycle

### 4.2 API Layer

Path:

- `cosmic_mail/api`

Responsibilities:

- request authentication
- org-scoped authorization
- route definitions
- dependency injection into service layer

Important route groups:

- organizations
- domains
- agents (including avatar and signature-graphic upload/serve)
- mailboxes
- drafts
- threads (including reply-to-thread and mark-message-read)
- attachments
- approvals
- webhooks
- system

### 4.3 Domain Layer

Path:

- `cosmic_mail/domain`

Responsibilities:

- SQLAlchemy models
- repository access
- Pydantic request/response schemas
- shared validation helpers

This is the product-owned persistence and schema boundary.

### 4.4 Service Layer

Path:

- `cosmic_mail/services`

Responsibilities:

- business logic
- orchestration between DB and transport layers
- domain onboarding
- mailbox provisioning
- agent lifecycle
- draft send flow with approval queue interception
- inbound sync and attachment extraction
- sync worker behavior
- webhook dispatch

Key services:

- `organizations.py`
- `api_keys.py`
- `domains.py`
- `mailboxes.py`
- `agents.py`
- `conversations.py`
- `inbound.py`
- `outbound.py`
- `webhooks.py`
- `sync_manager.py`
- `james.py`

### 4.5 Operator Console

Path:

- `cosmic_mail/web/static`

Responsibilities:

- operator-facing control surface
- organization and access workflows
- domain onboarding and deliverability controls
- inbox provisioning
- agent management with approval mode toggle and avatar / signature-graphic uploads
- conversation inspection and reply
- approval queue — filter tabs, detail pane, edit / approve / reject actions
- webhook registration and management

It is intentionally a thin client over the public API.

### 4.6 Infrastructure

Paths:

- `infra/docker-compose.production.yml`
- `infra/james/conf`
- `infra/nginx`

Responsibilities:

- application container
- Postgres runtime
- Apache James runtime
- James configuration owned by the product
- HTTP reverse-proxy entrypoint

## 5. Data Model

### 5.1 Core Entities

`Organization`
- tenant boundary for most product data

`OrganizationApiKey`
- scoped API access for operators, workers, or integrations

`Domain`
- a linked sending/receiving domain
- stores generated deliverability settings and DNS posture
- owns DKIM key material per selector

`MailboxIdentity`
- a provisioned email address under a domain
- stores sync posture, quota, and encrypted credentials

`AgentProfile`
- the agent's business identity
- prompt, persona, signature, title, status
- `approval_required: bool` — when true, all outbound drafts are queued before delivery
- `avatar_url` and `signature_graphic_url` — served from the product API

`AgentMailboxLink`
- many-to-many relation between agents and inboxes
- supports labels and a primary mailbox

`MailThread`
- normalized conversation grouping for a mailbox

`MailMessage`
- normalized inbound or outbound message record
- tracks read state

`MailDraft`
- explicit send pipeline state before delivery
- status lifecycle: `draft → pending_approval → sent / failed`
  - or on rejection: `pending_approval → draft` (editable again)

`MailAttachment`
- extracted attachment records linked to a message
- content stored in the product database or on disk

`OutboundApproval`
- created when a draft send is intercepted because the agent has `approval_required`
- status: `pending → approved` or `pending → rejected`
- stores optional `reviewer_note` and `reviewed_at` timestamp
- draft is editable while the approval is in `pending` state
- on approve: immediately executes the outbound send
- on reject: resets draft to `draft` state for editing

`Webhook`
- HTTP endpoint registered by an org to receive mail events
- stores URL, enabled state, and secret for HMAC signature verification

### 5.2 Why Threads and Messages Are Product-Owned

We do not want the product to depend entirely on whatever thread representation the underlying mail engine does or does not provide.

Owning the thread/message model lets us:

- attach agent workflows later
- keep consistent API responses
- store product-specific metadata
- enforce our own draft / send / sync semantics
- queue and inspect outbound before delivery

## 6. Key Flows

### 6.1 Domain Onboarding

1. Operator creates a domain under an organization.
2. Product generates DNS records (MX, SPF, DKIM, DMARC).
3. Product provisions the domain in the mail engine.
4. Operator publishes DNS records externally.
5. Product verifies DNS and marks the domain active.
6. Operator can rotate DKIM selector and key material at any time.

### 6.2 Mailbox Provisioning

1. Operator creates a mailbox under an active domain.
2. Product provisions the mailbox in Apache James.
3. Product stores credentials securely.
4. Product records quota and sync state.

### 6.3 Agent Provisioning

1. Operator creates an agent profile.
2. Operator sets prompt, signature, and default domain.
3. Operator links one or more inboxes to the agent.
4. One mailbox can be marked primary.
5. Operator optionally uploads avatar and signature graphic.
6. Operator optionally enables `approval_required` for human review of all outbound.

### 6.4 Outbound Mail

1. Client creates a draft through the API.
2. Product stores draft state.
3. Client triggers send.
4. If the linked agent has `approval_required`:
   - Draft status is set to `pending_approval`.
   - An `OutboundApproval` record is created.
   - Send is deferred. Route returns `queued_for_approval: true`.
5. Otherwise, product loads mailbox credentials and sends through outbound transport.
6. Outbound is DKIM-signed using the sending domain's active key.
7. Signature logos are embedded as CID inline images.
8. Product persists normalized outbound message and thread updates.
9. Registered webhooks are dispatched with the event payload.

### 6.5 Approval Queue

1. Human operator opens the Approvals section of the operator console.
2. Pending approvals are listed with sender, recipient, and subject.
3. Operator opens a detail pane to preview the full email body.
4. Operator can optionally edit subject, body, and recipients before deciding.
5. Approve: product calls `_execute_send` directly, bypassing the `approval_required` check, marks approval `approved`.
6. Reject: draft reverts to `draft` status, approval is marked `rejected`, optional note is stored.

### 6.6 Inbound Mail

1. Mail arrives at Apache James.
2. Inbox becomes readable over IMAP.
3. Product sync worker or manual sync fetches new messages.
4. Product normalizes them into threads and messages.
5. Attachments are extracted and stored per message.
6. API and operator console expose the normalized state.
7. Registered webhooks are dispatched with the event payload.

### 6.7 Webhooks

1. Operator registers a webhook URL with an optional secret.
2. On inbound sync or outbound send, product fires an HTTP POST to each active webhook.
3. Payload includes org ID, event type, thread and message context.
4. Request includes an `X-Cosmic-Signature` header derived from the webhook secret for verification.

## 7. Runtime Topology

### 7.1 Local Development

Common modes:

- SQLite + `noop` engine for API work
- Postgres + James for integration work

This makes it possible to work on product logic without always needing a live mail engine.

### 7.2 Production Runtime

Current deployment shape:

- `nginx` or host reverse proxy
- `cosmic-mail` app container
- `postgres` container
- `james` container

Public exposure today should generally be:

- `80` / `443` for the control plane
- `25` for public inbound SMTP

Keep these internal unless intentionally exposed:

- James WebAdmin
- IMAP
- internal app-to-James transport paths

## 8. Extension Points

The design intentionally leaves seams for future changes.

### 8.1 Mail Engine Abstraction

Path:

- `cosmic_mail/services/mail_engine.py`

This allows the product to provision against different backends later.

### 8.2 Outbound Transport Abstraction

Path:

- `cosmic_mail/services/outbound.py`

This lets us evolve from direct SMTP toward stricter submission or relay-backed delivery.
Inline image CID embedding and DKIM signing are handled here.

### 8.3 Inbound Transport Abstraction

Path:

- `cosmic_mail/services/inbound.py`

This lets us change sync strategy later:

- IMAP polling
- IMAP IDLE
- event bridge
- JMAP or other integration

### 8.4 Approval Queue

Path:

- `cosmic_mail/services/conversations.py`
- `cosmic_mail/api/routes/approvals.py`

The approval interception point is inside `send_draft`. Extracting `_execute_send` as a private method means `approve_outbound` can trigger the real send without re-entering the approval check. New review policies can be added without changing the route layer.

### 8.5 Webhook Dispatch

Path:

- `cosmic_mail/services/webhooks.py`

Webhook dispatch is invoked from the sync flow and the outbound send flow. Additional event types can be added by calling the dispatch helper from any service.

## 9. Current Gaps

The biggest remaining architecture gaps are not CRUD issues. They are production-email concerns:

- public deliverability validation
- bounce and complaint ingestion
- alias / forwarding layer
- stronger abuse controls
- better event-driven inbound processing (IMAP IDLE or event bridge)
- migrations / backup / restore hardening

## 10. Non-Goals

At the current stage, we are not optimizing for:

- polished end-user mailbox UX
- deep webmail features
- replacing the mail engine with a Python SMTP server
- provider-specific lock-in abstractions

## 11. How To Read The Codebase

Recommended order:

1. `README.md`
2. `ARCHITECTURE.md`
3. `cosmic_mail/main.py`
4. `cosmic_mail/domain/models.py`
5. `cosmic_mail/services/*`
6. `cosmic_mail/api/routes/*`
7. `infra/docker-compose.production.yml`
8. `infra/james/conf/*`

That order gives enough system context before implementation detail.
