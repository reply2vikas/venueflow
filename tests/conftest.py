"""
Shared pytest fixtures for VenueFlow test suite.

All external dependencies (Firestore, BigQuery, Vertex AI) are mocked
so tests run fully offline without GCP credentials.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from api.models.schemas import ZoneDensityResponse


# ── Zone fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_zones_low_density() -> list[ZoneDensityResponse]:
    """All zones lightly occupied — ideal conditions."""
    zones = [
        ("gate_A",         1, 0.20, 1),
        ("gate_B",         2, 0.40, 3),
        ("gate_C",         1, 0.15, 1),
        ("concourse_north",2, 0.38, 2),
        ("concourse_south",1, 0.22, 1),
        ("food_court_E",   2, 0.35, 4),
        ("restroom_accessible_F", 1, 0.10, 0),
        ("exit_main",      1, 0.18, 1),
    ]
    return [
        ZoneDensityResponse(
            zone_id=z, density_level=d, capacity_pct=c,
            wait_time_minutes=w, last_updated="2026-04-01T19:00:00Z"
        )
        for z, d, c, w in zones
    ]


@pytest.fixture
def mock_zones_surge() -> list[ZoneDensityResponse]:
    """Post-match surge — all exit zones packed."""
    zones = [
        ("gate_A",         5, 0.95, 22),
        ("gate_B",         5, 0.92, 25),
        ("gate_C",         3, 0.62,  8),
        ("concourse_north",5, 0.90, 20),
        ("concourse_south",4, 0.75, 14),
        ("food_court_E",   5, 0.98, 30),
        ("restroom_accessible_F", 3, 0.60, 8),
        ("exit_main",      5, 0.94, 24),
    ]
    return [
        ZoneDensityResponse(
            zone_id=z, density_level=d, capacity_pct=c,
            wait_time_minutes=w, last_updated="2026-04-01T22:30:00Z"
        )
        for z, d, c, w in zones
    ]


@pytest.fixture
def mock_zones_mixed() -> list[ZoneDensityResponse]:
    """Realistic mid-match: some zones busy, some clear."""
    zones = [
        ("gate_A",         2, 0.42,  3),
        ("gate_B",         4, 0.81, 12),
        ("gate_C",         1, 0.20,  1),
        ("concourse_north",3, 0.65,  6),
        ("concourse_south",2, 0.38,  2),
        ("food_court_E",   5, 0.95, 18),
        ("restroom_accessible_F", 1, 0.15, 1),
        ("exit_main",      3, 0.60,  5),
    ]
    return [
        ZoneDensityResponse(
            zone_id=z, density_level=d, capacity_pct=c,
            wait_time_minutes=w, last_updated="2026-04-01T20:30:00Z"
        )
        for z, d, c, w in zones
    ]


# ── FastAPI test client ───────────────────────────────────────────────────────

@pytest.fixture
def client():
    """FastAPI test client with all external services mocked."""
    from api.main import app
    with TestClient(app) as c:
        yield c


# ── Service mocks ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_firestore():
    with patch("api.services.crowd._get_firestore") as mock:
        mock.side_effect = Exception("Firestore mocked out")
        yield mock


@pytest.fixture
def mock_bigquery():
    with patch("api.services.prediction._bq_historical", new_callable=AsyncMock) as mock:
        mock.return_value = None  # Default: BigQuery unavailable
        yield mock


@pytest.fixture
def mock_gemini():
    with patch("api.services.gemini_assistant.ask_gemini", new_callable=AsyncMock) as mock:
        mock.return_value = "Gate C accessible ramp is clear. Head there now."
        yield mock
