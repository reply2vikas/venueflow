"""
Wait time prediction endpoint.

Blends live Firestore crowd density (60%) with BigQuery historical
patterns (40%) to produce accurate queue wait time estimates.
Falls back gracefully to live-only estimates when BigQuery is
unavailable, ensuring the endpoint always returns useful data.
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.models.schemas import WaitTimeResponse
from api.services.prediction import predict_wait_all

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.get(
    "/waittimes",
    response_model=List[WaitTimeResponse],
    summary="Predicted queue wait times",
    description=(
        "Returns predicted wait times for all zones. "
        "Blends 60% live density data from Firestore with 40% BigQuery "
        "historical averages for the same hour and match phase. "
        "Confidence: high=both sources, medium=live only, low=historical only."
    ),
)
@limiter.limit("60/minute")
async def get_wait_times(request: Request) -> List[WaitTimeResponse]:
    """Return predicted wait times for all venue zones.

    Uses a weighted blend of real-time and historical data for accuracy.
    The historical component captures patterns like post-match exit rushes
    that pure density readings miss.

    Args:
        request: FastAPI request object (required by slowapi rate limiter).

    Returns:
        List of WaitTimeResponse with zone_id, wait_minutes, and confidence.
        Confidence values: "high" | "medium" | "low".

    Raises:
        HTTPException: 503 if prediction service encounters an unexpected error.

    Example::

        GET /api/waittimes
        Response: [{"zone_id": "gate_A", "wait_minutes": 3, "confidence": "high"}, ...]
    """
    try:
        results = await predict_wait_all()
        logger.info("wait times predicted zone_count=%d", len(results))
        return results
    except Exception as exc:
        logger.error("wait time prediction failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Wait time data temporarily unavailable. Please try again.",
        )
