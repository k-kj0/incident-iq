import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.router as router_mod
from backend import mount
from backend.settings import EMBED_DIM


def _vec(i: int) -> list[float]:
    v = [0.0] * EMBED_DIM
    v[i] = 1.0
    return v


def _fake_embed(text: str):
    return _vec(0) if "pool" in text else _vec(1)


def _fake_analyze(alert: dict) -> dict:
    cause = "Database connection pool exhaustion" if "pool" in alert["logs"] else "Other"
    return {"root_cause": cause, "confidence_score": 0.85, "severity": "high"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(router_mod, "embed", _fake_embed)
    app = FastAPI()
    mount(app, _fake_analyze)
    return TestClient(app)


def _post(client, logs, tenant="demo_corp", key="demo-key-123"):
    return client.post("/api/v2/analyze", json={
        "alert": {"service": f"svc-{uuid.uuid4().hex[:6]}", "error": "timeout", "logs": logs},
        "tenant_id": tenant, "api_key": key,
    })


def test_ready(client):
    assert client.get("/api/v2/ready").json() == {"status": "ready"}


def test_bad_key_rejected(client):
    assert _post(client, "x", key="wrong").status_code == 401


def test_cross_tenant_key_rejected(client):
    assert _post(client, "x", tenant="test_inc", key="demo-key-123").status_code == 401


def test_analyze_persists_and_lists(client):
    r = _post(client, "database connection pool exhausted")
    assert r.status_code == 200
    items = client.get("/api/v2/incidents",
                       params={"tenant_id": "demo_corp", "api_key": "demo-key-123",
                               "limit": 5}).json()["items"]
    assert any(i["incident_id"] == r.json()["incident_id"] for i in items)


def test_similar_returns_closest_first(client):
    pool = _post(client, "database connection pool exhausted").json()["incident_id"]
    _post(client, "disk is full")
    res = client.post("/api/v2/incidents/similar", json={
        "tenant_id": "demo_corp", "api_key": "demo-key-123",
        "query": "pool exhausted again", "k": 3,
    }).json()
    assert res["mode"] == "vector"
    assert res["items"][0]["root_cause"] == "Database connection pool exhaustion"
    assert any(i["incident_id"] == pool for i in res["items"])
