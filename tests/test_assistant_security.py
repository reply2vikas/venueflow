"""
Tests for AI assistant, security, and translation services.
All external Google APIs are mocked — runs fully offline.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch


# ── Gemini assistant tests ────────────────────────────────────────────────────

class TestGeminiAssistant:

    @pytest.mark.asyncio
    async def test_falls_back_gracefully_when_vertex_unavailable(self, mock_zones_mixed):
        """When Vertex AI is unavailable, rule-based fallback must return a string."""
        from api.services.gemini_assistant import ask_gemini
        zone_dicts = [
            {"zone_id": z.zone_id, "density_level": z.density_level,
             "wait_time_minutes": z.wait_time_minutes}
            for z in mock_zones_mixed
        ]
        # vertexai not installed in test env — triggers fallback
        result = await ask_gemini("Where is the nearest restroom?", zone_dicts)
        assert isinstance(result, str)
        assert len(result) > 10

    @pytest.mark.asyncio
    async def test_food_question_redirects_away_from_packed_zone(self, mock_zones_mixed):
        """Food court at density 5 → fallback should suggest alternatives."""
        from api.services.gemini_assistant import _rule_based_fallback
        zone_dicts = [
            {"zone_id": z.zone_id, "density_level": z.density_level,
             "wait_time_minutes": z.wait_time_minutes}
            for z in mock_zones_mixed
        ]
        result = _rule_based_fallback("Where should I get food?", zone_dicts)
        assert "packed" in result.lower() or "gate" in result.lower() or "food" in result.lower()

    @pytest.mark.asyncio
    async def test_exit_question_returns_accessible_guidance(self, mock_zones_mixed):
        from api.services.gemini_assistant import _rule_based_fallback
        zone_dicts = [{"zone_id": z.zone_id, "density_level": z.density_level,
                       "wait_time_minutes": z.wait_time_minutes} for z in mock_zones_mixed]
        result = _rule_based_fallback("How do I get out?", zone_dicts)
        assert "accessible" in result.lower() or "exit" in result.lower() or "north" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_zones_returns_fallback_message(self):
        from api.services.gemini_assistant import ask_gemini
        result = await ask_gemini("What is going on?", zone_context=[])
        assert isinstance(result, str)
        assert len(result) > 5

    @pytest.mark.asyncio
    async def test_input_sanitisation_in_route_endpoint(self, mock_zones_mixed):
        """HTML injection in question should be sanitised before reaching model."""
        from api.routes.assistant import ChatRequest
        from pydantic import ValidationError
        try:
            req = ChatRequest(
                question="<script>alert('xss')</script> Where is gate A?",
                wheelchair=False,
                language="en",
            )
            # Should sanitise — script tags removed
            assert "<script>" not in req.question
        except ValidationError:
            pass  # Also acceptable — strict validation


# ── Security middleware tests ─────────────────────────────────────────────────

class TestSecurityMiddleware:

    def test_security_headers_present_on_zone_response(self, client):
        resp = client.get("/api/zones")
        assert resp.status_code in (200, 503)
        # These headers MUST be present on every response
        assert "x-content-type-options" in resp.headers
        assert resp.headers["x-content-type-options"] == "nosniff"

    def test_xframe_options_deny(self, client):
        resp = client.get("/api/zones")
        assert "x-frame-options" in resp.headers
        assert resp.headers["x-frame-options"] == "DENY"

    def test_x_request_id_present(self, client):
        resp = client.get("/api/zones")
        assert "x-request-id" in resp.headers
        # UUID format: 8-4-4-4-12
        rid = resp.headers["x-request-id"]
        assert len(rid) == 36
        assert rid.count("-") == 4

    def test_rate_limit_header_present(self, client):
        resp = client.get("/api/zones")
        assert "x-ratelimit-limit" in resp.headers

    def test_invalid_route_input_rejected(self, client):
        """POST /api/route with empty body → 422 Unprocessable Entity."""
        resp = client.post("/api/route", json={})
        assert resp.status_code == 422

    def test_oversized_question_rejected(self, client):
        """Chat question over 200 chars → 422."""
        resp = client.post("/api/chat", json={
            "question": "A" * 201,
            "wheelchair": False,
            "language": "en"
        })
        assert resp.status_code == 422

    def test_invalid_language_rejected(self, client):
        """Language code not in [en, kn, hi, ta] → 422."""
        resp = client.post("/api/chat", json={
            "question": "Where is gate A?",
            "wheelchair": False,
            "language": "fr"   # French not supported
        })
        assert resp.status_code == 422


# ── Translation service tests ─────────────────────────────────────────────────

class TestTranslation:

    @pytest.mark.asyncio
    async def test_english_passthrough_unchanged(self):
        from api.services.translation import translate_text
        result = await translate_text("Gate A is clear", "en")
        assert result == "Gate A is clear"

    @pytest.mark.asyncio
    async def test_empty_string_returns_empty(self):
        from api.services.translation import translate_text
        result = await translate_text("", "kn")
        assert result == ""

    @pytest.mark.asyncio
    async def test_static_translation_returned_without_api(self):
        """Known strings should translate without hitting the Cloud API."""
        from api.services.translation import translate_text, STATIC_TRANSLATIONS
        # Ensure "Clear" is in static dict
        assert "Clear" in STATIC_TRANSLATIONS
        result = await translate_text("Clear", "kn")
        assert result == STATIC_TRANSLATIONS["Clear"]["kn"]

    @pytest.mark.asyncio
    async def test_falls_back_to_english_on_api_failure(self):
        from api.services.translation import translate_text
        with patch("api.services.translation._get_translate_client",
                   side_effect=Exception("API error")):
            result = await translate_text("Some new text not in cache", "hi")
            assert result == "Some new text not in cache"

    @pytest.mark.asyncio
    async def test_route_notes_none_passthrough(self):
        from api.services.translation import translate_route_notes
        result = await translate_route_notes(None, "kn")
        assert result is None
