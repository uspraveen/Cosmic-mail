# Cosmic Mail

Cosmic Mail is an agent-first email platform.

The goal is not to build a generic webmail clone. The goal is to build the best email infrastructure and control plane for AI agents:

- create and manage many agent-owned email identities
- onboard customer or internal domains
- provision inboxes safely
- send and receive real email through a real mail engine
- keep a product-owned model for agents, threads, drafts, and policies
- expose everything through APIs first
- keep the operator experience good enough to run the system day to day

Today, this repo contains a working control-plane checkpoint built in Python, with Apache James used as the mail-engine runtime underneath.

For the system-level design, read [ARCHITECTURE.md](./ARCHITECTURE.md).

## Project Status

This is beyond a prototype, but not yet complete public-internet email infrastructure.

What is built:

- organizations and org-scoped API keys
- agent profiles with prompts, signatures, personas, default domains, mailbox links, and approval mode
- agent avatar and signature-graphic uploads with magic-byte content validation (JPEG, PNG, GIF, WebP only)
- domain onboarding with generated `MX`, `SPF`, `DKIM`, and `DMARC`
- DNS verification and domain deliverability management
- DKIM key rotation per domain
- mailbox provisioning into Apache James
- encrypted mailbox credential storage
- outbound send flow through pluggable SMTP-style transport
- outbound DKIM signing at the transport layer
- externally-hosted signature logos embedded via `<img src>` in outbound HTML (compatible with Gmail image proxy)
- bounce auto-detection on inbound sync (RFC 3463 DSN parsing + heuristic fallback), stored as `is_bounce` / `bounce_type` on messages
- full-text search across threads and messages (Postgres `tsvector` weighted ranking; SQLite ILIKE fallback for local dev) with pagination
- external deliverability validation — public DNS resolver, MX-to-IP resolution, DNSBL blacklist checks (Spamhaus, SpamCop, SORBS)
- inbound sync through pluggable IMAP-style transport
- attachment handling for inbound and outbound messages
- product-owned threads, messages, drafts, and approval records
- reply-to-thread shorthand with full thread context
- mark-message-read tracking
- approval queue for agent outbound — agents in approval mode queue drafts for human review before send
- full approval queue management endpoints (list, review, edit, approve, reject)
- webhooks — register HTTP endpoints to receive events on mail activity
- background sync worker and manual sync controls
- a built-in operator console served from `/`
- Linux deployment artifacts for `Cosmic Mail + Postgres + Apache James`
- automated tests and Linux smoke coverage
- API key authentication required on all `/v1` endpoints including image-serving routes
- rate limiting — 120 requests per minute per IP + key prefix, 429 on breach
- security headers on every response (`X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security` when behind HTTPS)
- configurable CORS middleware
- startup enforcement — insecure default `secret_key` triggers a logged warning at boot
- email address format validation on draft recipients
- pagination (`page` / `per_page`) on all list endpoints
- outbound filter rules — per-agent and per-inbox whitelist/blacklist with `exact`, `domain`, `subdomain`, and `wildcard` pattern types; blacklists always win; whitelist gates apply independently per scope; enforcement at send time raises a structured error before transport; pre-flight check endpoint for draft validation

What is not finished:

- real external inbox-placement validation with Gmail / Outlook / enterprise providers (DKIM/SPF/DMARC and DNSBL checks are in place; automated placement testing against real inboxes is not)
- bounce / complaint ingestion pipeline — bounce detection on inbound sync is done (`is_bounce` / `bounce_type` stored per message); acting on bounces (suppression lists, auto-disable bad addresses, alerting) is not
- alias and forwarding controls
- per-organization rate quotas and abuse shaping for hostile multi-tenant use (global rate limiting is in place; per-tenant enforcement is not)
- JMAP-based identity or event integration

Short version:

- ready for controlled development, staging, and internal operator use
- not yet ready to claim "full public-email SaaS maturity"

## Product Vision

Cosmic Mail should let a developer or operator do the following without touching raw mail-server internals:

1. create an organization
2. link a domain
3. publish DNS records
4. verify the domain
5. create inboxes
6. create agent profiles
7. attach one or more inboxes to each agent
8. send and receive email through those inboxes
9. inspect threads and messages through a product-owned API
10. manage access and sync behavior safely
11. put agents into approval mode so human operators can review outbound before delivery
12. register webhooks to push mail events into external systems

This is why the project keeps its own domain model instead of exposing Apache James directly.

