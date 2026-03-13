from __future__ import annotations


def auth_headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def bootstrap_organization(client, admin_headers, *, name="Acme Agents", slug="acme"):
    organization = client.post(
        "/v1/organizations",
        json={"name": name, "slug": slug},
        headers=admin_headers,
    ).json()
    api_key = client.post(
        f"/v1/organizations/{organization['id']}/api-keys",
        json={"name": f"{slug}-primary"},
        headers=admin_headers,
    ).json()["plaintext_key"]
    return organization, auth_headers(api_key)


def create_active_domain(client, admin_headers, fake_dns_verifier):
    organization, organization_headers = bootstrap_organization(client, admin_headers)
    domain = client.post(
        "/v1/domains",
        json={"organization_id": organization["id"], "domain": "agents.acme.dev"},
        headers=organization_headers,
    ).json()

    records = {}
    for record in domain["dns_records"]:
        records[(record["type"], record["host"])] = record
    fake_dns_verifier.set_records("MX", "agents.acme.dev", ["10 mx.cosmicmail.test"])
    fake_dns_verifier.set_records("TXT", "agents.acme.dev", [records[("TXT", "agents.acme.dev")]["value"]])
    fake_dns_verifier.set_records(
        "TXT",
        "_dmarc.agents.acme.dev",
        [records[("TXT", "_dmarc.agents.acme.dev")]["value"]],
    )
    fake_dns_verifier.set_records(
        "TXT",
        "agent._domainkey.agents.acme.dev",
        [records[("TXT", "agent._domainkey.agents.acme.dev")]["value"]],
    )
    client.post(f"/v1/domains/{domain['id']}/verify-dns", headers=organization_headers)
    return organization, organization_headers, domain


def create_active_mailbox(client, admin_headers, fake_dns_verifier):
    organization, organization_headers, domain = create_active_domain(client, admin_headers, fake_dns_verifier)
    mailbox = client.post(
        "/v1/mailboxes",
        json={"domain_id": domain["id"], "local_part": "agent", "display_name": "Agent One"},
        headers=organization_headers,
    ).json()
    return organization, organization_headers, domain, mailbox
