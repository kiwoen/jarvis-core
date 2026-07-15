"""Tests for the Court REST API (FastAPI test client).

Validates all endpoints: registration, evolution, inspection,
dispatch recording, feedback, and genome persistence.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from jarvis.court_api import app
from jarvis.court.court import CourtConfig


@pytest.fixture
def client():
    return TestClient(app)


# ══════════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════════

class TestHealth:
    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

    def test_summary_empty(self, client):
        r = client.get("/court/summary")
        assert r.status_code == 200
        assert "summary" in r.json()

    def test_snapshot_empty(self, client):
        r = client.get("/court/snapshot")
        assert r.status_code == 200
        assert r.json()["total_ministers"] == 0


# ══════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════

class TestAPIRegistration:
    def test_register_single(self, client):
        r = client.post("/court/register", json={
            "name": "curie", "domain": "physics", "temperature": 0.3,
        })
        assert r.status_code == 200
        assert r.json()["name"] == "curie"

    def test_register_auto_name(self, client):
        r = client.post("/court/register", json={"domain": "code"})
        assert r.status_code == 200
        assert r.json()["name"].startswith("m")

    def test_register_batch(self, client):
        r = client.post("/court/register/batch", json={
            "ministers": [
                {"domain": "math"},
                {"name": "turing", "domain": "code"},
            ],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2
        assert "turing" in data["names"]
        # auto-named minister starts with "m"
        other = [n for n in data["names"] if n != "turing"][0]
        assert other.startswith("m")

    def test_list_ministers_after_register(self, client):
        client.post("/court/register", json={"name": "einstein", "domain": "physics"})
        r = client.get("/court/ministers")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1

    def test_minister_detail(self, client):
        client.post("/court/register", json={"name": "newton", "domain": "physics"})
        r = client.get("/court/minister/newton")
        assert r.status_code == 200
        assert "newton" in r.json()["detail"]

    def test_minister_not_found(self, client):
        r = client.get("/court/minister/nobody")
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════
# Evolution
# ══════════════════════════════════════════════════════════════════

class TestAPIEvolution:
    def test_evolve_single(self, client):
        client.post("/court/register/batch", json={
            "ministers": [
                {"domain": "math"},
                {"domain": "code"},
                {"name": "curie", "domain": "physics"},
            ],
        })
        r = client.post("/court/evolve", json={"cycles": 1})
        assert r.status_code == 200
        data = r.json()
        assert data["total_cycles"] == 1

    def test_evolve_multiple(self, client):
        client.post("/court/register/batch", json={
            "ministers": [
                {"domain": "math"},
                {"domain": "code"},
                {"name": "curie", "domain": "physics"},
            ],
        })
        r = client.post("/court/evolve", json={"cycles": 3})
        assert r.status_code == 200
        data = r.json()
        assert data["total_cycles"] == 3
        assert len(data["cycles"]) == 3

    def test_history_after_evolution(self, client):
        client.post("/court/register/batch", json={
            "ministers": [
                {"domain": "math"},
                {"domain": "code"},
                {"name": "curie", "domain": "physics"},
            ],
        })
        client.post("/court/evolve", json={"cycles": 2})
        r = client.get("/court/history")
        assert r.status_code == 200
        data = r.json()
        assert data["cycles"] >= 2


# ══════════════════════════════════════════════════════════════════
# Dispatch & Feedback
# ══════════════════════════════════════════════════════════════════

class TestAPIDispatch:
    def test_record_dispatch(self, client):
        client.post("/court/register", json={"name": "alpha", "domain": "math"})
        r = client.post("/court/dispatch", json={
            "minister": "alpha",
            "edict_id": "e1",
            "intent": "solve equation",
            "success": True,
            "confidence": 0.95,
            "execution_time_ms": 120.0,
        })
        assert r.status_code == 200

    def test_record_feedback(self, client):
        client.post("/court/register", json={"name": "beta", "domain": "code"})
        client.post("/court/dispatch", json={
            "minister": "beta",
            "edict_id": "e2",
            "intent": "write function",
            "success": True,
            "confidence": 0.88,
        })
        r = client.post("/court/feedback", json={
            "minister": "beta", "edict_id": "e2", "score": 0.95,
        })
        assert r.status_code == 200

    def test_feedback_not_found(self, client):
        r = client.post("/court/feedback", json={
            "minister": "ghost", "edict_id": "nx", "score": 0.5,
        })
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════
# Genome persistence
# ══════════════════════════════════════════════════════════════════

class TestAPIPersistence:
    def test_save_no_path_configured(self, client):
        client.post("/court/register", json={"name": "x", "domain": "math"})
        r = client.post("/court/genomes/save")
        assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════════════════════════

class TestAPIValidation:
    def test_evolve_zero_cycles_rejected(self, client):
        r = client.post("/court/evolve", json={"cycles": 0})
        assert r.status_code == 422

    def test_temperature_out_of_range(self, client):
        r = client.post("/court/register", json={
            "name": "hot", "temperature": 99.0,
        })
        assert r.status_code == 422
