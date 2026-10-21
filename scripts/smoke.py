"""Provision two local demo users and exercise all four core capabilities.

Run only against the localhost Docker Compose environment. Values come from .env.
"""

import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
IDENTITY = "http://localhost:8081"
GATEWAY = "http://localhost:8000"


def read_env() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def request(method: str, url: str, *, data=None, token=None, content_type=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None and content_type:
        headers["Content-Type"] = content_type
    body = data
    if isinstance(data, (dict, list)):
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=20) as response:
            content = response.read()
            return response.status, json.loads(content) if content and "json" in response.headers.get("Content-Type", "") else content
    except HTTPError as exc:
        content = exc.read()
        return exc.code, json.loads(content) if content and "json" in exc.headers.get("Content-Type", "") else content


def require(status: int, expected: int, result):
    if status != expected:
        raise RuntimeError(f"Expected HTTP {expected}; got {status}: {result}")
    return result


def wait_for(url: str):
    for _ in range(60):
        try:
            status, _ = request("GET", url)
            if status == 200:
                return
        except (URLError, OSError):
            pass
        time.sleep(2)
    raise RuntimeError(f"Service did not become ready: {url}")


def token(username: str, password: str, client_id: str, realm: str = "dxos") -> str:
    form = urlencode({
        "grant_type": "password",
        "client_id": client_id,
        "username": username,
        "password": password,
    }).encode("utf-8")
    status, result = request(
        "POST", f"{IDENTITY}/realms/{realm}/protocol/openid-connect/token",
        data=form, content_type="application/x-www-form-urlencoded",
    )
    return require(status, 200, result)["access_token"]


def admin_token(password: str) -> str:
    return token("admin", password, "admin-cli", realm="master")


def ensure_user(admin: str, username: str, password: str, role: str) -> None:
    base = f"{IDENTITY}/admin/realms/dxos"
    status, users = request("GET", f"{base}/users?{urlencode({'username': username, 'exact': 'true'})}", token=admin)
    require(status, 200, users)
    if not users:
        status, result = request("POST", f"{base}/users", token=admin, data={
            "username": username, "enabled": True,
            "firstName": "DXOS", "lastName": "Demo",
            "email": f"{username}@example.invalid", "emailVerified": True,
            "requiredActions": [],
            "credentials": [{"type": "password", "value": password, "temporary": False}],
        })
        require(status, 201, result)
        status, users = request("GET", f"{base}/users?{urlencode({'username': username, 'exact': 'true'})}", token=admin)
        require(status, 200, users)
    user_id = users[0]["id"]
    status, result = request("PUT", f"{base}/users/{user_id}", token=admin, data={
        "username": username, "enabled": True,
        "firstName": "DXOS", "lastName": "Demo",
        "email": f"{username}@example.invalid", "emailVerified": True,
        "requiredActions": [],
    })
    require(status, 204, result)
    status, result = request("PUT", f"{base}/users/{user_id}/reset-password", token=admin, data={
        "type": "password", "value": password, "temporary": False,
    })
    require(status, 204, result)
    status, role_data = request("GET", f"{base}/roles/{role}", token=admin)
    require(status, 200, role_data)
    status, result = request(
        "POST", f"{base}/users/{user_id}/role-mappings/realm", token=admin, data=[role_data]
    )
    require(status, 204, result)


def multipart_file(content: bytes, filename: str = "report.txt") -> tuple[bytes, str]:
    boundary = "dxos-smoke-test-boundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/plain\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return body, f"multipart/form-data; boundary={boundary}"


def main() -> None:
    values = read_env()
    wait_for(f"{IDENTITY}/realms/dxos/.well-known/openid-configuration")
    wait_for(f"{GATEWAY}/health")
    admin = admin_token(values["KEYCLOAK_ADMIN_PASSWORD"])
    ensure_user(admin, "dxos-citizen", values["DEMO_CITIZEN_PASSWORD"], "citizen")
    ensure_user(admin, "dxos-operator", values["DEMO_OPERATOR_PASSWORD"], "operator")
    citizen = token("dxos-citizen", values["DEMO_CITIZEN_PASSWORD"], "dxos-cli")
    operator = token("dxos-operator", values["DEMO_OPERATOR_PASSWORD"], "dxos-cli")

    status, record = request("POST", f"{GATEWAY}/api/data/records", token=citizen, data={
        "kind": "environment-report",
        "payload": {"title": "Sample report", "location": {"lat": 21.02, "lon": 105.85}},
    })
    require(status, 201, record)
    record_id = record["id"]

    body, content_type = multipart_file(b"DX-OS demo attachment")
    status, stored = request(
        "POST", f"{GATEWAY}/api/data/objects?record_id={record_id}",
        token=citizen, data=body, content_type=content_type,
    )
    require(status, 201, stored)
    status, downloaded = request("GET", f"{GATEWAY}/api/data/objects/{stored['id']}", token=citizen)
    require(status, 200, downloaded)
    if downloaded != b"DX-OS demo attachment":
        raise RuntimeError("Object round-trip failed")

    status, instance = request("POST", f"{GATEWAY}/api/workflow/instances", token=citizen, data={
        "definition_key": "report-handling", "reference_id": record_id,
    })
    require(status, 201, instance)
    instance_id = instance["id"]
    status, _ = request(
        "POST", f"{GATEWAY}/api/workflow/instances/{instance_id}/actions/triage", token=citizen
    )
    if status != 403:
        raise RuntimeError(f"Citizen was unexpectedly allowed to triage: HTTP {status}")
    for action, expected_state in (("triage", "triaged"), ("assign", "assigned"), ("resolve", "resolved")):
        status, result = request(
            "POST", f"{GATEWAY}/api/workflow/instances/{instance_id}/actions/{action}", token=operator
        )
        require(status, 200, result)
        if result["state"] != expected_state:
            raise RuntimeError(f"Workflow state mismatch after {action}")
    status, result = request("GET", f"{GATEWAY}/api/workflow/instances/{instance_id}", token=citizen)
    require(status, 200, result)
    if len(result["history"]) != 4:
        raise RuntimeError("Workflow history is incomplete")
    print(f"PASS: SSO, gateway, records, object storage and workflow; record={record_id}; instance={instance_id}")


if __name__ == "__main__":
    main()

