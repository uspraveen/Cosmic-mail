from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cosmic_mail.integrations.blaxel import BlaxelClient, BlaxelError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Cosmic Mail Linux smoke test on Blaxel and delete the sandboxes afterward.",
    )
    parser.add_argument("--workspace", default=os.environ.get("BL_WORKSPACE"))
    parser.add_argument("--region", default=None)
    parser.add_argument("--python-image", default="blaxel/base-image:latest")
    parser.add_argument("--james-image", default="blaxel/base-image:latest")
    return parser.parse_args()


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} must be set")
    return value


def collect_repo_files(repo_root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    included_files = [
        repo_root / "pyproject.toml",
        repo_root / "README.md",
    ]
    included_roots = [
        repo_root / "cosmic_mail",
        repo_root / "infra",
        repo_root / "scripts",
        repo_root / "tests",
    ]

    for file_path in included_files:
        files[file_path.relative_to(repo_root).as_posix()] = file_path.read_text(encoding="utf-8")

    for root in included_roots:
        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            if "__pycache__" in file_path.parts:
                continue
            files[file_path.relative_to(repo_root).as_posix()] = file_path.read_text(encoding="utf-8")

    return files


def collect_james_conf_files(repo_root: Path) -> dict[str, str]:
    conf_root = repo_root / "infra" / "james" / "conf"
    return {
        file_path.name: file_path.read_text(encoding="utf-8")
        for file_path in conf_root.glob("*")
        if file_path.is_file()
    }


def runtime_headers(api_key: str, workspace: str | None) -> dict[str, str]:
    bearer = f"Bearer {api_key}"
    headers = {
        "Authorization": bearer,
        "X-Blaxel-Authorization": bearer,
    }
    if workspace:
        headers["X-Blaxel-Workspace"] = workspace
    return headers


def wait_for_http(
    url: str,
    *,
    api_key: str,
    workspace: str | None,
    timeout_seconds: float = 180.0,
) -> httpx.Response:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    with httpx.Client(
        follow_redirects=True,
        timeout=10.0,
        headers=runtime_headers(api_key, workspace),
    ) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(url)
                if response.status_code == 200:
                    return response
            except httpx.HTTPError as exc:
                last_error = exc
            time.sleep(2.0)

    raise RuntimeError(f"timed out waiting for {url}: {last_error}")


def ensure_process_success(
    blaxel: BlaxelClient,
    sandbox_url: str,
    *,
    command: str,
    name: str,
    working_dir: str | None = None,
    timeout_seconds: int = 600,
) -> dict[str, object]:
    process = blaxel.exec_process(
        sandbox_url,
        command=command,
        name=name,
        working_dir=working_dir,
        wait_for_completion=True,
        timeout_seconds=timeout_seconds,
    )
    if str(process.get("status", "")).lower() != "completed":
        logs = blaxel.get_process_logs(sandbox_url, str(process["pid"]))
        raise RuntimeError(f"process {name} failed: {logs}")
    return process


def run_python_linux_smoke(
    blaxel: BlaxelClient,
    *,
    repo_root: Path,
    sandbox_name: str,
    image: str,
    region: str | None,
) -> None:
    print(f"[blaxel] creating python sandbox {sandbox_name}")
    blaxel.create_sandbox(
        name=sandbox_name,
        image=image,
        memory_mb=2048,
        region=region,
        ttl="2h",
        idle_ttl="20m",
    )
    sandbox = blaxel.wait_for_status(sandbox_name)
    sandbox_url = blaxel.sandbox_ref(sandbox).url

    print("[blaxel] uploading Cosmic Mail repo snapshot")
    blaxel.upload_tree(sandbox_url, "/workspace", collect_repo_files(repo_root))

    print("[blaxel] installing python runtime in linux sandbox")
    install_python_runtime(blaxel, sandbox_url)

    print("[blaxel] installing dependencies in linux sandbox")
    ensure_process_success(
        blaxel,
        sandbox_url,
        command=(
            "sh -lc "
            "\"python3 -m venv /workspace/.venv && "
            ". /workspace/.venv/bin/activate && "
            "pip install --no-cache-dir -e .[dev]\""
        ),
        name="install-cosmic-mail",
        working_dir="/workspace",
        timeout_seconds=900,
    )

    print("[blaxel] running pytest in linux sandbox")
    ensure_process_success(
        blaxel,
        sandbox_url,
        command=(
            "sh -lc "
            "\". /workspace/.venv/bin/activate && "
            "python -m pytest -q\""
        ),
        name="pytest-cosmic-mail",
        working_dir="/workspace",
        timeout_seconds=900,
    )


def start_or_wait_for_james(
    blaxel: BlaxelClient,
    *,
    repo_root: Path,
    sandbox_name: str,
    image: str,
    region: str | None,
    api_key: str,
    workspace: str | None,
) -> str:
    print(f"[blaxel] creating James sandbox {sandbox_name}")
    blaxel.create_sandbox(
        name=sandbox_name,
        image=image,
        memory_mb=4096,
        ports=(8000,),
        region=region,
        ttl="2h",
        idle_ttl="20m",
    )
    sandbox = blaxel.wait_for_status(sandbox_name)
    sandbox_url = blaxel.sandbox_ref(sandbox).url
    health_url = BlaxelClient.port_url(sandbox_url, 8000) + "/healthcheck"

    print("[blaxel] installing Apache James in linux sandbox")
    ensure_process_success(
        blaxel,
        sandbox_url,
        command=(
            "sh -lc "
            "\"set -e; "
            "apk add --no-cache openjdk21-jdk curl unzip; "
            "curl -L https://dlcdn.apache.org/james/server/3.9.0/james-server-jpa-guice.zip "
            "-o /tmp/james.zip; "
            "rm -rf /opt/james; "
            "mkdir -p /opt/james; "
            "unzip -q /tmp/james.zip -d /opt/james; "
            "sed -i 's/^host=.*/host=0.0.0.0/' "
            "/opt/james/james-server-jpa-guice/conf/webadmin.properties; "
            "hostname cosmicmail-james; "
            "printf '127.0.0.1 localhost\\n127.0.0.1 cosmicmail-james\\n' > /etc/hosts\""
        ),
        name="install-james",
        timeout_seconds=1200,
    )

    print("[blaxel] uploading owned James configuration")
    blaxel.upload_tree(
        sandbox_url,
        "/opt/james/james-server-jpa-guice/conf",
        collect_james_conf_files(repo_root),
    )

    print("[blaxel] starting Apache James in linux sandbox")
    process = blaxel.exec_process(
        sandbox_url,
        command=(
            "sh -lc "
            "\"cd /opt/james/james-server-jpa-guice && "
            "java -javaagent:james-server-jpa-app.lib/openjpa-4.1.1.jar "
            "-Dworking.directory=. "
            "-Djdk.tls.ephemeralDHKeySize=2048 "
            "-Dlogback.configurationFile=conf/logback.xml "
            "-jar james-server-jpa-app.jar --generate-keystore\""
        ),
        name="james-server",
        wait_for_completion=False,
        timeout_seconds=0,
        keep_alive=True,
    )
    try:
        wait_for_http(
            health_url,
            api_key=api_key,
            workspace=workspace,
            timeout_seconds=180.0,
        )
    except Exception as exc:
        logs = blaxel.get_process_logs(sandbox_url, str(process["pid"]))
        raise RuntimeError(f"james failed to become healthy: {logs}") from exc

    return sandbox_url


def run_live_james_smoke_in_sandbox(
    blaxel: BlaxelClient,
    *,
    repo_root: Path,
    sandbox_url: str,
) -> None:
    print("[blaxel] uploading Cosmic Mail repo snapshot to James sandbox")
    blaxel.upload_tree(sandbox_url, "/workspace", collect_repo_files(repo_root))

    print("[blaxel] installing python runtime in James sandbox")
    install_python_runtime(blaxel, sandbox_url)

    print("[blaxel] installing Cosmic Mail dependencies in James sandbox")
    ensure_process_success(
        blaxel,
        sandbox_url,
        command=(
            "sh -lc "
            "\"cd /workspace && "
            "python3 -m venv /workspace/.venv && "
            ". /workspace/.venv/bin/activate && "
            "pip install --no-cache-dir -e .[dev]\""
        ),
        name="install-cosmic-mail-james-sandbox",
        timeout_seconds=900,
    )

    print("[blaxel] waiting for James SMTP and IMAP ports")
    ensure_process_success(
        blaxel,
        sandbox_url,
        command=(
            "sh -lc "
            "\"cd /workspace && "
            ". /workspace/.venv/bin/activate && "
            "python - <<'PY'\n"
            "import socket\n"
            "import time\n"
            "\n"
            "deadline = time.time() + 120\n"
            "ports = (25, 143)\n"
            "while time.time() < deadline:\n"
            "    ready = True\n"
            "    for port in ports:\n"
            "        try:\n"
            "            with socket.create_connection(('127.0.0.1', port), timeout=2):\n"
            "                pass\n"
            "        except OSError:\n"
            "            ready = False\n"
            "            break\n"
            "    if ready:\n"
            "        raise SystemExit(0)\n"
            "    time.sleep(2)\n"
            "raise SystemExit(1)\n"
            "PY\""
        ),
        name="wait-for-james-mail-ports",
        timeout_seconds=180,
    )

    print("[blaxel] running live James SMTP/IMAP smoke inside the James sandbox")
    ensure_process_success(
        blaxel,
        sandbox_url,
        command=(
            "sh -lc "
            "\"cd /workspace && "
            ". /workspace/.venv/bin/activate && "
            "python scripts/live_james_transport_smoke.py "
            "--admin-api-key smoke-admin-key "
            "--secret-key smoke-tests-only "
            "--james-webadmin-url http://127.0.0.1:8000 "
            "--smtp-host 127.0.0.1 "
            "--smtp-port 25 "
            "--imap-host 127.0.0.1 "
            "--imap-port 143\""
        ),
        name="live-james-transport-smoke",
        timeout_seconds=900,
    )
    print("[smoke] live James transport passed")


def install_python_runtime(blaxel: BlaxelClient, sandbox_url: str) -> None:
    ensure_process_success(
        blaxel,
        sandbox_url,
        command=(
            "sh -lc "
            "\"apk add --no-cache python3 py3-pip py3-setuptools py3-wheel py3-virtualenv "
            "gcc musl-dev libffi-dev openssl-dev cargo\""
        ),
        name="install-python-runtime",
        timeout_seconds=1200,
    )


def main() -> int:
    args = parse_args()
    api_key = require_env("BL_API_KEY")
    workspace = args.workspace
    if not workspace:
        raise RuntimeError("BL_WORKSPACE or --workspace must be set")

    suffix = uuid4().hex[:8]
    python_sandbox_name = f"cosmic-mail-py-{suffix}"
    james_sandbox_name = f"cosmic-mail-james-{suffix}"

    blaxel = BlaxelClient(api_key, workspace=workspace)
    cleanup_failures: list[str] = []
    try:
        run_python_linux_smoke(
            blaxel,
            repo_root=REPO_ROOT,
            sandbox_name=python_sandbox_name,
            image=args.python_image,
            region=args.region,
        )
        james_sandbox_url = start_or_wait_for_james(
            blaxel,
            repo_root=REPO_ROOT,
            sandbox_name=james_sandbox_name,
            image=args.james_image,
            region=args.region,
            api_key=api_key,
            workspace=workspace,
        )
        run_live_james_smoke_in_sandbox(
            blaxel,
            repo_root=REPO_ROOT,
            sandbox_url=james_sandbox_url,
        )
        return 0
    finally:
        print("[blaxel] cleaning up sandboxes")
        for sandbox_name in (james_sandbox_name, python_sandbox_name):
            try:
                blaxel.delete_sandbox(sandbox_name)
                print(f"[blaxel] deleted {sandbox_name}")
            except BlaxelError as exc:
                cleanup_failures.append(f"{sandbox_name}: {exc}")
                print(f"[blaxel] cleanup warning for {sandbox_name}: {exc}")
        blaxel.close()
        if cleanup_failures:
            raise RuntimeError(
                "one or more sandboxes could not be deleted: "
                + "; ".join(cleanup_failures)
            )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[smoke] failed: {exc}", file=sys.stderr)
        raise
