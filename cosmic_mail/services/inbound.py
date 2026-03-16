from __future__ import annotations

import imaplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from email.parser import BytesParser
from email.policy import default as default_policy
from email.utils import make_msgid
from typing import Protocol

from cosmic_mail.services.message_utils import (
    extract_message_bodies,
    normalize_subject,
    parse_contacts,
    parse_header_datetime,
    parse_references,
    utcnow,
)


class InboxSyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class InboundAttachment:
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class InboundMessageEnvelope:
    source_uid: int
    internet_message_id: str
    folder_name: str
    subject: str
    normalized_subject: str
    in_reply_to: str | None
    references: list[str] = field(default_factory=list)
    from_name: str | None = None
    from_address: str = "unknown@unknown.invalid"
    to_recipients: list[dict[str, str | None]] = field(default_factory=list)
    cc_recipients: list[dict[str, str | None]] = field(default_factory=list)
    bcc_recipients: list[dict[str, str | None]] = field(default_factory=list)
    reply_to_recipients: list[dict[str, str | None]] = field(default_factory=list)
    text_body: str | None = None
    html_body: str | None = None
    sent_at: datetime | None = None
    received_at: datetime = field(default_factory=utcnow)
    attachments: list[InboundAttachment] = field(default_factory=list)
    is_bounce: bool = False
    bounce_type: str | None = None  # "hard" | "soft"


class InboundMailboxClient(Protocol):
    def fetch_messages(
        self,
        *,
        address: str,
        password: str,
        last_uid: int,
        folder_name: str,
    ) -> list[InboundMessageEnvelope]:
        ...


class NoopInboundMailboxClient:
    def fetch_messages(
        self,
        *,
        address: str,
        password: str,
        last_uid: int,
        folder_name: str,
    ) -> list[InboundMessageEnvelope]:
        return []


class IMAPInboundMailboxClient:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        use_ssl: bool,
        use_starttls: bool,
        validate_certs: bool,
        timeout_seconds: float,
    ) -> None:
        self._host = host
        self._port = port
        self._use_ssl = use_ssl
        self._use_starttls = use_starttls
        self._validate_certs = validate_certs
        self._timeout_seconds = timeout_seconds

    def fetch_messages(
        self,
        *,
        address: str,
        password: str,
        last_uid: int,
        folder_name: str,
    ) -> list[InboundMessageEnvelope]:
        client = self._connect()
        try:
            self._expect_ok(client.login(address, password), "imap login failed")
            self._expect_ok(client.select(folder_name, readonly=True), f"unable to select {folder_name}")
            start_uid = max(1, last_uid + 1)
            status, payload = client.uid("SEARCH", None, f"UID {start_uid}:*")
            self._expect_ok((status, payload), "imap search failed")
            raw_uids = payload[0].decode("utf-8").strip() if payload and payload[0] else ""
            if not raw_uids:
                return []

            envelopes: list[InboundMessageEnvelope] = []
            for raw_uid in raw_uids.split():
                status, fetch_payload = client.uid("FETCH", raw_uid, "(RFC822)")
                self._expect_ok((status, fetch_payload), f"imap fetch failed for uid {raw_uid}")
                raw_message = _extract_rfc822_bytes(fetch_payload)
                if raw_message is None:
                    continue
                envelopes.append(
                    _parse_envelope(
                        raw_message,
                        source_uid=int(raw_uid),
                        folder_name=folder_name,
                        default_domain=address.split("@", maxsplit=1)[-1],
                    )
                )
            return envelopes
        except (imaplib.IMAP4.error, OSError, ValueError) as exc:
            raise InboxSyncError(f"imap sync failed: {exc}") from exc
        finally:
            try:
                client.logout()
            except (imaplib.IMAP4.error, OSError):
                pass

    def _connect(self) -> imaplib.IMAP4:
        ssl_context = _build_ssl_context(self._validate_certs)
        if self._use_ssl:
            return imaplib.IMAP4_SSL(
                host=self._host,
                port=self._port,
                timeout=self._timeout_seconds,
                ssl_context=ssl_context,
            )
        client = imaplib.IMAP4(
            host=self._host,
            port=self._port,
            timeout=self._timeout_seconds,
        )
        if self._use_starttls:
            client.starttls(ssl_context=ssl_context)
        return client

    @staticmethod
    def _expect_ok(result: tuple[str, list[bytes]], error_message: str) -> None:
        status, _ = result
        if status != "OK":
            raise InboxSyncError(error_message)


def _extract_rfc822_bytes(payload: list[object]) -> bytes | None:
    for item in payload:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            return item[1]
    return None


