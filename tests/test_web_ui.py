from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from cosmic_mail.main import create_app


def test_root_serves_operator_console(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Cosmic Mail Console" in response.text
    assert 'data-view="agents"' in response.text
    assert "/static/app.css" in response.text
    assert "/static/app.js" in response.text


def test_static_assets_are_served(client):
    css_response = client.get("/static/app.css")
    js_response = client.get("/static/app.js")
    api_response = client.get("/static/api.js")
    state_response = client.get("/static/state.js")
    templates_response = client.get("/static/templates.js")

    assert css_response.status_code == 200
    assert ".nav-button" in css_response.text
    assert js_response.status_code == 200
    assert 'from "./api.js"' in js_response.text
    assert api_response.status_code == 200
    assert state_response.status_code == 200
    assert templates_response.status_code == 200
    assert "loadWorkspace" in js_response.text


def test_operator_console_loads_from_package_data_when_source_static_dir_is_missing(
    monkeypatch,
    test_settings,
    fake_mail_engine,
    fake_dns_verifier,
    fake_outbound_sender,
    fake_inbound_client,
):
    monkeypatch.setattr("cosmic_mail.main.WEB_STATIC_DIR", Path("Z:/definitely-missing-static-dir"))

    app = create_app(
        settings=test_settings,
        mail_engine=fake_mail_engine,
        dns_verifier=fake_dns_verifier,
        outbound_sender=fake_outbound_sender,
        inbound_client=fake_inbound_client,
    )

    with TestClient(app) as fallback_client:
        root_response = fallback_client.get("/")
        js_response = fallback_client.get("/static/app.js")
        api_response = fallback_client.get("/static/api.js")
        state_response = fallback_client.get("/static/state.js")
        templates_response = fallback_client.get("/static/templates.js")

    assert root_response.status_code == 200
    assert "Cosmic Mail Console" in root_response.text
    assert js_response.status_code == 200
    assert api_response.status_code == 200
    assert state_response.status_code == 200
    assert templates_response.status_code == 200
    assert "loadWorkspace" in js_response.text
