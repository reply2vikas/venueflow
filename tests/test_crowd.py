"""Unit tests for crowd density service."""
import pytest, time
from unittest.mock import patch
from api.services import crowd

@pytest.mark.asyncio
async def test_mock_data_returned_when_firestore_unavailable():
    with patch('api.services.crowd._get_firestore', side_effect=Exception("offline")):
        crowd._cache = []
        crowd._cache_ts = 0
        result = await crowd.get_all_zone_densities()
        assert len(result) > 0
        assert all(0 <= z.density_level <= 5 for z in result)

@pytest.mark.asyncio
async def test_cache_returned_within_ttl():
    from api.models.schemas import ZoneDensityResponse
    crowd._cache = [ZoneDensityResponse(zone_id="test_zone", density_level=2,
                                         capacity_pct=0.4, last_updated="2024-01-01T00:00:00Z")]
    crowd._cache_ts = time.time()
    with patch('api.services.crowd._get_firestore', side_effect=Exception("offline")):
        result = await crowd.get_all_zone_densities()
        assert result[0].zone_id == "test_zone"

@pytest.mark.asyncio
async def test_density_levels_valid_range():
    with patch('api.services.crowd._get_firestore', side_effect=Exception("offline")):
        crowd._cache = []
        crowd._cache_ts = 0
        result = await crowd.get_all_zone_densities()
        for zone in result:
            assert 1 <= zone.density_level <= 5, f"Invalid density level for {zone.zone_id}"