def _parse_envelope(
    raw_message: bytes,
    *,
    source_uid: int,
    folder_name: str,
    default_domain: str,
) -> InboundMessageEnvelope:
    parsed = BytesParser(policy=default_policy).parsebytes(raw_message)
    subject = str(parsed.get("Subject") or "").strip() or "(no subject)"
    in_reply_to = str(parsed.get("In-Reply-To")).strip() if parsed.get("In-Reply-To") else None
    references = parse_references(str(parsed.get("References")) if parsed.get("References") else None)
    from_contacts = parse_contacts(parsed.get_all("From", []))
    from_contact = from_contacts[0] if from_contacts else {"email": "unknown@unknown.invalid", "name": None}
    text_body, html_body = extract_message_bodies(parsed)
    message_id = str(parsed.get("Message-ID") or "").strip() or make_msgid(domain=default_domain)
    attachments = _extract_attachments(parsed)
    is_bounce, bounce_type = _detect_bounce(parsed)

    return InboundMessageEnvelope(
        source_uid=source_uid,
        internet_message_id=message_id,
        folder_name=folder_name,
        subject=subject,
        normalized_subject=normalize_subject(subject),
        in_reply_to=in_reply_to,
        references=references,
        from_name=from_contact.get("name"),
        from_address=from_contact.get("email") or "unknown@unknown.invalid",
        to_recipients=parse_contacts(parsed.get_all("To", [])),
        cc_recipients=parse_contacts(parsed.get_all("Cc", [])),
        bcc_recipients=parse_contacts(parsed.get_all("Bcc", [])),
        reply_to_recipients=parse_contacts(parsed.get_all("Reply-To", [])),
        text_body=text_body,
        html_body=html_body,
        sent_at=parse_header_datetime(str(parsed.get("Date")) if parsed.get("Date") else None),
        received_at=utcnow(),
        attachments=attachments,
        is_bounce=is_bounce,
        bounce_type=bounce_type,
    )


_BOUNCE_FROM_PATTERNS = (
    "mailer-daemon",
    "postmaster",
    "mail delivery subsystem",
    "delivery subsystem",
)

_BOUNCE_SUBJECT_PATTERNS = (
    "delivery status notification",
    "delivery failure",
    "mail delivery failed",
    "returned to sender",
    "undeliverable",
    "delivery has failed",
    "mail system error",
    "failed delivery",
    "could not be delivered",
    "message not delivered",
)


def _detect_bounce(parsed) -> tuple[bool, str | None]:
    """Return (is_bounce, bounce_type) by inspecting the parsed message.

    bounce_type is "hard" (permanent 5xx), "soft" (transient 4xx), or None
    when the classification cannot be determined but the message looks like a bounce.
    """
    content_type = parsed.get_content_type() or ""
    report_type = (parsed.get_param("report-type") or "").lower()

    if content_type == "multipart/report" and report_type == "delivery-status":
        # Walk parts for the machine-readable delivery-status section
        for part in parsed.walk():
            if part.get_content_type() == "message/delivery-status":
                payload = part.get_payload()
                if isinstance(payload, str):
                    cls = _parse_dsn_status_class(payload)
                    if cls == "5":
                        return True, "hard"
                    if cls == "4":
                        return True, "soft"
        # Standard DSN structure but no parseable status — treat as hard bounce
        return True, "hard"

    # Fallback: heuristic header matching
    from_header = str(parsed.get("From") or "").lower()
    subject = str(parsed.get("Subject") or "").lower()

    if any(p in from_header for p in _BOUNCE_FROM_PATTERNS):
        return True, "hard"
    if any(p in subject for p in _BOUNCE_SUBJECT_PATTERNS):
        return True, "hard"

    return False, None


def _parse_dsn_status_class(delivery_status_payload: str) -> str | None:
    """Return the RFC 3463 status class digit (2/4/5) from a delivery-status part."""
    for line in delivery_status_payload.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("status:"):
            value = stripped.split(":", 1)[1].strip()
            if value and value[0] in ("2", "4", "5"):
                return value[0]
    return None


def _extract_attachments(parsed) -> list[InboundAttachment]:
    attachments: list[InboundAttachment] = []
    for part in parsed.walk():
        content_disposition = str(part.get("Content-Disposition") or "")
        if part.get_content_maintype() == "multipart":
            continue
        is_attachment = "attachment" in content_disposition
        is_inline_with_name = "inline" in content_disposition and part.get_filename()
        if not (is_attachment or is_inline_with_name):
            continue
        filename = part.get_filename() or "attachment"
        data = part.get_payload(decode=True)
        if not isinstance(data, bytes) or not data:
            continue
        content_type = part.get_content_type() or "application/octet-stream"
        attachments.append(InboundAttachment(filename=filename, content_type=content_type, data=data))
    return attachments


def _build_ssl_context(validate_certs: bool) -> ssl.SSLContext:
    if validate_certs:
        return ssl.create_default_context()
    return ssl._create_unverified_context()
