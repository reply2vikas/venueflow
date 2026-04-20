"""
Crowd zone density endpoint.

Provides real-time occupancy levels for every zone in the venue,
sourced from Firestore with an in-memory cache fallback.
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.models.schemas import ZoneDensityResponse
from api.services.crowd import get_all_zone_densities

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.get(
    "/zones",
    response_model=List[ZoneDensityResponse],
    summary="Live crowd density",
    description=(
        "Returns current occupancy level (1-5) for every venue zone. "
        "Updated every 30 seconds from sensor data via Pub/Sub → Firestore pipeline."
    ),
)
@limiter.limit("60/minute")
async def get_zones(request: Request) -> List[ZoneDensityResponse]:
    """Return real-time crowd density for all venue zones.

    Fetches from Firestore (primary), falls back to in-memory cache,
    then to realistic mock data so the endpoint never returns an error
    to the end user.

    Args:
        request: FastAPI request object (required by slowapi rate limiter).

    Returns:
        List of ZoneDensityResponse, one entry per zone.
        Density levels: 1=Clear  2=Light  3=Moderate  4=Busy  5=Packed.

    Raises:
        HTTPException: 503 only if the service layer raises unexpectedly.

    Example::

        GET /api/zones
        Response: [{"zone_id": "gate_A", "density_level": 2, ...}, ...]
    """
    try:
        zones = await get_all_zone_densities()
        logger.info("zones fetched successfully count=%d", len(zones))
        return zones
    except Exception as exc:
        logger.error("zone fetch failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Zone data temporarily unavailable. Please try again.",
        )
