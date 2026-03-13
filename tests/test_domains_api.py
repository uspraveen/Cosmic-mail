from __future__ import annotations

from tests.helpers import bootstrap_organization, create_active_domain


def test_create_domain_returns_dns_plan(client, admin_headers):
    organization, organization_headers = bootstrap_organization(client, admin_headers)
    organization_id = organization["id"]

    response = client.post(
        "/v1/domains",
        json={"organization_id": organization_id, "domain": "Agents.Acme.dev"},
        headers=organization_headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "agents.acme.dev"
    assert payload["status"] == "pending_dns"
    assert payload["james_domain_created"] is False
    assert {record["type"] for record in payload["dns_records"]} == {"MX", "TXT"}
    assert any(record["host"] == "agents.acme.dev" and record["type"] == "MX" for record in payload["dns_records"])
    assert any(record["host"] == "_dmarc.agents.acme.dev" for record in payload["dns_records"])


def test_verify_dns_activates_domain_and_provisions_james(client, admin_headers, fake_mail_engine, fake_dns_verifier):
    _, organization_headers, domain = create_active_domain(client, admin_headers, fake_dns_verifier)

    verify = client.post(f"/v1/domains/{domain['id']}/verify-dns", headers=organization_headers)

    assert verify.status_code == 200
    payload = verify.json()
    assert payload["all_records_present"] is True
    assert payload["status"] == "active"
    assert payload["james_domain_created"] is True
    assert fake_mail_engine.domains == ["agents.acme.dev"]


def test_verify_dns_leaves_domain_pending_when_records_are_missing(client, admin_headers, fake_mail_engine):
    organization, organization_headers = bootstrap_organization(client, admin_headers)
    domain = client.post(
        "/v1/domains",
        json={"organization_id": organization["id"], "domain": "agents.acme.dev"},
        headers=organization_headers,
    ).json()

    verify = client.post(f"/v1/domains/{domain['id']}/verify-dns", headers=organization_headers)

    assert verify.status_code == 200
    payload = verify.json()
    assert payload["all_records_present"] is False
    assert payload["status"] == "pending_dns"
    assert fake_mail_engine.domains == []
