from __future__ import annotations

import httpx

from cosmic_mail.integrations.blaxel import BlaxelClient


def test_blaxel_client_create_sandbox_uses_expected_payload():
    requests: list[tuple[str, str, dict[str, str], str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(
            (
                request.method,
                str(request.url),
                dict(request.headers),
                request.read().decode("utf-8"),
            )
        )
        return httpx.Response(
            status_code=200,
            json={
                "metadata": {
                    "name": "cosmic-mail-smoke",
                    "url": "https://run.blaxel.ai/work/sandboxes/test",
                },
                "spec": {"runtime": {"image": "python:3.12-slim", "memory": 2048}},
                "status": "DEPLOYED",
            },
        )

    client = BlaxelClient(
        "test-api-key",
        workspace="workspace-a",
        transport=httpx.MockTransport(handler),
    )

    payload = client.create_sandbox(
        name="cosmic-mail-smoke",
        image="python:3.12-slim",
        memory_mb=2048,
        ports=(8000,),
        region="us-pdx-1",
    )
    client.close()

    assert payload["metadata"]["name"] == "cosmic-mail-smoke"
    assert requests[0][0] == "POST"
    assert "createIfNotExist=true" in requests[0][1]
    headers = {key.lower(): value for key, value in requests[0][2].items()}
    assert headers["authorization"] == "Bearer test-api-key"
    assert headers["x-blaxel-authorization"] == "Bearer test-api-key"
    assert headers["x-blaxel-workspace"] == "workspace-a"
    assert '"name":"cosmic-mail-smoke"' in requests[0][3]
    assert '"image":"python:3.12-slim"' in requests[0][3]
    assert '"target":8000' in requests[0][3]


def test_blaxel_client_upload_tree_targets_runtime_path():
    requests: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url), request.read().decode("utf-8")))
        return httpx.Response(status_code=200, json={"files": {}, "subdirectories": []})

    client = BlaxelClient(
        "test-api-key",
        transport=httpx.MockTransport(handler),
    )

    client.upload_tree(
        "https://run.blaxel.ai/workspace/sandboxes/cosmic-mail",
        "/workspace",
        {"README.md": "# Cosmic Mail"},
    )
    client.close()

    assert requests[0][0] == "PUT"
    assert (
        requests[0][1]
        == "https://run.blaxel.ai/workspace/sandboxes/cosmic-mail/filesystem/tree/workspace"
    )
    assert requests[0][2] == '{"files":{"README.md":"# Cosmic Mail"}}'
