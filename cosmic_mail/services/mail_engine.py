from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class MailEngineError(RuntimeError):
    pass


DEFAULT_SYSTEM_MAILBOXES: tuple[str, ...] = (
    "INBOX",
    "Draft",
    "Sent",
    "Trash",
    "Outbox",
)


@dataclass(frozen=True)
class ProvisioningResult:
    created: bool
    already_exists: bool = False


class MailEngine(Protocol):
    def ensure_domain(self, domain: str) -> ProvisioningResult:
        ...

    def ensure_user(self, address: str, password: str) -> ProvisioningResult:
        ...

    def configure_mailbox(
        self,
        address: str,
        *,
        quota_mb: int,
        quota_messages: int,
    ) -> None:
        ...


class NoopMailEngine:
    def ensure_domain(self, domain: str) -> ProvisioningResult:
        return ProvisioningResult(created=True)

    def ensure_user(self, address: str, password: str) -> ProvisioningResult:
        return ProvisioningResult(created=True)

    def configure_mailbox(
        self,
        address: str,
        *,
        quota_mb: int,
        quota_messages: int,
    ) -> None:
        return None
