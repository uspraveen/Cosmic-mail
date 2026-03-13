from __future__ import annotations

from typing import Any

import httpx

from cosmic_mail.services.mail_engine import (
    DEFAULT_SYSTEM_MAILBOXES,
    MailEngineError,
    ProvisioningResult,
)


class JamesMailEngine:
    def __init__(
        self,
        base_url: str,
        admin_token: str | None = None,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers: dict[str, str] = {}
        if admin_token:
            headers["Authorization"] = f"Bearer {admin_token}"
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers=headers,
            transport=transport,
        )

    def ensure_domain(self, domain: str) -> ProvisioningResult:
        response = self._request("PUT", f"/domains/{domain}")
        if response.status_code == 409:
            return ProvisioningResult(created=False, already_exists=True)
        self._expect_success(response, allowed={204})
        return ProvisioningResult(created=True)

    def ensure_user(self, address: str, password: str) -> ProvisioningResult:
        response = self._request("PUT", f"/users/{address}", json={"password": password})
        if response.status_code == 409:
            return ProvisioningResult(created=False, already_exists=True)
        self._expect_success(response, allowed={204})
        return ProvisioningResult(created=True)

    def configure_mailbox(
        self,
        address: str,
        *,
        quota_mb: int,
        quota_messages: int,
    ) -> None:
        self._set_user_quota(
            address,
            quota_mb=quota_mb,
            quota_messages=quota_messages,
        )
        self._ensure_system_mailboxes(address)

    def check_health(self) -> dict[str, Any]:
        response = self._request("GET", "/healthcheck")
        self._expect_success(response, allowed={200})
        payload = response.json()
        if payload.get("status") == "unhealthy":
            raise MailEngineError(f"apache james is unhealthy: {payload}")
        return payload

    def user_exists(self, address: str) -> bool:
        response = self._request("HEAD", f"/users/{address}")
        if response.status_code == 404:
            return False
        self._expect_success(response, allowed={200})
        return True

    def get_user_quota(self, address: str) -> dict[str, Any]:
        response = self._request("GET", f"/quota/users/{address}")
        self._expect_success(response, allowed={200})
        return response.json()

    def list_user_mailboxes(self, address: str) -> list[str]:
        response = self._request("GET", f"/users/{address}/mailboxes")
        self._expect_success(response, allowed={200})
        return [entry["mailboxName"] for entry in response.json()]

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise MailEngineError(f"apache james request failed: {exc}") from exc

    def _set_user_quota(
        self,
        address: str,
        *,
        quota_mb: int,
        quota_messages: int,
    ) -> None:
        response = self._request(
            "PUT",
            f"/quota/users/{address}",
            json={
                "count": quota_messages,
                "size": quota_mb * 1024 * 1024,
            },
        )
        self._expect_success(response, allowed={204})

    def _ensure_system_mailboxes(self, address: str) -> None:
        for mailbox_name in DEFAULT_SYSTEM_MAILBOXES:
            response = self._request("PUT", f"/users/{address}/mailboxes/{mailbox_name}")
            self._expect_success(response, allowed={200, 204})

    @staticmethod
    def _expect_success(response: httpx.Response, *, allowed: set[int]) -> None:
        if response.status_code not in allowed:
            raise MailEngineError(
                f"apache james returned {response.status_code}: {response.text}"
            )
