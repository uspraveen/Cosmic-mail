from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from html import unescape


_SUBJECT_PREFIX_RE = re.compile(r"^\s*((re|fw|fwd)\s*:\s*)+", re.IGNORECASE)
_REFERENCE_RE = re.compile(r"<[^>]+>")
_HTML_BLOCK_RE = re.compile(r"</?(?:br|div|p|li|tr|td|h[1-6])\b[^>]*>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc_datetime(value: datetime | None) -> datetime:
    if value is None:
        return utcnow()
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_subject(value: str | None) -> str:
    subject = (value or "").strip()
    if not subject:
        return "(no subject)"
    normalized = _SUBJECT_PREFIX_RE.sub("", subject).strip()
    return normalized or "(no subject)"


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def normalize_contacts(
    contacts: Iterable[dict[str, str | None]],
) -> list[dict[str, str | None]]:
    normalized: list[dict[str, str | None]] = []
    for contact in contacts:
        email = (contact.get("email") or "").strip().lower()
        if not email:
            continue
        raw_name = contact.get("name")
        name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else None
        normalized.append({"email": email, "name": name})
    return normalized


def parse_contacts(values: Sequence[str]) -> list[dict[str, str | None]]:
    contacts = [
        {"email": address, "name": display_name}
        for display_name, address in getaddresses(values)
    ]
    return normalize_contacts(contacts)


def parse_references(value: str | None) -> list[str]:
    if not value:
        return []
    tokens = _REFERENCE_RE.findall(value) or value.split()
    return unique_preserve_order(tokens)


def html_to_text(value: str) -> str:
    text = _HTML_BLOCK_RE.sub("\n", value)
    text = _HTML_TAG_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", unescape(text)).strip()


def extract_preview(
    text_body: str | None,
    html_body: str | None,
    *,
    limit: int = 180,
) -> str | None:
    source = (text_body or "").strip()
    if not source and html_body:
        source = html_to_text(html_body)
    if not source:
        return None
    collapsed = _WHITESPACE_RE.sub(" ", source).strip()
    return collapsed[:limit]


def parse_header_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_message_bodies(message: Message) -> tuple[str | None, str | None]:
    plain_parts: list[str] = []
    html_parts: list[str] = []
    for part in _walk_renderable_parts(message):
        try:
            content = part.get_content()
        except (KeyError, LookupError, UnicodeDecodeError):
            continue
        if not isinstance(content, str):
            continue
        cleaned = content.strip()
        if not cleaned:
            continue
        if part.get_content_type() == "text/plain":
            plain_parts.append(cleaned)
        elif part.get_content_type() == "text/html":
            html_parts.append(cleaned)

    text_body = "\n\n".join(plain_parts) if plain_parts else None
    html_body = "\n\n".join(html_parts) if html_parts else None
    return text_body, html_body


def _walk_renderable_parts(message: Message) -> list[Message]:
    if not message.is_multipart():
        return [message]

    parts: list[Message] = []
    for part in message.walk():
        disposition = part.get_content_disposition()
        content_type = part.get_content_type()
        if disposition == "attachment":
            continue
        if content_type in {"text/plain", "text/html"}:
            parts.append(part)
    return parts