## Core Model

The current product model is:

- `Organization`
- `OrganizationApiKey`
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
- `OutboundFilterRule`

Important relationship summary:

- one organization owns many domains
- one domain owns many inboxes
- one organization owns many agents
- one agent can link to many inboxes
- one inbox can be linked to many agents
- one inbox owns many threads
- one thread owns many messages
- one message owns many attachments
- one draft in approval mode produces one `OutboundApproval` record
- one organization owns many webhooks
- one agent or one inbox can own many `OutboundFilterRule` records (scoped separately)
- filter rules are evaluated at send time: blacklists across both scopes win first, then whitelist gates apply per scope

## Architecture

For the full breakdown, see [ARCHITECTURE.md](./ARCHITECTURE.md).

The system is intentionally split into two layers.

Application layer:

- `cosmic_mail`
- FastAPI control plane
- product-owned models and orchestration
- domain onboarding logic
- thread / message persistence
- sync worker
- operator console

Mail-engine layer:

- Apache James
- SMTP / IMAP / storage / mailbox protocol correctness
- WebAdmin provisioning

This split is deliberate. Our product surface must stay stable even if the underlying mail engine changes later.

### Why Apache James right now

Apache James is the current reference engine because it is mature, standards-oriented, and permissively licensed under `Apache-2.0`.

We are not trying to win by rewriting a mail server from scratch in Python. We are trying to win by building the best agent-email product on top of a real mail substrate.

## Repository Layout

Key directories:

- `cosmic_mail/main.py`
  - app wiring, lifespan, health, readiness, static operator console mounting
- `cosmic_mail/api`
  - authentication, dependency wiring, HTTP routes
- `cosmic_mail/domain`
  - SQLAlchemy models, repositories, Pydantic schemas, validation
- `cosmic_mail/services`
  - business logic for organizations, agents, domains, inboxes, conversations, transport, sync, webhooks, and filter rules
- `cosmic_mail/web/static`
  - operator console frontend
- `infra/docker-compose.production.yml`
  - production compose stack
- `infra/james/conf`
  - James configuration owned by this product
- `scripts`
  - smoke and integration scripts, including Linux testing
- `tests`
  - API and UI smoke coverage

## Main Flows

### 1. Organization and Access

- create an organization with the admin API key
- mint org-scoped API keys
- use org keys for normal operator or worker access

### 2. Domain Onboarding

- create a domain under an organization
- generate DNS records
- verify DNS
- inspect / update deliverability settings
- rotate DKIM selector and key material

### 3. Inbox Provisioning

- create a mailbox under an active domain
- provision the user in Apache James
- configure quota and mailbox bootstrap
- store issued credentials securely

### 4. Agent Provisioning

- create an agent profile
- set prompt, signature, persona, title, and default domain
- link one or more inboxes to the agent
- mark a primary inbox when needed
- optionally upload an agent avatar and a signature graphic
- optionally enable `approval_required` to queue all outbound for human review

### 5. Mail Flow

- create a draft
- send the draft through the configured outbound transport
- outbound is DKIM-signed per the sending domain's key material
- signature logos are embedded as externally-hosted `<img src>` URLs (renders correctly in Gmail and all major clients)
- sync inbound mail through IMAP
- normalize inbound and outbound mail into product-owned threads and messages
- attachments are extracted and stored against each message

### 6. Approval Queue

- agent is configured with `approval_required: true`
- all draft sends for that agent are intercepted before transport
- draft status moves to `pending_approval`
- an `OutboundApproval` record is created
- human operator inspects and optionally edits subject, body, and recipients
- operator approves → draft is sent immediately via the normal outbound flow
- operator rejects → draft reverts to editable `draft` state with an optional reviewer note
- the approval queue is surfaced in the operator console with filter tabs and a detail pane

### 7. Webhooks

- operator registers webhook endpoints per organization
- events are fired after inbound sync or outbound send
- payload includes thread and message context
- each webhook call includes a signature header for request verification

### 8. Outbound Filter Rules

- create whitelist or blacklist rules scoped to an agent or to a specific inbox
- four pattern types: `exact` (full address), `domain` (`@acme.com`), `subdomain` (`@*.acme.com` and `@acme.com`), `wildcard` (fnmatch glob, e.g. `*@*.acme.com`)
- precedence at send time: blacklists (across all scopes) are checked first and always win; then whitelist gates are applied independently per scope — if any scope has a whitelist, all recipients must match at least one rule in that scope
- enforcement happens before approval queuing — a blocked draft never enters the approval queue
- pre-flight check via `POST /v1/filter-rules/check` lets callers validate recipients before creating a draft
- rules are manageable per-agent and per-inbox from both the API and the operator console

