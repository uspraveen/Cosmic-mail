# Cosmic Mail Architecture

This document explains how Cosmic Mail is structured today, what sits inside the product boundary, what is delegated to the mail engine, and where future work should go.

## 1. System Intent

Cosmic Mail is an agent-first email platform.

The product should let operators and developers:

- onboard organizations
- link domains
- provision inboxes
- create agent identities
- link inboxes to agents
- send and receive real email
- normalize mail into product-owned threads and messages
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
- agents
- mailboxes
- drafts
- threads
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
- draft send flow
- inbound sync
- sync worker behavior

Key services:

- `organizations.py`
- `api_keys.py`
- `domains.py`
- `mailboxes.py`
- `agents.py`
- `conversations.py`
- `inbound.py`
- `outbound.py`
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
- agent management
- conversation inspection

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

`MailboxIdentity`
- a provisioned email address under a domain
- stores sync posture, quota, and encrypted credentials

`AgentProfile`
- the agent’s business identity
- prompt, persona, signature, title, status

`AgentMailboxLink`
- many-to-many relation between agents and inboxes
- supports labels and a primary mailbox

`MailThread`
- normalized conversation grouping for a mailbox

`MailMessage`
- normalized inbound or outbound message record

`MailDraft`
- explicit send pipeline state before delivery

### 5.2 Why Threads and Messages Are Product-Owned

We do not want the product to depend entirely on whatever thread representation the underlying mail engine does or does not provide.

Owning the thread/message model lets us:

- attach agent workflows later
- keep consistent API responses
- store product-specific metadata
- enforce our own draft / send / sync semantics

## 6. Key Flows

### 6.1 Domain Onboarding

1. Operator creates a domain under an organization.
2. Product generates DNS records.
3. Product provisions the domain in the mail engine.
4. Operator publishes DNS records externally.
5. Product verifies DNS and marks the domain active.

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

### 6.4 Outbound Mail

1. Client creates a draft through the API.
2. Product stores draft state.
3. Client triggers send.
4. Product loads mailbox credentials.
5. Product sends through the outbound transport.
6. Product persists normalized outbound message and thread updates.

### 6.5 Inbound Mail

1. Mail arrives at Apache James.
2. Inbox becomes readable over IMAP.
3. Product sync worker or manual sync fetches new messages.
4. Product normalizes them into threads and messages.
5. API and operator console expose the normalized state.

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

### 8.3 Inbound Transport Abstraction

Path:

- `cosmic_mail/services/inbound.py`

This lets us change sync strategy later:

- IMAP polling
- IMAP IDLE
- event bridge
- JMAP or other integration

## 9. Current Gaps

The biggest remaining architecture gaps are not CRUD issues. They are production-email concerns:

- public deliverability validation
- outbound DKIM signing integration
- bounce and complaint ingestion
- alias / forwarding layer
- stronger abuse controls
- better event-driven inbound processing
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
