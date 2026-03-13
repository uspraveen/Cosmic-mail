from __future__ import annotations

from tests.helpers import create_active_mailbox


def test_create_and_send_draft_persists_thread_and_message(client, admin_headers, fake_dns_verifier, fake_outbound_sender):
    _, organization_headers, _, mailbox = create_active_mailbox(client, admin_headers, fake_dns_verifier)

    create_response = client.post(
        "/v1/drafts",
        json={
            "mailbox_id": mailbox["id"],
            "subject": "Intro from Cosmic",
            "to_recipients": [{"email": "user@gmail.com", "name": "User"}],
            "text_body": "Hello from our agent platform.",
        },
        headers=organization_headers,
    )

    assert create_response.status_code == 201
    draft = create_response.json()
    assert draft["status"] == "draft"

    list_response = client.get("/v1/drafts", params={"mailbox_id": mailbox["id"]}, headers=organization_headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    send_response = client.post(f"/v1/drafts/{draft['id']}/send", headers=organization_headers)
    assert send_response.status_code == 200
    payload = send_response.json()

    assert payload["draft"]["status"] == "sent"
    assert payload["message"]["direction"] == "outbound"
    assert payload["message"]["subject"] == "Intro from Cosmic"
    assert payload["thread"]["message_count"] == 1
    assert fake_outbound_sender.calls[0]["password"] == mailbox["issued_password"]

    outbound_request = fake_outbound_sender.calls[0]["request"]
    assert outbound_request.subject == "Intro from Cosmic"
    assert outbound_request.to_recipients == [{"email": "user@gmail.com", "name": "User"}]

    threads_response = client.get("/v1/threads", params={"mailbox_id": mailbox["id"]}, headers=organization_headers)
    assert threads_response.status_code == 200
    threads = threads_response.json()
    assert len(threads) == 1
    assert threads[0]["id"] == payload["thread"]["id"]

    messages_response = client.get(
        f"/v1/threads/{payload['thread']['id']}/messages",
        headers=organization_headers,
    )
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert len(messages) == 1
    assert messages[0]["internet_message_id"] == payload["message"]["internet_message_id"]


def test_reply_draft_reuses_existing_thread(client, admin_headers, fake_dns_verifier):
    _, organization_headers, _, mailbox = create_active_mailbox(client, admin_headers, fake_dns_verifier)

    first_draft = client.post(
        "/v1/drafts",
        json={
            "mailbox_id": mailbox["id"],
            "subject": "Customer follow-up",
            "to_recipients": [{"email": "customer@gmail.com"}],
            "text_body": "First note.",
        },
        headers=organization_headers,
    ).json()
    first_send = client.post(f"/v1/drafts/{first_draft['id']}/send", headers=organization_headers).json()

    second_draft_response = client.post(
        "/v1/drafts",
        json={
            "mailbox_id": mailbox["id"],
            "thread_id": first_send["thread"]["id"],
            "reply_to_message_id": first_send["message"]["internet_message_id"],
            "subject": "Re: Customer follow-up",
            "to_recipients": [{"email": "customer@gmail.com"}],
            "text_body": "Second note.",
        },
        headers=organization_headers,
    )

    assert second_draft_response.status_code == 201
    second_draft = second_draft_response.json()

    second_send_response = client.post(f"/v1/drafts/{second_draft['id']}/send", headers=organization_headers)
    assert second_send_response.status_code == 200
    second_send = second_send_response.json()

    assert second_send["thread"]["id"] == first_send["thread"]["id"]
    assert second_send["message"]["in_reply_to"] == first_send["message"]["internet_message_id"]
    assert second_send["message"]["references"] == [first_send["message"]["internet_message_id"]]

    threads = client.get("/v1/threads", params={"mailbox_id": mailbox["id"]}, headers=organization_headers).json()
    assert len(threads) == 1
    assert threads[0]["message_count"] == 2