## API Surface

All `/v1` routes require an API key. Use either:

- `X-API-Key: <key>`
- `Authorization: Bearer <key>`

Current API groups:

### Organizations

- `POST /v1/organizations`
- `GET /v1/organizations`
- `POST /v1/organizations/{organization_id}/api-keys`
- `GET /v1/organizations/{organization_id}/api-keys`
- `DELETE /v1/organizations/{organization_id}/api-keys/{api_key_id}`
- `POST /v1/organizations/{organization_id}/sync-mailboxes`

### Domains

- `POST /v1/domains`
- `GET /v1/domains` — supports `?page=&per_page=` (max 200)
- `POST /v1/domains/{domain_id}/verify-dns`
- `GET /v1/domains/{domain_id}/deliverability`
- `PATCH /v1/domains/{domain_id}/deliverability`
- `POST /v1/domains/{domain_id}/rotate-dkim`
- `GET /v1/domains/{domain_id}/deliverability/check` — live external DNS + DNSBL blacklist check via public resolver

### Agents

- `POST /v1/agents`
- `GET /v1/agents` — supports `?page=&per_page=` (max 200)
- `GET /v1/agents/{agent_id}`
- `PATCH /v1/agents/{agent_id}`
- `POST /v1/agents/{agent_id}/mailboxes`
- `DELETE /v1/agents/{agent_id}/mailboxes/{mailbox_id}`
- `POST /v1/agents/{agent_id}/avatar` — upload avatar image (JPEG / PNG / GIF / WebP; max `MAX_ATTACHMENT_SIZE_MB`)
- `GET /v1/agents/{agent_id}/avatar` — serve avatar image (requires auth)
- `POST /v1/agents/{agent_id}/signature-graphic` — upload signature logo (JPEG / PNG / GIF / WebP; max `MAX_ATTACHMENT_SIZE_MB`)
- `GET /v1/agents/{agent_id}/signature-graphic` — serve signature logo (requires auth)

### Mailboxes

- `POST /v1/mailboxes`
- `GET /v1/mailboxes` — supports `?page=&per_page=` (max 200)
- `GET /v1/mailboxes/{mailbox_id}/sync-policy`
- `PATCH /v1/mailboxes/{mailbox_id}/sync-policy`
- `POST /v1/mailboxes/{mailbox_id}/sync-inbox`

### Drafts and Conversations

- `POST /v1/drafts`
- `GET /v1/drafts`
- `POST /v1/drafts/{draft_id}/send` — returns `queued_for_approval: true` when agent is in approval mode
- `GET /v1/threads`
- `GET /v1/threads/{thread_id}`
- `GET /v1/threads/{thread_id}/messages`
- `POST /v1/threads/{thread_id}/reply` — reply shorthand with full thread context
- `PATCH /v1/threads/{thread_id}/messages/{message_id}/read` — mark message read

### Attachments

- `POST /v1/attachments/drafts/{draft_id}` — upload a file to a draft (multipart); attached automatically when the draft is sent
- `DELETE /v1/attachments/{attachment_id}` — remove an attachment from a draft before sending
- `GET /v1/messages/{message_id}/attachments` — list attachments on a received message
- `GET /v1/attachments/{attachment_id}/download` — download attachment content (draft or inbound)

### Approval Queue

- `GET /v1/approvals` — list with `status`, `agent_id`, `mailbox_id` filters
- `GET /v1/approvals/{approval_id}` — get single approval with full draft embedded
- `PATCH /v1/approvals/{approval_id}` — edit subject, body, or recipients before sending
- `POST /v1/approvals/{approval_id}/approve` — approve and immediately send
- `POST /v1/approvals/{approval_id}/reject` — reject with optional reviewer note

### Search

- `GET /v1/search/messages` — full-text search across messages (`q`, `mailbox_id`, `direction`, `date_from`, `date_to`, `page`, `per_page`)
- `GET /v1/search/threads` — full-text search across threads (`q`, `mailbox_id`, `date_from`, `date_to`, `page`, `per_page`)

### Webhooks

