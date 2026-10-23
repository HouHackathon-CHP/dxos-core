# SPDX-License-Identifier: Apache-2.0
"""Provision local demo users and exercise all four core capabilities.

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


def ensure_tenant_mapper(admin: str) -> None:
    base = f"{IDENTITY}/admin/realms/dxos"
    status, clients = request("GET", f"{base}/clients?clientId=dxos-cli", token=admin)
    require(status, 200, clients)
    if len(clients) != 1:
        raise RuntimeError("Expected one dxos-cli client")
    client_id = clients[0]["id"]
    url = f"{base}/clients/{client_id}/protocol-mappers/models"
    status, mappers = request("GET", url, token=admin)
    require(status, 200, mappers)
    if any(mapper["name"] == "dxos-tenant-id" for mapper in mappers):
        return
    status, result = request("POST", url, token=admin, data={
        "name": "dxos-tenant-id",
        "protocol": "openid-connect",
        "protocolMapper": "oidc-usermodel-attribute-mapper",
        "consentRequired": False,
        "config": {
            "user.attribute": "tenant_id", "claim.name": "tenant_id",
            "jsonType.label": "String", "access.token.claim": "true",
            "id.token.claim": "false", "userinfo.token.claim": "false",
        },
    })
    require(status, 201, result)


def ensure_tenant_profile(admin: str) -> None:
    """Register tenant_id as a managed attribute before assigning users to tenants."""
    url = f"{IDENTITY}/admin/realms/dxos/users/profile"
    status, profile = request("GET", url, token=admin)
    require(status, 200, profile)
    if any(attribute["name"] == "tenant_id" for attribute in profile["attributes"]):
        return
    profile["attributes"].append({
        "name": "tenant_id",
        "displayName": "Tenant ID",
        "permissions": {"view": ["admin", "user"], "edit": ["admin"]},
    })
    status, result = request("PUT", url, token=admin, data=profile)
    require(status, 200, result)


def ensure_web_client(admin: str) -> None:
    """Provision the separate browser client on existing local realms."""
    base = f"{IDENTITY}/admin/realms/dxos"
    definition = next(
        client for client in json.loads((ROOT / "identity/realm.json").read_text(encoding="utf-8"))["clients"]
        if client["clientId"] == "dxos-web"
    )
    url = f"{base}/clients?clientId=dxos-web"
    status, clients = request("GET", url, token=admin)
    require(status, 200, clients)
    if not clients:
        status, result = request("POST", f"{base}/clients", token=admin, data=definition)
        require(status, 201, result)
        status, clients = request("GET", url, token=admin)
        require(status, 200, clients)
    if len(clients) != 1:
        raise RuntimeError("Expected one dxos-web client")
    client_id = clients[0]["id"]
    status, current = request("GET", f"{base}/clients/{client_id}", token=admin)
    require(status, 200, current)
    if not (current.get("publicClient") and current.get("standardFlowEnabled")) or current.get(
        "directAccessGrantsEnabled"
    ) or current.get("attributes", {}).get("pkce.code.challenge.method") != "S256":
        raise RuntimeError("Browser client does not require Authorization Code + PKCE S256")
    if current.get("redirectUris") != ["http://localhost:3000/*"] or current.get(
        "webOrigins"
    ) != ["http://localhost:3000"]:
        raise RuntimeError("Browser client origins differ from the local configuration")
    status, mappers = request(
        "GET", f"{base}/clients/{client_id}/protocol-mappers/models", token=admin
    )
    require(status, 200, mappers)
    if not {"dxos-api-audience", "dxos-tenant-id"}.issubset({item["name"] for item in mappers}):
        raise RuntimeError("Browser access tokens lack the API audience or tenant mapper")


def ensure_user(admin: str, username: str, password: str, role: str, tenant: str) -> None:
    base = f"{IDENTITY}/admin/realms/dxos"
    status, users = request("GET", f"{base}/users?{urlencode({'username': username, 'exact': 'true'})}", token=admin)
    require(status, 200, users)
    if not users:
        status, result = request("POST", f"{base}/users", token=admin, data={
            "username": username, "enabled": True,
            "firstName": "DXOS", "lastName": "Demo",
            "email": f"{username}@example.invalid", "emailVerified": True,
            "requiredActions": [],
            "attributes": {"tenant_id": [tenant]},
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
        "attributes": {"tenant_id": [tenant]},
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
    ensure_tenant_mapper(admin)
    ensure_tenant_profile(admin)
    ensure_web_client(admin)
    preflight = Request(
        f"{GATEWAY}/api/data/records", method="OPTIONS", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    with urlopen(preflight, timeout=20) as response:
        if response.status != 200 or response.headers.get("Access-Control-Allow-Origin") != "http://localhost:3000":
            raise RuntimeError("Browser gateway CORS preflight failed")
    blocked_preflight = Request(
        f"{GATEWAY}/api/data/records", method="OPTIONS", headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    try:
        urlopen(blocked_preflight, timeout=20)
    except HTTPError as exc:
        if exc.code != 400:
            raise RuntimeError(f"Unexpected CORS response for another origin: {exc.code}") from exc
    else:
        raise RuntimeError("Gateway allowed another browser origin")
    ensure_user(admin, "dxos-citizen", values["DEMO_CITIZEN_PASSWORD"], "citizen", "demo")
    ensure_user(admin, "dxos-operator", values["DEMO_OPERATOR_PASSWORD"], "operator", "demo")
    ensure_user(admin, "dxos-outsider", values["DEMO_OUTSIDER_PASSWORD"], "citizen", "other")
    citizen = token("dxos-citizen", values["DEMO_CITIZEN_PASSWORD"], "dxos-cli")
    operator = token("dxos-operator", values["DEMO_OPERATOR_PASSWORD"], "dxos-cli")
    outsider = token("dxos-outsider", values["DEMO_OUTSIDER_PASSWORD"], "dxos-cli")

    status, record = request("POST", f"{GATEWAY}/api/data/records", token=citizen, data={
        "kind": "environment-report",
        "payload": {"title": "Sample report", "location": {"lat": 21.02, "lon": 105.85}},
    })
    require(status, 201, record)
    record_id = record["id"]
    status, _ = request("GET", f"{GATEWAY}/api/data/records/{record_id}", token=outsider)
    if status != 404:
        raise RuntimeError(f"Cross-tenant record access was not blocked: HTTP {status}")
    status, updated = request("PATCH", f"{GATEWAY}/api/data/records/{record_id}", token=citizen, data={
        "payload": {"title": "Sample report updated", "location": {"lat": 21.02, "lon": 105.85}},
    })
    require(status, 200, updated)
    status, history = request("GET", f"{GATEWAY}/api/data/records/{record_id}/history", token=citizen)
    require(status, 200, history)
    if [event["action"] for event in history] != ["create", "update"]:
        raise RuntimeError("Record change history is incomplete")
    status, _ = request("GET", f"{GATEWAY}/api/data/records/{record_id}/history", token=outsider)
    if status != 404:
        raise RuntimeError(f"Cross-tenant record history access was not blocked: HTTP {status}")

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
    status, _ = request("GET", f"{GATEWAY}/api/data/objects/{stored['id']}", token=outsider)
    if status != 404:
        raise RuntimeError(f"Cross-tenant object access was not blocked: HTTP {status}")

    status, instance = request("POST", f"{GATEWAY}/api/workflow/instances", token=citizen, data={
        "definition_key": "report-handling", "reference_id": record_id,
    })
    require(status, 201, instance)
    instance_id = instance["id"]
    status, _ = request("GET", f"{GATEWAY}/api/workflow/instances/{instance_id}", token=outsider)
    if status != 404:
        raise RuntimeError(f"Cross-tenant workflow access was not blocked: HTTP {status}")
    status, _ = request(
        "POST", f"{GATEWAY}/api/workflow/instances/{instance_id}/actions/triage", token=outsider
    )
    if status != 404:
        raise RuntimeError(f"Cross-tenant workflow action was not blocked: HTTP {status}")
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
