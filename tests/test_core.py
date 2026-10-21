import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def headers(user: str, tenant: str = "tenant-a", roles: str = "citizen") -> dict:
    return {
        "X-Internal-Secret": "test-secret",
        "X-DXOS-User": user,
        "X-DXOS-Tenant": tenant,
        "X-DXOS-Roles": roles,
    }


def test_data_tenant_and_owner_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'data.db'}")
    monkeypatch.setenv("INTERNAL_GATEWAY_SECRET", "test-secret")
    data = load_module("dxos_data_test", ROOT / "data/app/main.py")
    with TestClient(data.app) as client:
        assert client.get("/records").status_code == 403
        created = client.post("/records", json={"kind": "report", "payload": {"x": 1}}, headers=headers("alice"))
        assert created.status_code == 201
        record_id = created.json()["id"]
        assert client.get(f"/records/{record_id}", headers=headers("bob")).status_code == 404
        assert client.get(f"/records/{record_id}", headers=headers("operator", roles="operator")).status_code == 200
        assert client.get(f"/records/{record_id}", headers=headers("operator", "tenant-b", "operator")).status_code == 404
        assert len(client.get("/records", headers=headers("alice")).json()) == 1
        assert client.get("/records", headers=headers("bob")).json() == []


def test_workflow_rejects_wrong_role_and_records_history(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'workflow.db'}")
    monkeypatch.setenv("INTERNAL_GATEWAY_SECRET", "test-secret")
    monkeypatch.setenv("DEFINITIONS_DIR", str(ROOT / "workflow/definitions"))
    workflow = load_module("dxos_workflow_test", ROOT / "workflow/app/main.py")
    event.listen(workflow.engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"))
    with TestClient(workflow.app) as client:
        created = client.post(
            "/instances", json={"definition_key": "report-handling", "reference_id": "record-1"},
            headers=headers("alice"),
        )
        assert created.status_code == 201
        instance_id = created.json()["id"]
        route = f"/instances/{instance_id}/actions/triage"
        assert client.post(route, headers=headers("alice")).status_code == 403
        assert client.post(route, headers=headers("bob", "tenant-b", "operator")).status_code == 404
        advanced = client.post(route, headers=headers("operator", roles="operator"))
        assert advanced.status_code == 200
        assert advanced.json()["state"] == "triaged"
        detail = client.get(f"/instances/{instance_id}", headers=headers("alice"))
        assert [event["action"] for event in detail.json()["history"]] == ["start", "triage"]


def test_workflow_definition_validation(monkeypatch):
    monkeypatch.setenv("DEFINITIONS_DIR", str(ROOT / "workflow/definitions"))
    workflow = load_module("dxos_workflow_validation", ROOT / "workflow/app/main.py")
    definition = workflow.load_definitions(ROOT / "workflow/definitions")["report-handling"]
    with pytest.raises(ValueError, match="Duplicate action"):
        workflow.Definition.model_validate({
            **definition.model_dump(),
            "transitions": [definition.transitions[0].model_dump()] * 2,
        })


def test_gateway_requires_bearer_token(monkeypatch):
    gateway = load_module("dxos_gateway_test", ROOT / "gateway/app/main.py")
    with TestClient(gateway.app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/data/records").status_code == 401
        assert client.get("/api/not-a-service/records").status_code == 404


def test_gateway_validates_audience_and_client(monkeypatch):
    gateway = load_module("dxos_gateway_jwt_test", ROOT / "gateway/app/main.py")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        gateway, "JWK_CLIENT", SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key()))
    )
    claims = {
        "iss": gateway.ISSUER,
        "sub": "alice",
        "aud": gateway.API_AUDIENCE,
        "azp": "dxos-cli",
        "tenant_id": "tenant-a",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    make_token = lambda data: jwt.encode(data, key, algorithm="RS256")
    assert gateway.claims_from_authorization(f"Bearer {make_token(claims)}")["sub"] == "alice"
    with pytest.raises(HTTPException) as wrong_audience:
        gateway.claims_from_authorization(f"Bearer {make_token({**claims, 'aud': 'other'})}")
    assert wrong_audience.value.status_code == 401
    with pytest.raises(HTTPException) as wrong_client:
        gateway.claims_from_authorization(f"Bearer {make_token({**claims, 'azp': 'other'})}")
    assert wrong_client.value.status_code == 403
    with pytest.raises(HTTPException) as missing_tenant:
        gateway.claims_from_authorization(f"Bearer {make_token({key: value for key, value in claims.items() if key != 'tenant_id'})}")
    assert missing_tenant.value.status_code == 403


def test_gateway_replaces_forged_identity_headers(monkeypatch):
    gateway = load_module("dxos_gateway_headers_test", ROOT / "gateway/app/main.py")
    monkeypatch.setattr(gateway, "INTERNAL_SECRET", "test-secret")
    monkeypatch.setattr(gateway, "claims_from_authorization", lambda _: {
        "sub": "alice", "tenant_id": "tenant-a", "realm_access": {"roles": ["citizen"]}
    })
    captured = {}

    class FakeClient:
        def __init__(self, **_):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def request(self, method, url, **kwargs):
            captured.update(kwargs["headers"])
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(gateway.httpx, "AsyncClient", FakeClient)
    with TestClient(gateway.app) as client:
        response = client.get(
            "/api/data/records", headers={"Authorization": "Bearer test", "X-DXOS-User": "attacker"}
        )
    assert response.status_code == 200
    assert captured["X-DXOS-User"] == "alice"
    assert captured["X-Internal-Secret"] == "test-secret"

