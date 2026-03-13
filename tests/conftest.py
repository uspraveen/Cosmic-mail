from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from cosmic_mail.core.config import Settings
from cosmic_mail.main import create_app
from cosmic_mail.services.inbound import InboundMessageEnvelope
from cosmic_mail.services.mail_engine import ProvisioningResult
from cosmic_mail.services.outbound import OutboundSendResult


class FakeMailEngine:
    def __init__(self) -> None:
        self.domains: list[str] = []
        self.users: list[tuple[str, str]] = []
        self.configured_mailboxes: list[tuple[str, int, int]] = []

    def ensure_domain(self, domain: str) -> ProvisioningResult:
        if domain in self.domains:
            return ProvisioningResult(created=False, already_exists=True)
        self.domains.append(domain)
        return ProvisioningResult(created=True)

    def ensure_user(self, address: str, password: str) -> ProvisioningResult:
        if any(existing_address == address for existing_address, _ in self.users):
            return ProvisioningResult(created=False, already_exists=True)
        self.users.append((address, password))
        return ProvisioningResult(created=True)

    def configure_mailbox(
        self,
        address: str,
        *,
        quota_mb: int,
        quota_messages: int,
    ) -> None:
        self.configured_mailboxes.append((address, quota_mb, quota_messages))


class FakeDNSVerifier:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], list[str]] = defaultdict(list)

    def set_records(self, record_type: str, host: str, values: list[str]) -> None:
        self.records[(record_type, host)] = values

    def lookup(self, record_type: str, host: str) -> list[str]:
        return self.records.get((record_type, host), [])


class FakeOutboundSender:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self._counter = 0

    def send(self, request, *, password: str | None) -> OutboundSendResult:
        self._counter += 1
        sent_at = datetime(2026, 3, 11, 18, self._counter, tzinfo=timezone.utc)
        message_id = f"<fake-{self._counter}@cosmic.test>"
        self.calls.append(
            {
                "request": request,
                "password": password,
                "message_id": message_id,
                "sent_at": sent_at,
            }
        )
        return OutboundSendResult(internet_message_id=message_id, sent_at=sent_at)


class FakeInboundClient:
    def __init__(self) -> None:
        self.messages_by_address: dict[str, list[InboundMessageEnvelope]] = defaultdict(list)
        self.calls: list[dict[str, object]] = []

    def set_messages(self, address: str, messages: list[InboundMessageEnvelope]) -> None:
        self.messages_by_address[address] = list(messages)

    def fetch_messages(
        self,
        *,
        address: str,
        password: str,
        last_uid: int,
        folder_name: str,
    ) -> list[InboundMessageEnvelope]:
        self.calls.append(
            {
                "address": address,
                "password": password,
                "last_uid": last_uid,
                "folder_name": folder_name,
            }
        )
        return list(self.messages_by_address.get(address, []))


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        database_url="sqlite:///:memory:",
        admin_api_key="test-admin-key",
        secret_key="tests-only-secret",
        public_mail_hostname="mx.cosmicmail.test",
        default_dkim_selector="agent",
    )


@pytest.fixture
def fake_mail_engine() -> FakeMailEngine:
    return FakeMailEngine()


@pytest.fixture
def fake_dns_verifier() -> FakeDNSVerifier:
    return FakeDNSVerifier()


@pytest.fixture
def fake_outbound_sender() -> FakeOutboundSender:
    return FakeOutboundSender()


@pytest.fixture
def fake_inbound_client() -> FakeInboundClient:
    return FakeInboundClient()


@pytest.fixture
def admin_headers(test_settings: Settings) -> dict[str, str]:
    return {"X-API-Key": test_settings.admin_api_key or ""}


@pytest.fixture
def client(
    test_settings: Settings,
    fake_mail_engine: FakeMailEngine,
    fake_dns_verifier: FakeDNSVerifier,
    fake_outbound_sender: FakeOutboundSender,
    fake_inbound_client: FakeInboundClient,
):
    app = create_app(
        settings=test_settings,
        mail_engine=fake_mail_engine,
        dns_verifier=fake_dns_verifier,
        outbound_sender=fake_outbound_sender,
        inbound_client=fake_inbound_client,
    )
    with TestClient(app) as test_client:
        yield test_client
