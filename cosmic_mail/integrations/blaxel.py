from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx


class BlaxelError(RuntimeError):
    pass


@dataclass(frozen=True)
class SandboxRef:
    name: str
    url: str
    status: str


class BlaxelClient:
    def __init__(
        self,
        api_key: str,
        *,
        workspace: str | None = None,
        base_url: str = "https://api.blaxel.ai/v0",
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = self._build_headers(api_key, workspace)
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
            transport=transport,
        )
        self._runtime_client = httpx.Client(
            timeout=timeout,
            headers=headers,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        self._runtime_client.close()
        self._client.close()

    def create_sandbox(
        self,
        *,
        name: str,
        image: str,
        memory_mb: int,
        ports: Iterable[int] = (),
        region: str | None = None,
        ttl: str = "2h",
        idle_ttl: str = "30m",
        envs: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "metadata": {"name": name},
            "spec": {
                "enabled": True,
                "runtime": {
                    "image": image,
                    "memory": memory_mb,
                    "ttl": ttl,
                    "ports": [{"target": port} for port in ports],
                },
                "lifecycle": {
                    "expirationPolicies": [
                        {
                            "action": "delete",
                            "type": "ttl-idle",
                            "value": idle_ttl,
                        }
                    ]
                },
            },
        }
        if region:
            body["spec"]["region"] = region
        if envs:
            body["spec"]["runtime"]["envs"] = [
                {"name": key, "value": value}
                for key, value in envs.items()
            ]

        response = self._client.post(
            "/sandboxes",
            params={"createIfNotExist": "true"},
            json=body,
        )
        return self._expect_json(response, "create sandbox")

    def get_sandbox(self, name: str) -> dict[str, Any]:
        response = self._client.get(f"/sandboxes/{name}")
        return self._expect_json(response, "get sandbox")

    def delete_sandbox(self, name: str) -> dict[str, Any] | None:
        response = self._client.delete(f"/sandboxes/{name}")
        if response.status_code == 404:
            return None
        return self._expect_json(response, "delete sandbox")

    def wait_for_status(
        self,
        name: str,
        *,
        expected: str = "DEPLOYED",
        timeout_seconds: float = 180.0,
        poll_interval_seconds: float = 2.0,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last_payload: dict[str, Any] | None = None

        while time.monotonic() < deadline:
            payload = self.get_sandbox(name)
            last_payload = payload
            status = str(payload.get("status", "")).upper()
            if status == expected.upper():
                return payload
            if status == "FAILED":
                raise BlaxelError(f"sandbox {name} failed to deploy: {payload}")
            time.sleep(poll_interval_seconds)

        raise BlaxelError(
            f"sandbox {name} did not reach {expected} before timeout: {last_payload}"
        )

    def upload_tree(
        self,
        sandbox_url: str,
        destination_path: str,
        files: Mapping[str, str],
    ) -> dict[str, Any]:
        path = destination_path.strip("/")
        response = self._runtime_client.put(
            self._runtime_url(sandbox_url, f"/filesystem/tree/{path}"),
            json={"files": dict(files)},
            headers={"Content-Type": "application/json"},
        )
        return self._expect_json(response, "upload tree")

    def exec_process(
        self,
        sandbox_url: str,
        *,
        command: str,
        name: str | None = None,
        working_dir: str | None = None,
        env: Mapping[str, str] | None = None,
        wait_for_completion: bool = True,
        timeout_seconds: int | None = None,
        wait_for_ports: Iterable[int] | None = None,
        keep_alive: bool | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "command": command,
            "waitForCompletion": wait_for_completion,
        }
        if name:
            body["name"] = name
        if working_dir:
            body["workingDir"] = working_dir
        if env:
            body["env"] = dict(env)
        if timeout_seconds is not None:
            body["timeout"] = timeout_seconds
        if wait_for_ports:
            body["waitForPorts"] = list(wait_for_ports)
        if keep_alive is not None:
            body["keepAlive"] = keep_alive

        response = self._runtime_client.post(
            self._runtime_url(sandbox_url, "/process"),
            json=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=None if wait_for_completion or wait_for_ports else self._client.timeout,
        )
        return self._expect_json(response, "exec process")

    def get_process(self, sandbox_url: str, identifier: str) -> dict[str, Any]:
        response = self._runtime_client.get(
            self._runtime_url(sandbox_url, f"/process/{identifier}"),
        )
        return self._expect_json(response, "get process")

    def get_process_logs(self, sandbox_url: str, identifier: str) -> dict[str, Any]:
        response = self._runtime_client.get(
            self._runtime_url(sandbox_url, f"/process/{identifier}/logs"),
        )
        return self._expect_json(response, "get process logs")

    @staticmethod
    def sandbox_ref(payload: Mapping[str, Any]) -> SandboxRef:
        metadata = payload.get("metadata", {})
        return SandboxRef(
            name=str(metadata.get("name", "")),
            url=str(metadata.get("url", "")),
            status=str(payload.get("status", "")),
        )

    @staticmethod
    def port_url(sandbox_url: str, port: int) -> str:
        return f"{sandbox_url.rstrip('/')}/port/{port}"

    @staticmethod
    def _build_headers(api_key: str, workspace: str | None) -> dict[str, str]:
        bearer = f"Bearer {api_key}"
        headers = {
            "Authorization": bearer,
            "X-Blaxel-Authorization": bearer,
        }
        if workspace:
            headers["X-Blaxel-Workspace"] = workspace
        return headers

    @staticmethod
    def _runtime_url(sandbox_url: str, path: str) -> str:
        return f"{sandbox_url.rstrip('/')}/{path.lstrip('/')}"

    @staticmethod
    def _expect_json(response: httpx.Response, action: str) -> dict[str, Any]:
        try:
            payload = response.json() if response.content else {}
        except ValueError:
            payload = {"raw": response.text}

        if response.is_success:
            return payload

        raise BlaxelError(f"failed to {action}: {response.status_code} {payload}")
