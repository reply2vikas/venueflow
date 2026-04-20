"""Unit tests for routing service."""
import pytest
from unittest.mock import AsyncMock, patch

MOCK_ZONES = [
    type('Z', (), {'zone_id': 'gate_A',         'density_level': 2})(),
    type('Z', (), {'zone_id': 'concourse_north', 'density_level': 5})(),
    type('Z', (), {'zone_id': 'section_B',       'density_level': 1})(),
    type('Z', (), {'zone_id': 'gate_C',          'density_level': 1})(),
    type('Z', (), {'zone_id': 'concourse_south', 'density_level': 2})(),
    type('Z', (), {'zone_id': 'lift_W1',         'density_level': 1})(),
    type('Z', (), {'zone_id': 'section_F',       'density_level': 1})(),
]

@pytest.mark.asyncio
async def test_wheelchair_excludes_inaccessible():
    from api.services.routing import get_best_route
    with patch('api.services.routing.get_all_zone_densities', new=AsyncMock(return_value=MOCK_ZONES)):
        route = await get_best_route("gate_C", "section_F", wheelchair=True, avoid_dense=True)
        assert "stairs_E1" not in route.path
        assert route.accessible is True

@pytest.mark.asyncio
async def test_always_returns_route():
    from api.services.routing import get_best_route
    dense = [type('Z', (), {'zone_id': z, 'density_level': 5})()
             for z in ["gate_A", "concourse_north", "section_B"]]
    with patch('api.services.routing.get_all_zone_densities', new=AsyncMock(return_value=dense)):
        route = await get_best_route("gate_A", "section_B", wheelchair=False, avoid_dense=True)
        assert route is not None
        assert len(route.path) >= 2

@pytest.mark.asyncio
async def test_crowd_level_within_range():
    from api.services.routing import get_best_route
    with patch('api.services.routing.get_all_zone_densities', new=AsyncMock(return_value=MOCK_ZONES)):
        route = await get_best_route("gate_A", "section_B", wheelchair=False, avoid_dense=True)
        assert 0 <= route.crowd_level <= 5
