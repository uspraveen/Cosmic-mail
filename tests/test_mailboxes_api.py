from __future__ import annotations

from tests.helpers import bootstrap_organization, create_active_domain


def test_create_mailbox_requires_active_domain(client, admin_headers):
    organization, organization_headers = bootstrap_organization(client, admin_headers)
    domain = client.post(
        "/v1/domains",
        json={"organization_id": organization["id"], "domain": "agents.acme.dev"},
        headers=organization_headers,
    ).json()

    response = client.post(
        "/v1/mailboxes",
        json={"domain_id": domain["id"], "local_part": "agent"},
        headers=organization_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "domain is not active"


def test_create_mailbox_provisions_user_and_returns_generated_password(client, admin_headers, fake_mail_engine, fake_dns_verifier):
    _, organization_headers, domain = create_active_domain(client, admin_headers, fake_dns_verifier)

    response = client.post(
        "/v1/mailboxes",
        json={"domain_id": domain["id"], "local_part": "agent", "display_name": "Agent One"},
        headers=organization_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["address"] == "agent@agents.acme.dev"
    assert payload["status"] == "active"
    assert payload["issued_password"]
    assert fake_mail_engine.users[0][0] == "agent@agents.acme.dev"
    assert fake_mail_engine.configured_mailboxes == [
        ("agent@agents.acme.dev", 1024, 100000),
    ]


def test_create_mailbox_detects_duplicate_address(client, admin_headers, fake_dns_verifier):
    _, organization_headers, domain = create_active_domain(client, admin_headers, fake_dns_verifier)

    first = client.post(
        "/v1/mailboxes",
        json={"domain_id": domain["id"], "local_part": "agent"},
        headers=organization_headers,
    )
    second = client.post(
        "/v1/mailboxes",
        json={"domain_id": domain["id"], "local_part": "agent"},
        headers=organization_headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409
