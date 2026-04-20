"""
Venue alerts endpoint.

Returns active alerts ordered by severity: emergencies first,
then warnings, then informational nudges. Automatically runs
stampede risk detection on every call using live zone density data.

This endpoint is polled every 25 seconds by the client as a
fallback when WebSocket connectivity is unavailable.
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.models.schemas import AlertResponse
from api.services.emergency import get_active_alerts

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.get(
    "/alerts",
    response_model=List[AlertResponse],
    summary="Active venue alerts",
    description=(
        "Returns all active venue alerts with emergencies first. "
        "Automatically runs stampede risk detection on live zone data "
        "on every call. Emergency alerts are written to Firestore for "
        "post-incident review by venue safety teams."
    ),
)
@limiter.limit("120/minute")
async def get_alerts(request: Request) -> List[AlertResponse]:
    """Return active venue alerts ordered by severity.

    Automatically detects stampede risk on every call by checking
    if any zone exceeds 85% capacity at density level 5. Emergency
    alerts are prepended to the list and written to Firestore.

    Alert types by severity:
        - emergency (severity 5): Immediate danger — stampede risk detected
        - nudge (severity 3): Zone approaching capacity — preemptive warning
        - info (severity 1): General venue information

    Args:
        request: FastAPI request object (required by slowapi rate limiter).

    Returns:
        List of AlertResponse objects ordered emergency → nudge → info.
        Returns empty list (not an error) when venue is safe.

    Raises:
        HTTPException: 503 only if the service encounters an unexpected error.

    Example::

        GET /api/alerts
        Response: [{"type": "emergency", "severity": 5, "message": "..."}, ...]
    """
    try:
        alerts = await get_active_alerts()
        emergency_count = sum(1 for a in alerts if a.type == "emergency")
        logger.info(
            "alerts fetched total=%d emergencies=%d",
            len(alerts), emergency_count,
        )
        return alerts
    except Exception as exc:
        logger.error("alert fetch failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Alert service temporarily unavailable. Please try again.",
        )
