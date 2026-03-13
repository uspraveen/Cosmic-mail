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
- agent profiles with prompts, signatures, default domains, and mailbox links
- domain onboarding with generated `MX`, `SPF`, `DKIM`, and `DMARC`
- DNS verification and domain deliverability management
- mailbox provisioning into Apache James
- encrypted mailbox credential storage
- outbound send flow through pluggable SMTP-style transport
- inbound sync through pluggable IMAP-style transport
- product-owned threads, messages, and drafts
- background sync worker and manual sync controls
- a built-in operator console served from `/`
- Linux deployment artifacts for `Cosmic Mail + Postgres + Apache James`
- automated tests and Linux smoke coverage

What is not finished:

- real external inbox-placement validation with Gmail / Outlook / enterprise providers
- final TLS / HTTPS production setup with a real domain
- outbound DKIM signing integration on the transport path
- bounce / complaint ingestion
- alias and forwarding controls
- abuse controls, quotas, and rate shaping for hostile multi-tenant use
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

Important relationship summary:

- one organization owns many domains
- one domain owns many inboxes
- one organization owns many agents
- one agent can link to many inboxes
- one inbox can be linked to many agents
- one inbox owns many threads
- one thread owns many messages

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
  - business logic for organizations, agents, domains, inboxes, conversations, transport, and sync
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

### 5. Mail Flow

- create a draft
- send the draft through the configured outbound transport
- sync inbound mail through IMAP
- normalize inbound and outbound mail into product-owned threads and messages

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
- `GET /v1/domains`
- `POST /v1/domains/{domain_id}/verify-dns`
- `GET /v1/domains/{domain_id}/deliverability`
- `PATCH /v1/domains/{domain_id}/deliverability`
- `POST /v1/domains/{domain_id}/rotate-dkim`

### Agents

- `POST /v1/agents`
- `GET /v1/agents`
- `GET /v1/agents/{agent_id}`
- `PATCH /v1/agents/{agent_id}`
- `POST /v1/agents/{agent_id}/mailboxes`
- `DELETE /v1/agents/{agent_id}/mailboxes/{mailbox_id}`

### Mailboxes

- `POST /v1/mailboxes`
- `GET /v1/mailboxes`
- `GET /v1/mailboxes/{mailbox_id}/sync-policy`
- `PATCH /v1/mailboxes/{mailbox_id}/sync-policy`
- `POST /v1/mailboxes/{mailbox_id}/sync-inbox`

### Drafts and Conversations

- `POST /v1/drafts`
- `GET /v1/drafts`
- `POST /v1/drafts/{draft_id}/send`
- `GET /v1/threads`
- `GET /v1/threads/{thread_id}/messages`

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
- `Access`

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

- `COSMIC_MAIL_DATABASE_URL`
- `COSMIC_MAIL_ADMIN_API_KEY`
- `COSMIC_MAIL_SECRET_KEY`
- `COSMIC_MAIL_MAIL_ENGINE_BACKEND`
- `COSMIC_MAIL_JAMES_WEBADMIN_URL`
- `COSMIC_MAIL_JAMES_ADMIN_TOKEN`
- `COSMIC_MAIL_PUBLIC_MAIL_HOSTNAME`
- `COSMIC_MAIL_PUBLIC_SUBMISSION_HOSTNAME`
- `COSMIC_MAIL_PUBLIC_SUBMISSION_PORT`
- `COSMIC_MAIL_PUBLIC_SUBMISSION_USE_STARTTLS`
- `COSMIC_MAIL_PUBLIC_IMAP_HOSTNAME`
- `COSMIC_MAIL_PUBLIC_IMAP_PORT`
- `COSMIC_MAIL_PUBLIC_IMAP_USE_SSL`
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
- `COSMIC_MAIL_SYNC_WORKER_ENABLED`
- `COSMIC_MAIL_SYNC_WORKER_INTERVAL_SECONDS`
- `COSMIC_MAIL_SYNC_WORKER_BATCH_SIZE`

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

- real external deliverability validation
- DNS automation and production onboarding UX
- bounce and complaint handling
- outbound DKIM signing at the transport layer
- aliases and forwarding
- abuse detection and rate control
- richer search and operator analytics
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

- stabilize the operator console and keep it intentionally simple
- validate full external send / receive with a real domain
- finish DKIM signing integration
- add alias and forwarding support
- add inbound eventing beyond polling
- add stronger tenant safety and abuse controls
