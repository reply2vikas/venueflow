"""Unit tests for wait-time prediction service."""
import pytest
from unittest.mock import AsyncMock, patch

MOCK_ZONES = [
    type('Z', (), {'zone_id': 'food_court_E',          'density_level': 5})(),
    type('Z', (), {'zone_id': 'gate_C',                'density_level': 1})(),
    type('Z', (), {'zone_id': 'restroom_accessible_F', 'density_level': 1})(),
]

@pytest.mark.asyncio
async def test_high_density_higher_wait():
    from api.services.prediction import predict_wait_all
    with patch('api.services.prediction.get_all_zone_densities', new=AsyncMock(return_value=MOCK_ZONES)), \
         patch('api.services.prediction._bq_historical', new=AsyncMock(return_value=None)):
        results = await predict_wait_all()
        food = next(r for r in results if r.zone_id == 'food_court_E')
        gate = next(r for r in results if r.zone_id == 'gate_C')
        assert food.wait_minutes > gate.wait_minutes

@pytest.mark.asyncio
async def test_all_wait_non_negative():
    from api.services.prediction import predict_wait_all
    with patch('api.services.prediction.get_all_zone_densities', new=AsyncMock(return_value=MOCK_ZONES)), \
         patch('api.services.prediction._bq_historical', new=AsyncMock(return_value=None)):
        results = await predict_wait_all()
        assert all(r.wait_minutes >= 0 for r in results)

@pytest.mark.asyncio
async def test_bq_data_improves_confidence():
    from api.services.prediction import predict_wait_all
    with patch('api.services.prediction.get_all_zone_densities', new=AsyncMock(return_value=MOCK_ZONES)), \
         patch('api.services.prediction._bq_historical', new=AsyncMock(return_value=5.0)):
        results = await predict_wait_all()
        assert all(r.confidence == "high" for r in results)