- `POST /v1/webhooks` — register a new webhook endpoint
- `GET /v1/webhooks` — list registered webhooks
- `GET /v1/webhooks/{webhook_id}` — get single webhook
- `PATCH /v1/webhooks/{webhook_id}` — update endpoint URL or enabled state
- `DELETE /v1/webhooks/{webhook_id}` — remove a webhook

### Filter Rules (Agent-scoped)

- `GET /v1/agents/{agent_id}/filter-rules` — list rules for an agent
- `POST /v1/agents/{agent_id}/filter-rules` — create a single rule
- `POST /v1/agents/{agent_id}/filter-rules/bulk` — bulk-create up to 100 rules
- `GET /v1/agents/{agent_id}/filter-rules/{rule_id}` — get a single rule
- `DELETE /v1/agents/{agent_id}/filter-rules/{rule_id}` — delete a rule

### Filter Rules (Inbox-scoped)

- `GET /v1/mailboxes/{mailbox_id}/filter-rules` — list rules for an inbox
- `POST /v1/mailboxes/{mailbox_id}/filter-rules` — create a single rule
- `POST /v1/mailboxes/{mailbox_id}/filter-rules/bulk` — bulk-create up to 100 rules
- `GET /v1/mailboxes/{mailbox_id}/filter-rules/{rule_id}` — get a single rule
- `DELETE /v1/mailboxes/{mailbox_id}/filter-rules/{rule_id}` — delete a rule

### Filter Rules (Utility)

- `POST /v1/filter-rules/check` — pre-flight check: test whether a set of recipients would be blocked by current rules before creating a draft; returns `passed` boolean and a `blocked` list with per-email reason, scope, and rule ID

### System

- `GET /v1/system/auth-context`
- `GET /v1/system/sync-worker`
- `POST /v1/system/sync-worker/run-once`
- `GET /health`
- `GET /ready`

## Operator Console

The built-in UI is served from:

- `/`
- `/app`

Current sections:

- `Overview`
- `Agents`
- `Domains`
- `Inboxes`
- `Conversations`
- `Approvals` — approval queue with filter tabs (Pending / Approved / Rejected / All) and split-pane detail view
- `Webhooks`
- `Access`

Filter rules in the console:

- "Filter rules" button on each row in the Agents table — opens a modal to manage that agent's rules
- "Filter rules" button on each row in the Inboxes table — opens a modal to manage that inbox's rules
- modal shows all active rules in a table with type, pattern, pattern type, label, and a delete button
- inline form inside the modal to add a new rule without leaving the page

Agent features in the console:

- create and edit agents with approval mode toggle
- upload avatar and signature graphic
- "approval mode" badge shown in agents table when `approval_required` is set
- orange pending badge on Approvals nav item when there are pending approvals

Frontend files:

- `cosmic_mail/web/static/index.html`
- `cosmic_mail/web/static/app.css`
- `cosmic_mail/web/static/app.js`
- `cosmic_mail/web/static/api.js`
- `cosmic_mail/web/static/state.js`
- `cosmic_mail/web/static/templates.js`

This console is an operator tool, not the final product UX for end customers.

## Local Development

### Quick start

Run the app:

```bash
uvicorn cosmic_mail.main:app --reload
```

The default development setup can run with:

- SQLite
- `noop` mail engine
- local admin API key

That lets you work on the control plane without a live James instance.

### Important environment variables

**Core**

- `COSMIC_MAIL_DATABASE_URL`
- `COSMIC_MAIL_ADMIN_API_KEY`
- `COSMIC_MAIL_SECRET_KEY` — **must be set to a strong random value in production**; the app logs a warning at startup if the default value is still in use
- `COSMIC_MAIL_MAIL_ENGINE_BACKEND`

**Mail engine (James)**

- `COSMIC_MAIL_JAMES_WEBADMIN_URL`
- `COSMIC_MAIL_JAMES_ADMIN_TOKEN`
- `COSMIC_MAIL_PUBLIC_MAIL_HOSTNAME`
- `COSMIC_MAIL_PUBLIC_SUBMISSION_HOSTNAME`
- `COSMIC_MAIL_PUBLIC_SUBMISSION_PORT`
- `COSMIC_MAIL_PUBLIC_SUBMISSION_USE_STARTTLS`
- `COSMIC_MAIL_PUBLIC_IMAP_HOSTNAME`
- `COSMIC_MAIL_PUBLIC_IMAP_PORT`
- `COSMIC_MAIL_PUBLIC_IMAP_USE_SSL`

