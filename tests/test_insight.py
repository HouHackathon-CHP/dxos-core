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
    assert data["model_version"] in {"phobert-base-v2-multitask-civic", "phobert-base-v2-civic-12labels", "multinomial-nb-bow-v1"}
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


def test_spatiotemporal_deduplication(monkeypatch):
    client = insight_client(monkeypatch)
    payload = {
        "text": "Ổ gà sâu nguy hiểm gây ngã xe trên đường",
        "labels": ["infrastructure", "transport"],
        "examples": [
            {"label": "infrastructure", "text": "Mặt đường hư hỏng ổ gà"},
            {"label": "transport", "text": "Xe cộ ùn tắc giao thông"},
        ],
        "latitude": 21.0285,
        "longitude": 105.8542,
        "created_at": "2026-11-13T10:00:00Z",
        "candidates": [
            # Candidate 1: Nearby (approx 20m) & within 1 hour -> should be matched as duplicate
            {
                "id": "cand-nearby",
                "text": "Ổ gà sâu nguy hiểm té ngã người đi đường",
                "latitude": 21.0286,
                "longitude": 105.8543,
                "created_at": "2026-11-13T11:00:00Z",
            },
            # Candidate 2: Identical text but in Ho Chi Minh City (>1000km away) -> must NOT be duplicate
            {
                "id": "cand-far-away",
                "text": "Ổ gà sâu nguy hiểm gây ngã xe trên đường",
                "latitude": 10.7769,
                "longitude": 106.7009,
                "created_at": "2026-11-13T10:05:00Z",
            },
        ],
    }
    result = client.post("/analyze", json=payload, headers=HEADERS)
    assert result.status_code == 200
    data = result.json()
    matched_ids = [item["id"] for item in data["similar"]]
    assert "cand-nearby" in matched_ids
    assert "cand-far-away" not in matched_ids


def test_urgency_classification_support(monkeypatch):
    client = insight_client(monkeypatch)
    payload = {
        "text": "Chập cháy cột điện nổ lớn đe dọa tính mạng người dân xung quanh khẩn cấp",
        "labels": ["high", "normal", "low"],
        "examples": [
            {"label": "high", "text": "Cháy nổ dây điện đứt nguy hiểm tính mạng"},
            {"label": "normal", "text": "Đèn đường hỏng cần bảo trì"},
            {"label": "low", "text": "Đề xuất làm đẹp cảnh quan"},
        ],
    }
    result = client.post("/analyze", json=payload, headers=HEADERS)
    assert result.status_code == 200
    data = result.json()
    assert len(data["ranked_labels"]) == 3
    assert data["ranked_labels"][0]["label"] == "high"

