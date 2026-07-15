"""Tests for jarvis.dashboard_html and dashboard API endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jarvis.court.court import Court
from jarvis.court_api import create_app


# ══════════════════════════════════════════════════════════════════
# Dashboard HTML
# ══════════════════════════════════════════════════════════════════


class TestDashboardHtml:
    def test_generate_html_returns_html(self):
        from jarvis.dashboard_html import generate_html
        html = generate_html()
        assert "<!DOCTYPE html>" in html
        assert "<title>Emperor Dashboard</title>" in html
        assert "Emperor Dashboard" in html

    def test_generate_html_injects_api_base(self):
        from jarvis.dashboard_html import generate_html
        html = generate_html(api_base="http://localhost:9999")
        assert "http://localhost:9999" in html
        assert "var API = " in html

    def test_generate_html_is_self_contained(self):
        from jarvis.dashboard_html import generate_html
        html = generate_html()
        # No external resource references
        assert 'src="http' not in html
        assert 'href="http' not in html
        # Contains inline styles and script
        assert "<style>" in html
        assert "<script>" in html


# ══════════════════════════════════════════════════════════════════
# Dashboard API endpoint
# ══════════════════════════════════════════════════════════════════


class TestDashboardApi:
    @pytest.fixture
    def client(self):
        court = Court()
        app = create_app(court=court)
        app.extra["host"] = "127.0.0.1"
        app.extra["port"] = 9999
        return TestClient(app)

    def test_dashboard_returns_html(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "Emperor Dashboard" in resp.text
        assert "127.0.0.1:9999" in resp.text

    def test_dashboard_status_empty_court(self, client):
        resp = client.get("/dashboard/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "court" in data
        assert "ministers" in data
        assert "tasks" in data
        assert "config" in data
        assert data["court"]["active_ministers"] >= 0
        assert data["court"]["cycle"] >= 0
        assert isinstance(data["ministers"], list)
        assert data["scheduler_running"] is False

    def test_dashboard_status_with_ministers(self, client):
        # Register some ministers
        client.post("/court/register", json={
            "name": "alice", "domain": "math", "temperature": 0.5,
        })
        client.post("/court/register", json={
            "name": "bob", "domain": "science", "temperature": 0.7,
        })
        client.post("/court/register", json={
            "name": "carol", "domain": "math", "temperature": 0.9,
        })

        resp = client.get("/dashboard/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["court"]["active_ministers"] == 3
        ministers = data["ministers"]
        assert len(ministers) == 3
        names = [m["name"] for m in ministers]
        assert "alice" in names
        assert "bob" in names
        assert "carol" in names

    def test_dashboard_status_sorted_by_merit(self, client):
        from jarvis.court.court import CourtConfig
        court = Court(config=CourtConfig(min_ministers=3))
        court.register("a", domain="math")
        court.register("b", domain="science")
        court.register("c", domain="literature")
        # Simulate some merit by evolving
        court.evolve(2)

        app2 = create_app(court=court)
        app2.extra["host"] = "127.0.0.1"
        app2.extra["port"] = 9999
        cli = TestClient(app2)

        resp = cli.get("/dashboard/status")
        data = resp.json()
        ministers = data["ministers"]
        # Sorted descending by merit
        merits = [m["merit"] for m in ministers]
        assert merits == sorted(merits, reverse=True)

    def test_dashboard_status_scheduler_info(self, client):
        # By default no scheduler info
        resp = client.get("/dashboard/status")
        data = resp.json()
        assert data["scheduler_running"] is False
        assert data["scheduler_jobs"] == 0
        assert data["scheduler_total_runs"] == 0
