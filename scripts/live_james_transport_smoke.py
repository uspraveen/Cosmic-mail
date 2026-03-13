from __future__ import annotations

import argparse
import time
import uuid

from fastapi.testclient import TestClient

from cosmic_mail.core.config import Settings
from cosmic_mail.main import create_app


class StaticDnsVerifier:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], list[str]] = {}

    def set_records(self, record_type: str, host: str, values: list[str]) -> None:
        self._records[(record_type, host)] = values

    def lookup(self, record_type: str, host: str) -> list[str]:
        return self._records.get((record_type, host), [])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exercise Cosmic Mail against a live Apache James instance.")
    parser.add_argument("--admin-api-key", required=True)
    parser.add_argument("--secret-key", required=True)
    parser.add_argument("--james-webadmin-url", default="http://127.0.0.1:8000")
    parser.add_argument("--public-mail-hostname", default="mx.cosmicmail.test")
    parser.add_argument("--smtp-host", default="127.0.0.1")
    parser.add_argument("--smtp-port", type=int, default=25)
    parser.add_argument("--smtp-use-starttls", action="store_true")
    parser.add_argument("--smtp-auth-enabled", action="store_true")
    parser.add_argument("--imap-host", default="127.0.0.1")
    parser.add_argument("--imap-port", type=int, default=143)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dns_verifier = StaticDnsVerifier()
    run_suffix = uuid.uuid4().hex[:8]
    organization_slug = f"cosmic-smoke-{run_suffix}"
    domain_name = f"{organization_slug}.mail-smoke.dev"
    settings = Settings(
        database_url="sqlite:///:memory:",
        admin_api_key=args.admin_api_key,
        secret_key=args.secret_key,
        public_mail_hostname=args.public_mail_hostname,
        mail_engine_backend="james",
        james_webadmin_url=args.james_webadmin_url,
        smtp_host=args.smtp_host,
        smtp_port=args.smtp_port,
        smtp_use_starttls=args.smtp_use_starttls,
        smtp_validate_certs=False,
        smtp_auth_enabled=args.smtp_auth_enabled,
        imap_host=args.imap_host,
        imap_port=args.imap_port,
        imap_use_ssl=False,
        imap_validate_certs=False,
    )

    admin_headers = {"X-API-Key": args.admin_api_key}
    app = create_app(settings=settings, dns_verifier=dns_verifier)
    with TestClient(app) as client:
        organization = client.post(
            "/v1/organizations",
            json={"name": f"Cosmic Smoke {run_suffix}", "slug": organization_slug},
            headers=admin_headers,
        )
        organization.raise_for_status()
        organization_payload = organization.json()

        api_key_response = client.post(
            f"/v1/organizations/{organization_payload['id']}/api-keys",
            json={"name": "smoke-primary"},
            headers=admin_headers,
        )
        api_key_response.raise_for_status()
        org_headers = {"X-API-Key": api_key_response.json()["plaintext_key"]}

        domain = client.post(
            "/v1/domains",
            json={
                "organization_id": organization_payload["id"],
                "domain": domain_name,
            },
            headers=org_headers,
        )
        domain.raise_for_status()
        domain_payload = domain.json()

        deliverability = client.get(
            f"/v1/domains/{domain_payload['id']}/deliverability",
            headers=org_headers,
        )
        deliverability.raise_for_status()
        assert deliverability.json()["connection_profile"]["submission"]["host"] == args.public_mail_hostname

        configure_dns_for_domain(dns_verifier, domain_payload)

        verify = client.post(
            f"/v1/domains/{domain_payload['id']}/verify-dns",
            headers=org_headers,
        )
        verify.raise_for_status()
        assert verify.json()["status"] == "active"

        sender_mailbox = client.post(
            "/v1/mailboxes",
            json={
                "domain_id": domain_payload["id"],
                "local_part": "agent",
                "display_name": "Cosmic Agent",
                "quota_mb": 128,
                "quota_messages": 4096,
            },
            headers=org_headers,
        )
        sender_mailbox.raise_for_status()
        sender_payload = sender_mailbox.json()

        recipient_mailbox = client.post(
            "/v1/mailboxes",
            json={
                "domain_id": domain_payload["id"],
                "local_part": "ops",
                "display_name": "Ops Inbox",
                "quota_mb": 128,
                "quota_messages": 4096,
            },
            headers=org_headers,
        )
        recipient_mailbox.raise_for_status()
        recipient_payload = recipient_mailbox.json()

        sync_policy = client.get(
            f"/v1/mailboxes/{recipient_payload['id']}/sync-policy",
            headers=org_headers,
        )
        sync_policy.raise_for_status()
        assert sync_policy.json()["enabled"] is True

        draft = client.post(
            "/v1/drafts",
            json={
                "mailbox_id": sender_payload["id"],
                "subject": "James transport smoke",
                "to_recipients": [{"email": recipient_payload["address"], "name": "Ops Inbox"}],
                "text_body": "This message should arrive through real SMTP and IMAP.",
            },
            headers=org_headers,
        )
        draft.raise_for_status()

        send = client.post(
            f"/v1/drafts/{draft.json()['id']}/send",
            headers=org_headers,
        )
        if send.status_code >= 400:
            raise RuntimeError(f"draft send failed: {send.status_code} {send.text}")

        sync_status = client.get("/v1/system/sync-worker", headers=admin_headers)
        sync_status.raise_for_status()
        assert sync_status.json()["enabled"] is False

        sync_payload = None
        for _ in range(15):
            sync = client.post(
                "/v1/system/sync-worker/run-once",
                params={"organization_id": organization_payload["id"]},
                headers=admin_headers,
            )
            sync.raise_for_status()
            sync_payload = sync.json()
            if sync_payload["imported_count"] > 0:
                break
            time.sleep(1.0)

        assert sync_payload is not None
        assert sync_payload["imported_count"] >= 1

        threads = client.get(
            "/v1/threads",
            params={"mailbox_id": recipient_payload["id"]},
            headers=org_headers,
        )
        threads.raise_for_status()
        threads_payload = threads.json()
        assert len(threads_payload) == 1
        assert threads_payload[0]["message_count"] >= 1

        messages = client.get(
            f"/v1/threads/{threads_payload[0]['id']}/messages",
            headers=org_headers,
        )
        messages.raise_for_status()
        messages_payload = messages.json()
        assert any(message["from_address"] == sender_payload["address"] for message in messages_payload)

    print("[smoke] live James SMTP/IMAP transport passed")
    return 0


def configure_dns_for_domain(dns_verifier: StaticDnsVerifier, domain_payload: dict[str, object]) -> None:
    record_map = {
        (record["type"], record["host"]): record
        for record in domain_payload["dns_records"]
    }
    domain_name = str(domain_payload["name"])

    dns_verifier.set_records("MX", domain_name, ["10 mx.cosmicmail.test"])
    dns_verifier.set_records(
        "TXT",
        domain_name,
        [str(record_map[("TXT", domain_name)]["value"])],
    )
    dns_verifier.set_records(
        "TXT",
        f"_dmarc.{domain_name}",
        [str(record_map[("TXT", f"_dmarc.{domain_name}")]["value"])],
    )
    dkim_host = next(
        record["host"]
        for record in domain_payload["dns_records"]
        if record["host"].endswith(f"._domainkey.{domain_name}")
    )
    dns_verifier.set_records(
        "TXT",
        str(dkim_host),
        [str(record_map[("TXT", str(dkim_host))]["value"])],
    )


if __name__ == "__main__":
    raise SystemExit(main())
