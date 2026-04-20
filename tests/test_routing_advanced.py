"""
Advanced routing tests covering edge cases and accessibility constraints.

These tests verify the core safety property of VenueFlow:
wheelchair mode must NEVER return a path with inaccessible segments.
This is tested exhaustively because it is a safety-critical feature.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


SAMPLE_GRAPH = {
    "nodes": {
        "gate_A":         {"accessible": True,  "label": "Gate A"},
        "gate_C":         {"accessible": True,  "label": "Gate C (Accessible)"},
        "stairs_E1":      {"accessible": False, "label": "East Stairwell"},
        "lift_W1":        {"accessible": True,  "label": "West Lift"},
        "concourse_north":{"accessible": True,  "label": "North Concourse"},
        "section_F":      {"accessible": True,  "label": "Section F"},
        "exit_north":     {"accessible": True,  "label": "North Exit"},
    },
    "edges": {
        "gate_A":          {"concourse_north": {"distance_m": 80,  "accessible": True}},
        "gate_C":          {"lift_W1":         {"distance_m": 20,  "accessible": True}},
        "concourse_north": {"stairs_E1":       {"distance_m": 30,  "accessible": False},
                            "section_F":       {"distance_m": 110, "accessible": True}},
        "lift_W1":         {"section_F":       {"distance_m": 70,  "accessible": True}},
        "section_F":       {"exit_north":      {"distance_m": 100, "accessible": True}},
    },
}


def _make_zones(overrides=None):
    """Build a mock zone density list."""
    from api.models.schemas import ZoneDensityResponse
    defaults = {
        "gate_A": 2, "gate_C": 1, "lift_W1": 1,
        "concourse_north": 3, "section_F": 2, "exit_north": 1,
    }
    if overrides:
        defaults.update(overrides)
    return [
        ZoneDensityResponse(
            zone_id=k, density_level=v, capacity_pct=v / 5,
            wait_time_minutes=v * 2, last_updated="2026-04-19T00:00:00Z"
        )
        for k, v in defaults.items()
    ]


class TestRoutingCore:

    @pytest.mark.asyncio
    async def test_basic_route_found(self):
        """A simple route between two connected zones must be found."""
        with patch("api.services.routing._load_graph", return_value=SAMPLE_GRAPH), \
             patch("api.services.routing.get_all_zone_densities",
                   new_callable=AsyncMock, return_value=_make_zones()):
            from api.services.routing import get_best_route
            result = await get_best_route("gate_A", "section_F", wheelchair=False)
            assert "gate_A" in result.path
            assert "section_F" in result.path
            assert result.distance_meters > 0

    @pytest.mark.asyncio
    async def test_wheelchair_never_includes_stairs(self):
        """Wheelchair mode must NEVER include inaccessible nodes in path."""
        with patch("api.services.routing._load_graph", return_value=SAMPLE_GRAPH), \
             patch("api.services.routing.get_all_zone_densities",
                   new_callable=AsyncMock, return_value=_make_zones()):
            from api.services.routing import get_best_route
            result = await get_best_route("gate_A", "section_F", wheelchair=True)
            assert "stairs_E1" not in result.path
            assert result.accessible is True

    @pytest.mark.asyncio
    async def test_wheelchair_flag_set_in_response(self):
        """accessible field in response must match wheelchair parameter."""
        with patch("api.services.routing._load_graph", return_value=SAMPLE_GRAPH), \
             patch("api.services.routing.get_all_zone_densities",
                   new_callable=AsyncMock, return_value=_make_zones()):
            from api.services.routing import get_best_route
            result = await get_best_route("gate_C", "exit_north", wheelchair=True)
            assert result.accessible is True

    @pytest.mark.asyncio
    async def test_non_wheelchair_may_include_stairs(self):
        """Without wheelchair mode, stairs can appear in path if shortest."""
        with patch("api.services.routing._load_graph", return_value=SAMPLE_GRAPH), \
             patch("api.services.routing.get_all_zone_densities",
                   new_callable=AsyncMock, return_value=_make_zones()):
            from api.services.routing import get_best_route
            result = await get_best_route("gate_A", "section_F", wheelchair=False)
            # stairs_E1 could appear — this is valid without wheelchair mode
            assert isinstance(result.path, list)
            assert len(result.path) >= 2

    @pytest.mark.asyncio
    async def test_unknown_origin_raises_value_error(self):
        """Routing from a nonexistent zone must raise ValueError (not crash)."""
        with patch("api.services.routing._load_graph", return_value=SAMPLE_GRAPH), \
             patch("api.services.routing.get_all_zone_densities",
                   new_callable=AsyncMock, return_value=_make_zones()):
            from api.services.routing import get_best_route
            with pytest.raises(ValueError, match="No path found"):
                await get_best_route("zone_that_doesnt_exist", "section_F", wheelchair=False)

    @pytest.mark.asyncio
    async def test_unknown_destination_raises_value_error(self):
        """Routing to a nonexistent destination must raise ValueError."""
        with patch("api.services.routing._load_graph", return_value=SAMPLE_GRAPH), \
             patch("api.services.routing.get_all_zone_densities",
                   new_callable=AsyncMock, return_value=_make_zones()):
            from api.services.routing import get_best_route
            with pytest.raises(ValueError):
                await get_best_route("gate_A", "nonexistent_dest", wheelchair=False)

    @pytest.mark.asyncio
    async def test_estimated_time_increases_with_crowd(self):
        """Higher crowd density must produce longer estimated times."""
        with patch("api.services.routing._load_graph", return_value=SAMPLE_GRAPH):
            from api.services.routing import get_best_route

            low_density = _make_zones({"gate_A": 1, "concourse_north": 1, "section_F": 1})
            high_density = _make_zones({"gate_A": 5, "concourse_north": 5, "section_F": 5})

            with patch("api.services.routing.get_all_zone_densities",
                       new_callable=AsyncMock, return_value=low_density):
                low_result = await get_best_route("gate_A", "section_F", wheelchair=False)

            with patch("api.services.routing.get_all_zone_densities",
                       new_callable=AsyncMock, return_value=high_density):
                high_result = await get_best_route("gate_A", "section_F", wheelchair=False)

            assert high_result.estimated_minutes >= low_result.estimated_minutes

    @pytest.mark.asyncio
    async def test_crowd_level_within_valid_range(self):
        """Crowd level in response must always be between 1 and 5."""
        with patch("api.services.routing._load_graph", return_value=SAMPLE_GRAPH), \
             patch("api.services.routing.get_all_zone_densities",
                   new_callable=AsyncMock, return_value=_make_zones()):
            from api.services.routing import get_best_route
            result = await get_best_route("gate_A", "section_F", wheelchair=False)
            assert 1 <= result.crowd_level <= 5

    @pytest.mark.asyncio
    async def test_distance_meters_positive(self):
        """Route distance must always be a positive integer."""
        with patch("api.services.routing._load_graph", return_value=SAMPLE_GRAPH), \
             patch("api.services.routing.get_all_zone_densities",
                   new_callable=AsyncMock, return_value=_make_zones()):
            from api.services.routing import get_best_route
            result = await get_best_route("gate_C", "section_F", wheelchair=True)
            assert result.distance_meters > 0

    @pytest.mark.asyncio
    async def test_path_starts_at_origin_ends_at_destination(self):
        """Path must start at origin and end at destination."""
        with patch("api.services.routing._load_graph", return_value=SAMPLE_GRAPH), \
             patch("api.services.routing.get_all_zone_densities",
                   new_callable=AsyncMock, return_value=_make_zones()):
            from api.services.routing import get_best_route
            result = await get_best_route("gate_A", "section_F", wheelchair=False)
            assert result.path[0] == "gate_A"
            assert result.path[-1] == "section_F"

    @pytest.mark.asyncio
    async def test_no_duplicate_nodes_in_path(self):
        """A valid path must not visit the same zone twice (no loops)."""
        with patch("api.services.routing._load_graph", return_value=SAMPLE_GRAPH), \
             patch("api.services.routing.get_all_zone_densities",
                   new_callable=AsyncMock, return_value=_make_zones()):
            from api.services.routing import get_best_route
            result = await get_best_route("gate_A", "section_F", wheelchair=False)
            assert len(result.path) == len(set(result.path))


class TestSchemaValidation:

    def test_route_request_wheelchair_defaults_false(self):
        """wheelchair field must default to False when not provided."""
        from api.models.schemas import RouteRequest
        req = RouteRequest(origin="gate_A", destination="section_F")
        assert req.wheelchair is False

    def test_zone_density_rejects_level_zero(self):
        """density_level of 0 is invalid — minimum is 1."""
        from pydantic import ValidationError
        from api.models.schemas import ZoneDensityResponse
        with pytest.raises(ValidationError):
            ZoneDensityResponse(
                zone_id="gate_A", density_level=0, capacity_pct=0.5,
                last_updated="2026-04-19T00:00:00Z"
            )

    def test_zone_density_rejects_level_six(self):
        """density_level of 6 is invalid — maximum is 5."""
        from pydantic import ValidationError
        from api.models.schemas import ZoneDensityResponse
        with pytest.raises(ValidationError):
            ZoneDensityResponse(
                zone_id="gate_A", density_level=6, capacity_pct=0.5,
                last_updated="2026-04-19T00:00:00Z"
            )

    def test_alert_type_must_be_valid(self):
        """Alert type must be one of: emergency, nudge, info."""
        from pydantic import ValidationError
        from api.models.schemas import AlertResponse
        with pytest.raises(ValidationError):
            AlertResponse(
                alert_id="001", type="danger",
                message="test", severity=3,
                timestamp="2026-04-19T00:00:00Z"
            )

    def test_wait_time_confidence_must_be_valid(self):
        """Confidence must be one of: high, medium, low."""
        from pydantic import ValidationError
        from api.models.schemas import WaitTimeResponse
        with pytest.raises(ValidationError):
            WaitTimeResponse(zone_id="gate_A", wait_minutes=5, confidence="unknown")
