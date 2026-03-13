from __future__ import annotations

from datetime import datetime, timezone

from cosmic_mail.services.inbound import InboundMessageEnvelope
from tests.helpers import create_active_mailbox


def test_sync_inbox_imports_threads_and_deduplicates(client, admin_headers, fake_dns_verifier, fake_inbound_client):
    _, organization_headers, _, mailbox = create_active_mailbox(client, admin_headers, fake_dns_verifier)
    fake_inbound_client.set_messages(
        mailbox["address"],
        [
            InboundMessageEnvelope(
                source_uid=101,
                internet_message_id="<m1@example.net>",
                folder_name="INBOX",
                subject="Need pricing",
                normalized_subject="Need pricing",
                in_reply_to=None,
                references=[],
                from_name="Buyer",
                from_address="buyer@example.net",
                to_recipients=[{"email": mailbox["address"], "name": "Agent One"}],
                text_body="Can you send pricing?",
                sent_at=datetime(2026, 3, 11, 10, 0, tzinfo=timezone.utc),
                received_at=datetime(2026, 3, 11, 10, 1, tzinfo=timezone.utc),
            ),
            InboundMessageEnvelope(
                source_uid=102,
                internet_message_id="<m2@example.net>",
                folder_name="INBOX",
                subject="Re: Need pricing",
                normalized_subject="Need pricing",
                in_reply_to="<m1@example.net>",
                references=["<m1@example.net>"],
                from_name="Buyer",
                from_address="buyer@example.net",
                to_recipients=[{"email": mailbox["address"], "name": "Agent One"}],
                text_body="Following up on this.",
                sent_at=datetime(2026, 3, 11, 10, 5, tzinfo=timezone.utc),
                received_at=datetime(2026, 3, 11, 10, 6, tzinfo=timezone.utc),
            ),
        ],
    )

    first_sync = client.post(f"/v1/mailboxes/{mailbox['id']}/sync-inbox", headers=organization_headers)
    assert first_sync.status_code == 200
    first_payload = first_sync.json()
    assert first_payload["imported_count"] == 2
    assert first_payload["skipped_count"] == 0
    assert first_payload["last_inbound_uid"] == 102

    threads_response = client.get("/v1/threads", params={"mailbox_id": mailbox["id"]}, headers=organization_headers)
    assert threads_response.status_code == 200
    threads = threads_response.json()
    assert len(threads) == 1
    assert threads[0]["message_count"] == 2

    messages_response = client.get(
        f"/v1/threads/{threads[0]['id']}/messages",
        headers=organization_headers,
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert [message["internet_message_id"] for message in messages] == [
        "<m1@example.net>",
        "<m2@example.net>",
    ]

    second_sync = client.post(f"/v1/mailboxes/{mailbox['id']}/sync-inbox", headers=organization_headers)
    assert second_sync.status_code == 200
    second_payload = second_sync.json()
    assert second_payload["imported_count"] == 0
    assert second_payload["skipped_count"] == 2
