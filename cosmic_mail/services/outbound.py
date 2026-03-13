from __future__ import annotations

import email.policy
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from email.utils import format_datetime, formataddr, make_msgid
from typing import Protocol

from cosmic_mail.services.message_utils import html_to_text, normalize_contacts, utcnow

logger = logging.getLogger(__name__)


class OutboundMailError(RuntimeError):
    pass


@dataclass(frozen=True)
class OutboundAttachment:
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class OutboundSendRequest:
    from_address: str
    from_name: str | None
    subject: str
    to_recipients: list[dict[str, str | None]]
    cc_recipients: list[dict[str, str | None]] = field(default_factory=list)
    bcc_recipients: list[dict[str, str | None]] = field(default_factory=list)
    reply_to_recipients: list[dict[str, str | None]] = field(default_factory=list)
    text_body: str | None = None
    html_body: str | None = None
    in_reply_to: str | None = None
    references: list[str] = field(default_factory=list)
    attachments: list[OutboundAttachment] = field(default_factory=list)
    dkim_private_key_pem: str | None = None
    dkim_selector: str | None = None
    dkim_domain: str | None = None


@dataclass(frozen=True)
class OutboundSendResult:
    internet_message_id: str
    sent_at: datetime


class OutboundMailSender(Protocol):
    def send(
        self,
        request: OutboundSendRequest,
        *,
        password: str | None,
    ) -> OutboundSendResult:
        ...


class NoopOutboundMailSender:
    def send(
        self,
        request: OutboundSendRequest,
        *,
        password: str | None,
    ) -> OutboundSendResult:
        sent_at = utcnow()
        domain = request.from_address.split("@", maxsplit=1)[-1]
        return OutboundSendResult(
            internet_message_id=make_msgid(domain=domain),
            sent_at=sent_at,
        )


class SMTPOutboundMailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        use_ssl: bool,
        use_starttls: bool,
        validate_certs: bool,
        auth_enabled: bool,
        timeout_seconds: float,
    ) -> None:
        self._host = host
        self._port = port
        self._use_ssl = use_ssl
        self._use_starttls = use_starttls
        self._validate_certs = validate_certs
        self._auth_enabled = auth_enabled
        self._timeout_seconds = timeout_seconds

    def send(
        self,
        request: OutboundSendRequest,
        *,
        password: str | None,
    ) -> OutboundSendResult:
        sent_at = utcnow()
        domain = request.from_address.split("@", maxsplit=1)[-1]
        message = EmailMessage()
        message["Message-ID"] = make_msgid(domain=domain)
        message["Date"] = format_datetime(sent_at)
        message["From"] = _format_address(request.from_name, request.from_address)
        message["To"] = _format_recipient_header(request.to_recipients)
        if request.cc_recipients:
            message["Cc"] = _format_recipient_header(request.cc_recipients)
        if request.reply_to_recipients:
            message["Reply-To"] = _format_recipient_header(request.reply_to_recipients)
        if request.in_reply_to:
            message["In-Reply-To"] = request.in_reply_to
        if request.references:
            message["References"] = " ".join(request.references)
        message["Subject"] = request.subject

        text_body = (request.text_body or "").strip()
        html_body = (request.html_body or "").strip()
        if html_body:
            message.set_content(text_body or html_to_text(html_body) or " ")
            message.add_alternative(html_body, subtype="html")
        else:
            message.set_content(text_body or " ")

        for att in request.attachments:
            maintype, _, subtype = att.content_type.partition("/")
            if not maintype or not subtype:
                maintype, subtype = "application", "octet-stream"
            message.add_attachment(att.data, maintype=maintype, subtype=subtype, filename=att.filename)

        recipients = [
            contact["email"]
            for contact in normalize_contacts(
                [
                    *request.to_recipients,
                    *request.cc_recipients,
                    *request.bcc_recipients,
                ]
            )
        ]

        raw_message = message.as_bytes(policy=email.policy.SMTP)
        if request.dkim_private_key_pem and request.dkim_selector and request.dkim_domain:
            raw_message = _dkim_sign(
                raw_message,
                selector=request.dkim_selector,
                domain=request.dkim_domain,
                private_key_pem=request.dkim_private_key_pem,
            )

        try:
            smtp = self._connect()
            with smtp:
                if self._auth_enabled:
                    if not password:
                        raise OutboundMailError("smtp authentication requires a mailbox password")
                    smtp.login(request.from_address, password)
                smtp.sendmail(request.from_address, recipients, raw_message)
        except (smtplib.SMTPException, OSError) as exc:
            raise OutboundMailError(f"smtp send failed: {exc}") from exc

        return OutboundSendResult(
            internet_message_id=message["Message-ID"],
            sent_at=sent_at,
        )

    def _connect(self) -> smtplib.SMTP:
        ssl_context = _build_ssl_context(self._validate_certs)
        if self._use_ssl:
            return smtplib.SMTP_SSL(
                host=self._host,
                port=self._port,
                timeout=self._timeout_seconds,
                context=ssl_context,
            )

        smtp = smtplib.SMTP(
            host=self._host,
            port=self._port,
            timeout=self._timeout_seconds,
        )
        smtp.ehlo()
        if self._use_starttls:
            smtp.starttls(context=ssl_context)
            smtp.ehlo()
        return smtp


def _dkim_sign(message_bytes: bytes, *, selector: str, domain: str, private_key_pem: str) -> bytes:
    """Sign message_bytes and return sig_header + message_bytes."""
    try:
        import dkim  # type: ignore[import-untyped]
        sig = dkim.sign(
            message=message_bytes,
            selector=selector.encode(),
            domain=domain.encode(),
            privkey=private_key_pem.encode(),
            include_headers=[
                b"from", b"to", b"cc", b"subject", b"date",
                b"message-id", b"mime-version", b"in-reply-to", b"references",
            ],
        )
        return sig + message_bytes
    except Exception as exc:
        logger.warning("DKIM signing failed, sending unsigned: %s", exc)
        return message_bytes


def _format_address(name: str | None, email: str) -> str:
    return formataddr((name, email)) if name else email


def _format_recipient_header(recipients: list[dict[str, str | None]]) -> str:
    return ", ".join(_format_address(contact.get("name"), contact["email"]) for contact in recipients)


def _build_ssl_context(validate_certs: bool) -> ssl.SSLContext:
    if validate_certs:
        return ssl.create_default_context()
    return ssl._create_unverified_context()
