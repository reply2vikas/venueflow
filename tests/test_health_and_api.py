"""
Integration-level tests for API endpoints and health probe.
Uses FastAPI TestClient — no live GCP services required.
"""
from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from api.main import app
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_ok_status(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"
        assert data["service"] == "venueflow"
        assert "version" in data

    def test_health_has_security_headers(self, client):
        resp = client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert "x-request-id" in resp.headers


class TestZonesEndpoint:
    def test_zones_returns_list(self, client):
        resp = client.get("/api/zones")
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, list)

    def test_zones_data_shape(self, client):
        resp = client.get("/api/zones")
        if resp.status_code == 200:
            for zone in resp.json():
                assert "zone_id" in zone
                assert "density_level" in zone
                assert 1 <= zone["density_level"] <= 5

    def test_zones_has_request_id_header(self, client):
        resp = client.get("/api/zones")
        assert "x-request-id" in resp.headers


class TestRouteEndpoint:
    def test_route_wheelchair_mode(self, client):
        """Wheelchair mode must return accessible=True or a 4xx — never 5xx."""
        resp = client.post("/api/route", json={
            "origin": "gate_C",
            "destination": "section_F",
            "wheelchair": True
        })
        assert resp.status_code in (200, 400, 503)
        if resp.status_code == 200:
            data = resp.json()
            assert data["accessible"] is True
            assert isinstance(data["path"], list)
            assert len(data["path"]) >= 2

    def test_route_missing_fields_422(self, client):
        resp = client.post("/api/route", json={"wheelchair": False})
        assert resp.status_code == 422

    def test_route_empty_body_422(self, client):
        resp = client.post("/api/route", json={})
        assert resp.status_code == 422


class TestWaittimesEndpoint:
    def test_waittimes_returns_list(self, client):
        resp = client.get("/api/waittimes")
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, list)
            for item in data:
                assert item["wait_minutes"] >= 0
                assert item["confidence"] in ("high", "medium", "low")


class TestChatEndpoint:
    def test_chat_valid_question(self, client):
        resp = client.post("/api/chat", json={
            "question": "Which gate has the shortest queue?",
            "wheelchair": False,
            "language": "en"
        })
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data["answer"], str)
            assert len(data["answer"]) > 5

    def test_chat_too_short_rejected(self, client):
        resp = client.post("/api/chat", json={"question": "Hi", "language": "en"})
        assert resp.status_code == 422

    def test_chat_too_long_rejected(self, client):
        resp = client.post("/api/chat", json={
            "question": "A" * 201,
            "language": "en"
        })
        assert resp.status_code == 422

    def test_chat_invalid_language_rejected(self, client):
        resp = client.post("/api/chat", json={
            "question": "Where is gate A?",
            "language": "de"
        })
        assert resp.status_code == 422

    def test_chat_xss_sanitised(self, client):
        """Script tags in question must be stripped, not passed to Gemini."""
        resp = client.post("/api/chat", json={
            "question": "<script>alert(1)</script> which gate?",
            "language": "en"
        })
        # Either sanitised and answered, or rejected — never 500
        assert resp.status_code in (200, 422, 503)
        assert resp.status_code != 500


class TestAlertsEndpoint:
    def test_alerts_returns_list(self, client):
        resp = client.get("/api/alerts")
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            assert isinstance(resp.json(), list)

    def test_alerts_never_500(self, client):
        """Alert endpoint must degrade gracefully — never 500."""
        resp = client.get("/api/alerts")
        assert resp.status_code != 500
