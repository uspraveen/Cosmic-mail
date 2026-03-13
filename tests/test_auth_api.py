from __future__ import annotations

from tests.helpers import bootstrap_organization


def test_api_routes_require_api_key(client):
    response = client.get("/v1/organizations")

    assert response.status_code == 401
    assert response.json()["detail"] == "missing api key"


def test_org_key_cannot_access_other_organization_resources(client, admin_headers):
    acme, acme_headers = bootstrap_organization(client, admin_headers, name="Acme Agents", slug="acme")
    beta, beta_headers = bootstrap_organization(client, admin_headers, name="Beta Agents", slug="beta")

    forbidden_domain = client.post(
        "/v1/domains",
        json={"organization_id": beta["id"], "domain": "agents.beta.dev"},
        headers=acme_headers,
    )
    assert forbidden_domain.status_code == 403
    assert forbidden_domain.json()["detail"] == "organization access denied"

    own_domain = client.post(
        "/v1/domains",
        json={"organization_id": beta["id"], "domain": "agents.beta.dev"},
        headers=beta_headers,
    )
    assert own_domain.status_code == 201

    listed = client.get("/v1/organizations", headers=beta_headers)
    assert listed.status_code == 200
    payload = listed.json()
    assert len(payload) == 1
    assert payload[0]["id"] == beta["id"]


def test_revoked_api_key_can_no_longer_access_routes(client, admin_headers):
    organization, organization_headers = bootstrap_organization(client, admin_headers)

    created_api_key = client.post(
        f"/v1/organizations/{organization['id']}/api-keys",
        json={"name": "secondary"},
        headers=organization_headers,
    )
    assert created_api_key.status_code == 201
    api_key_payload = created_api_key.json()

    revoke_response = client.delete(
        f"/v1/organizations/{organization['id']}/api-keys/{api_key_payload['api_key']['id']}",
        headers=organization_headers,
    )
    assert revoke_response.status_code == 200

    revoked_headers = {"X-API-Key": api_key_payload["plaintext_key"]}
    listed = client.get("/v1/organizations", headers=revoked_headers)
    assert listed.status_code == 401
    assert listed.json()["detail"] == "invalid api key"


def test_auth_context_endpoint_reflects_current_key_scope(client, admin_headers):
    organization, organization_headers = bootstrap_organization(client, admin_headers)

    admin_response = client.get("/v1/system/auth-context", headers=admin_headers)
    assert admin_response.status_code == 200
    assert admin_response.json()["is_admin"] is True
    assert admin_response.json()["organization_id"] is None

    organization_response = client.get("/v1/system/auth-context", headers=organization_headers)
    assert organization_response.status_code == 200
    payload = organization_response.json()
    assert payload["is_admin"] is False
    assert payload["organization_id"] == organization["id"]