**SMTP / IMAP transport**

- `COSMIC_MAIL_SMTP_HOST`
- `COSMIC_MAIL_SMTP_PORT`
- `COSMIC_MAIL_SMTP_USE_SSL`
- `COSMIC_MAIL_SMTP_USE_STARTTLS`
- `COSMIC_MAIL_SMTP_VALIDATE_CERTS`
- `COSMIC_MAIL_SMTP_AUTH_ENABLED`
- `COSMIC_MAIL_IMAP_HOST`
- `COSMIC_MAIL_IMAP_PORT`
- `COSMIC_MAIL_IMAP_USE_SSL`
- `COSMIC_MAIL_IMAP_USE_STARTTLS`
- `COSMIC_MAIL_IMAP_VALIDATE_CERTS`

**Sync worker**

- `COSMIC_MAIL_SYNC_WORKER_ENABLED`
- `COSMIC_MAIL_SYNC_WORKER_INTERVAL_SECONDS`
- `COSMIC_MAIL_SYNC_WORKER_BATCH_SIZE`

**Storage and security**

- `COSMIC_MAIL_STORAGE_PATH` — base path for avatar and signature-graphic uploads
- `COSMIC_MAIL_MAX_ATTACHMENT_SIZE_MB` — max upload size for images (default `25`)
- `COSMIC_MAIL_CORS_ALLOWED_ORIGINS` — JSON list of allowed CORS origins, e.g. `["https://app.example.com"]`; defaults to `["*"]` (open) for local dev
- `COSMIC_MAIL_RATE_LIMIT_REQUESTS_PER_MINUTE` — max API requests per minute per IP + key prefix (default `600`)

## Production Deployment

The Linux deployment path in this repo uses:

- `Dockerfile`
- `infra/docker-compose.production.yml`
- `infra/env.production.example`
- `infra/james/conf/*`

Typical flow:

```bash
cp infra/env.production.example .env
docker compose -f infra/docker-compose.production.yml --env-file .env up -d --build
```

The compose stack provisions:

- `postgres`
- `james`
- `cosmic-mail`

Current deployment assumptions:

- James WebAdmin stays internal
- IMAP stays internal unless you intentionally expose it
- public inbound SMTP is on `25`
- the app talks to James over internal SMTP / IMAP

## Testing and Verification

### Local tests

```bash
python -m pytest -q
python -m compileall -q cosmic_mail tests scripts
```

### Linux smoke with Blaxel

Required environment:

- `BL_API_KEY`
- `BL_WORKSPACE`

Run:

```bash
python scripts/blaxel_linux_smoke.py
```

What it covers:

- Linux test execution
- live James provisioning
- domain onboarding path
- mailbox provisioning
- SMTP send
- IMAP sync
- sandbox cleanup in `finally`

## Current Gaps

These are the biggest known gaps between the current checkpoint and a true public-email product:

- real external inbox-placement validation (automated testing against Gmail / Outlook / enterprise inboxes)
- DNS automation and production onboarding UX
- bounce / complaint action pipeline (detection is done; suppression lists and auto-disable are not)
- aliases and forwarding
- per-organization rate quotas and abuse shaping (global rate limiting is in place; per-tenant enforcement is not)
- Fernet key derivation upgrade (currently SHA-256 KDF; PBKDF2 migration would require a credential re-encryption pass)
- richer operator analytics and search
- migrations / backup / restore hardening

## Development Principles

This repo is being built with a few explicit rules:

- API first
- product-owned data model
- mail-engine abstraction under the product surface
- no dependency on a proprietary provider model like "pods"
- build the application in Python, not the SMTP server itself
- keep the path open to swap mail engines later if the product requires it

## If You Are New To This Repo

Read in this order:

1. `README.md`
2. `ARCHITECTURE.md`
3. `cosmic_mail/main.py`
4. `cosmic_mail/domain/models.py`
5. `cosmic_mail/services`
6. `cosmic_mail/api/routes`
7. `infra/docker-compose.production.yml`
8. `infra/james/conf`

That sequence gives you the fastest path to understanding the system without getting lost in details too early.

## Near-Term Roadmap

- validate full external send / receive with a real domain
- add alias and forwarding support
- add inbound eventing beyond polling (IMAP IDLE or webhook bridge)
- add stronger tenant safety and abuse controls
- bounce and complaint ingestion
- richer operator analytics and search
