# SPDX-License-Identifier: Apache-2.0
"""The internal classifier has a bounded, authenticated contract."""

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient


def insight_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("INTERNAL_GATEWAY_SECRET", "test-secret")
    path = Path(__file__).resolve().parents[1] / "insight/app/main.py"
    spec = importlib.util.spec_from_file_location("dxos_insight_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return TestClient(module.app)


HEADERS = {
    "X-Internal-Secret": "test-secret",
    "X-DXOS-Tenant": "tenant-a",
    "X-DXOS-User": "dispatcher-a",
}
BODY = {
    "text": "Đèn đường hỏng và không sáng",
    "labels": ["infrastructure", "environment"],
    "examples": [
        {"label": "infrastructure", "text": "Đèn đường hỏng không sáng"},
        {"label": "infrastructure", "text": "Cột đèn chiếu sáng cần sửa"},
        {"label": "environment", "text": "Rác thải và cây xanh"},
        {"label": "environment", "text": "Thu gom rác thải trên phố"},
    ],
    "candidates": [
        {"id": "same", "text": "Đèn đường hỏng và không sáng"},
        {"id": "other", "text": "Rác thải chất đống"},
    ],
}


def test_insight_requires_internal_context_and_ranks_text(monkeypatch):
    client = insight_client(monkeypatch)
    assert client.get("/health").status_code == 200
    assert client.post("/analyze", json=BODY).status_code == 403
    assert client.post("/analyze", json=BODY, headers={"X-Internal-Secret": "test-secret"}).status_code == 403
    result = client.post("/analyze", json=BODY, headers=HEADERS)
    assert result.status_code == 200
    data = result.json()
    assert data["model_version"] in {"phobert-base-v2-civic-12labels", "multinomial-nb-bow-v1"}
    assert data["ranked_labels"][0]["label"] == "infrastructure"
    assert "đèn" in data["signals"]
    assert data["similar"] == [{"id": "same", "similarity": 1.0}]


def test_insight_rejects_unbounded_or_wrong_labels(monkeypatch):
    client = insight_client(monkeypatch)
    assert client.post("/analyze", json={**BODY, "labels": ["infrastructure", "infrastructure"]},
                       headers=HEADERS).status_code == 422
    assert client.post("/analyze", json={**BODY, "examples": BODY["examples"] +
                       [{"label": "transport", "text": "Xe buýt bị chậm"}]}, headers=HEADERS).status_code == 422
    assert client.post("/analyze", json={**BODY, "text": "x" * 4001}, headers=HEADERS).status_code == 422


def test_unseen_words_do_not_bias_a_label(monkeypatch):
    client = insight_client(monkeypatch)
    result = client.post("/analyze", json={**BODY, "text": "xyzzy plugh qwerty"}, headers=HEADERS)
    assert result.status_code == 200
    assert result.json()["signals"] == []
    assert {item["score"] for item in result.json()["ranked_labels"]} == {0.5}
