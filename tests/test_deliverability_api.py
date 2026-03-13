from __future__ import annotations

from tests.helpers import bootstrap_organization, create_active_domain


def test_get_domain_deliverability_exposes_dns_and_connection_profile(client, admin_headers, fake_dns_verifier):
    _, organization_headers, domain = create_active_domain(client, admin_headers, fake_dns_verifier)

    response = client.get(
        f"/v1/domains/{domain['id']}/deliverability",
        headers=organization_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["domain_id"] == domain["id"]
    assert payload["connection_profile"]["submission"]["host"] == "mx.cosmicmail.test"
    assert payload["connection_profile"]["submission"]["port"] == 587
    assert payload["connection_profile"]["submission"]["security"] == "starttls"
    assert payload["connection_profile"]["imap"]["port"] == 993
    assert any(record["host"] == "_dmarc.agents.acme.dev" for record in payload["dns_records"])


def test_update_domain_deliverability_reissues_dns_verification(client, admin_headers, fake_dns_verifier):
    _, organization_headers, domain = create_active_domain(client, admin_headers, fake_dns_verifier)

    response = client.patch(
        f"/v1/domains/{domain['id']}/deliverability",
        json={
            "spf_value": "v=spf1 mx include:_spf.senders.example -all",
            "dmarc_policy": "reject",
            "dmarc_subdomain_policy": "reject",
            "dmarc_aggregate_report_email": "dmarc-reports@example.com",
        },
        headers=organization_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending_dns"
    assert payload["spf_value"] == "v=spf1 mx include:_spf.senders.example -all"
    assert "p=reject" in payload["dmarc_value"]
    assert "rua=mailto:dmarc-reports@example.com" in payload["dmarc_value"]
    assert any(
        record["host"] == "agents.acme.dev" and "include:_spf.senders.example" in record["value"]
        for record in payload["dns_records"]
    )


def test_rotate_domain_dkim_changes_selector(client, admin_headers):
    organization, organization_headers = bootstrap_organization(client, admin_headers)
    domain = client.post(
        "/v1/domains",
        json={"organization_id": organization["id"], "domain": "agents.acme.dev"},
        headers=organization_headers,
    ).json()

    response = client.post(
        f"/v1/domains/{domain['id']}/rotate-dkim",
        json={},
        headers=organization_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending_dns"
    assert payload["dkim_selector"] != "agent"
    assert any(
        record["host"] == f"{payload['dkim_selector']}._domainkey.agents.acme.dev"
        for record in payload["dns_records"]
    )
