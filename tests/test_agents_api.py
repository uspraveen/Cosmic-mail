from __future__ import annotations

from tests.helpers import bootstrap_organization, create_active_domain, create_active_mailbox


def test_create_and_update_agent(client, admin_headers, fake_dns_verifier):
    organization, organization_headers, domain = create_active_domain(client, admin_headers, fake_dns_verifier)

    create_response = client.post(
        "/v1/agents",
        json={
            "organization_id": organization["id"],
            "name": "Support Scout",
            "title": "Tier 1 Inbox Agent",
            "persona_summary": "Handles routine inbound support triage.",
            "system_prompt": "Be calm, concise, and structured.",
            "signature": "Support Scout",
            "default_domain_id": domain["id"],
            "accent_color": "#ff8a1f",
        },
        headers=organization_headers,
    )

    assert create_response.status_code == 201
    payload = create_response.json()
    assert payload["organization_id"] == organization["id"]
    assert payload["default_domain_id"] == domain["id"]
    assert payload["default_domain_name"] == "agents.acme.dev"
    assert payload["mailboxes"] == []

    update_response = client.patch(
        f"/v1/agents/{payload['id']}",
        json={
            "title": "Escalation Triage Agent",
            "status": "paused",
            "accent_color": "#fb923c",
        },
        headers=organization_headers,
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["title"] == "Escalation Triage Agent"
    assert updated["status"] == "paused"
    assert updated["accent_color"] == "#fb923c"


def test_link_and_unlink_mailboxes_for_agent(client, admin_headers, fake_dns_verifier):
    organization, organization_headers, domain, mailbox = create_active_mailbox(client, admin_headers, fake_dns_verifier)
    second_mailbox = client.post(
        "/v1/mailboxes",
        json={"domain_id": domain["id"], "local_part": "escalations", "display_name": "Escalations"},
        headers=organization_headers,
    ).json()

    agent = client.post(
        "/v1/agents",
        json={"organization_id": organization["id"], "name": "Ops Lead"},
        headers=organization_headers,
    ).json()

    first_link = client.post(
        f"/v1/agents/{agent['id']}/mailboxes",
        json={"mailbox_id": mailbox["id"], "label": "Primary inbox"},
        headers=organization_headers,
    )

    assert first_link.status_code == 200
    first_payload = first_link.json()
    assert len(first_payload["mailboxes"]) == 1
    assert first_payload["mailboxes"][0]["mailbox_id"] == mailbox["id"]
    assert first_payload["mailboxes"][0]["is_primary"] is True

    second_link = client.post(
        f"/v1/agents/{agent['id']}/mailboxes",
        json={"mailbox_id": second_mailbox["id"], "label": "Escalations", "is_primary": True},
        headers=organization_headers,
    )

    assert second_link.status_code == 200
    second_payload = second_link.json()
    primary_mailboxes = [entry for entry in second_payload["mailboxes"] if entry["is_primary"]]
    assert len(primary_mailboxes) == 1
    assert primary_mailboxes[0]["mailbox_id"] == second_mailbox["id"]

    unlink = client.delete(
        f"/v1/agents/{agent['id']}/mailboxes/{second_mailbox['id']}",
        headers=organization_headers,
    )

    assert unlink.status_code == 200
    unlink_payload = unlink.json()
    assert len(unlink_payload["mailboxes"]) == 1
    assert unlink_payload["mailboxes"][0]["mailbox_id"] == mailbox["id"]
    assert unlink_payload["mailboxes"][0]["is_primary"] is True


def test_agent_mailbox_link_enforces_organization_scope(client, admin_headers, fake_dns_verifier):
    organization, organization_headers, _, mailbox = create_active_mailbox(client, admin_headers, fake_dns_verifier)
    other_organization, other_headers = bootstrap_organization(client, admin_headers, name="Other Org", slug="other")

    other_domain = client.post(
        "/v1/domains",
        json={"organization_id": other_organization["id"], "domain": "agents.other.dev"},
        headers=other_headers,
    ).json()

    domain_records = {(record["type"], record["host"]): record for record in other_domain["dns_records"]}
    fake_dns_verifier.set_records("MX", "agents.other.dev", ["10 mx.cosmicmail.test"])
    fake_dns_verifier.set_records("TXT", "agents.other.dev", [domain_records[("TXT", "agents.other.dev")]["value"]])
    fake_dns_verifier.set_records(
        "TXT",
        "_dmarc.agents.other.dev",
        [domain_records[("TXT", "_dmarc.agents.other.dev")]["value"]],
    )
    fake_dns_verifier.set_records(
        "TXT",
        "agent._domainkey.agents.other.dev",
        [domain_records[("TXT", "agent._domainkey.agents.other.dev")]["value"]],
    )
    client.post(f"/v1/domains/{other_domain['id']}/verify-dns", headers=other_headers)

    agent = client.post(
        "/v1/agents",
        json={"organization_id": organization["id"], "name": "Shared Agent"},
        headers=organization_headers,
    ).json()

    response = client.post(
        f"/v1/agents/{agent['id']}/mailboxes",
        json={"mailbox_id": mailbox["id"]},
        headers=other_headers,
    )

    assert response.status_code == 403
