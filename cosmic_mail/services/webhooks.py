from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import httpx

from cosmic_mail.domain.models import MailMessage, MailThread, Webhook, WebhookEventType
from cosmic_mail.domain.repositories import WebhookRepository

logger = logging.getLogger(__name__)


def _build_payload(event_type: str, message: MailMessage, thread: MailThread) -> dict:
    return {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mailbox_id": message.mailbox_id,
        "thread_id": message.thread_id,
        "message": {
            "id": message.id,
            "internet_message_id": message.internet_message_id,
            "direction": message.direction,
            "subject": message.subject,
            "from_address": message.from_address,
            "from_name": message.from_name,
            "to_recipients": message.to_recipients,
            "preview_text": message.preview_text,
            "received_at": message.received_at.isoformat() if message.received_at else None,
            "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        },
        "thread": {
            "id": thread.id,
            "subject": thread.subject,
            "message_count": thread.message_count,
        },
    }


def _sign_payload(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def dispatch_webhooks(
    repo: WebhookRepository,
    message: MailMessage,
    thread: MailThread,
    event_type: str,
) -> None:
    webhooks = repo.list_active_for_mailbox(message.organization_id, message.mailbox_id)
    if not webhooks:
        return

    matching = [
        wh for wh in webhooks
        if wh.event_type in (WebhookEventType.all.value, event_type)
    ]
    if not matching:
        return

    payload = _build_payload(event_type, message, thread)
    body = json.dumps(payload, default=str).encode()

    for webhook in matching:
        _fire(webhook, body)


def _fire(webhook: Webhook, body: bytes) -> None:
    headers = {"Content-Type": "application/json", "X-Cosmic-Mail-Event": "1"}
    if webhook.secret:
        headers["X-Cosmic-Mail-Signature"] = _sign_payload(webhook.secret, body)
    try:
        with httpx.Client(timeout=8.0) as client:
            resp = client.post(webhook.url, content=body, headers=headers)
            if resp.status_code >= 400:
                logger.warning("Webhook %s returned %s", webhook.id, resp.status_code)
    except Exception as exc:
        logger.warning("Webhook %s delivery failed: %s", webhook.id, exc)
