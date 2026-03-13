from __future__ import annotations

from datetime import datetime, timezone

from cosmic_mail.services.inbound import InboundMessageEnvelope
from tests.helpers import create_active_mailbox


def test_mailbox_sync_policy_endpoints_toggle_worker_participation(
    client,
    admin_headers,
    fake_dns_verifier,
):
    _, organization_headers, _, mailbox = create_active_mailbox(client, admin_headers, fake_dns_verifier)

    get_response = client.get(
        f"/v1/mailboxes/{mailbox['id']}/sync-policy",
        headers=organization_headers,
    )
    assert get_response.status_code == 200
    assert get_response.json()["enabled"] is True

    patch_response = client.patch(
        f"/v1/mailboxes/{mailbox['id']}/sync-policy",
        json={"enabled": False},
        headers=organization_headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["enabled"] is False


def test_organization_sync_mailboxes_runs_enabled_mailboxes(
    client,
    admin_headers,
    fake_dns_verifier,
    fake_inbound_client,
):
    organization, organization_headers, _, mailbox = create_active_mailbox(client, admin_headers, fake_dns_verifier)
    fake_inbound_client.set_messages(
        mailbox["address"],
        [
            InboundMessageEnvelope(
                source_uid=201,
                internet_message_id="<org-sync@example.net>",
                folder_name="INBOX",
                subject="Pipeline",
                normalized_subject="Pipeline",
                in_reply_to=None,
                references=[],
                from_name="Buyer",
                from_address="buyer@example.net",
                to_recipients=[{"email": mailbox["address"], "name": "Agent One"}],
                text_body="Org level sync should import this.",
                sent_at=datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc),
                received_at=datetime(2026, 3, 11, 12, 1, tzinfo=timezone.utc),
            )
        ],
    )

    response = client.post(
        f"/v1/organizations/{organization['id']}/sync-mailboxes",
        headers=organization_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["organization_id"] == organization["id"]
    assert payload["mailbox_count"] == 1
    assert payload["synced_mailboxes"] == 1
    assert payload["imported_count"] == 1


def test_admin_sync_worker_endpoints_report_status_and_run(
    client,
    admin_headers,
    fake_dns_verifier,
    fake_inbound_client,
):
    organization, _, _, mailbox = create_active_mailbox(client, admin_headers, fake_dns_verifier)
    fake_inbound_client.set_messages(
        mailbox["address"],
        [
            InboundMessageEnvelope(
                source_uid=301,
                internet_message_id="<worker-sync@example.net>",
                folder_name="INBOX",
                subject="Worker sync",
                normalized_subject="Worker sync",
                in_reply_to=None,
                references=[],
                from_name="Buyer",
                from_address="buyer@example.net",
                to_recipients=[{"email": mailbox["address"], "name": "Agent One"}],
                text_body="System worker should import this.",
                sent_at=datetime(2026, 3, 11, 13, 0, tzinfo=timezone.utc),
                received_at=datetime(2026, 3, 11, 13, 1, tzinfo=timezone.utc),
            )
        ],
    )

    status_response = client.get("/v1/system/sync-worker", headers=admin_headers)
    assert status_response.status_code == 200
    assert status_response.json()["enabled"] is False

    run_response = client.post(
        "/v1/system/sync-worker/run-once",
        params={"organization_id": organization["id"]},
        headers=admin_headers,
    )
    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["organization_id"] == organization["id"]
    assert payload["mailbox_count"] == 1
    assert payload["synced_mailboxes"] == 1
    assert payload["imported_count"] == 1
