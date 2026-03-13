from __future__ import annotations

import httpx

from cosmic_mail.services.james import JamesMailEngine
from cosmic_mail.services.mail_engine import DEFAULT_SYSTEM_MAILBOXES


def test_james_mail_engine_uses_webadmin_routes():
    requests: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode("utf-8") if request.content else None
        requests.append((request.method, str(request.url), body))
        return httpx.Response(status_code=204)

    transport = httpx.MockTransport(handler)
    client = JamesMailEngine("http://mail.local:8000", admin_token="token", transport=transport)

    client.ensure_domain("agents.example.com")
    client.ensure_user("bot@agents.example.com", "super-secret-password")
    client.close()

    assert requests[0][0] == "PUT"
    assert requests[0][1] == "http://mail.local:8000/domains/agents.example.com"
    assert requests[1][0] == "PUT"
    assert requests[1][1] == "http://mail.local:8000/users/bot@agents.example.com"
    assert '"password":"super-secret-password"' in (requests[1][2] or "")


def test_james_mail_engine_configures_quota_and_system_mailboxes():
    requests: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode("utf-8") if request.content else None
        requests.append((request.method, str(request.url), body))
        return httpx.Response(status_code=204)

    transport = httpx.MockTransport(handler)
    client = JamesMailEngine("http://mail.local:8000", transport=transport)

    client.configure_mailbox(
        "bot@agents.example.com",
        quota_mb=256,
        quota_messages=4096,
    )
    client.close()

    assert requests[0][0] == "PUT"
    assert requests[0][1] == "http://mail.local:8000/quota/users/bot@agents.example.com"
    assert requests[0][2] == '{"count":4096,"size":268435456}'
    assert [request[1] for request in requests[1:]] == [
        f"http://mail.local:8000/users/bot@agents.example.com/mailboxes/{mailbox_name}"
        for mailbox_name in DEFAULT_SYSTEM_MAILBOXES
    ]


def test_james_mail_engine_user_exists_handles_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(status_code=404)
        return httpx.Response(status_code=500)

    transport = httpx.MockTransport(handler)
    client = JamesMailEngine("http://mail.local:8000", transport=transport)

    assert client.user_exists("missing@agents.example.com") is False
    client.close()
