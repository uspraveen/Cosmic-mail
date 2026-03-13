from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from cosmic_mail.api.auth import AuthContext, authenticate_request
from cosmic_mail.core.config import Settings
from cosmic_mail.services.inbound import InboundMailboxClient
from cosmic_mail.services.dns import DNSVerifier
from cosmic_mail.services.mail_engine import MailEngine
from cosmic_mail.services.outbound import OutboundMailSender
from cosmic_mail.services.sync_manager import SyncWorker


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def get_mail_engine(request: Request) -> MailEngine:
    return request.app.state.mail_engine


def get_dns_verifier(request: Request) -> DNSVerifier:
    return request.app.state.dns_verifier


def get_outbound_sender(request: Request) -> OutboundMailSender:
    return request.app.state.outbound_sender


def get_inbound_client(request: Request) -> InboundMailboxClient:
    return request.app.state.inbound_client


def get_sync_worker(request: Request) -> SyncWorker:
    return request.app.state.sync_worker


def get_auth_context(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    return authenticate_request(request, session, settings)
