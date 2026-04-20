"""
Crowd-aware accessible route planning endpoint.

Uses a BFS graph search over the static venue graph, weighted by
live crowd density. Enforces hard accessibility constraints when
wheelchair mode is enabled — stairs are blocked entirely, not
just penalised.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from api.models.schemas import RouteRequest, RouteResponse
from api.services.routing import get_best_route

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


@router.post(
    "/route",
    response_model=RouteResponse,
    summary="Find best route between two zones",
    description=(
        "Computes the crowd-aware shortest path between two venue zones. "
        "When wheelchair=true, any path containing stairs or escalators "
        "is removed entirely from consideration before scoring."
    ),
)
@limiter.limit("30/minute")
async def compute_route(request: Request, body: RouteRequest) -> RouteResponse:
    """Find the optimal route between two venue zones.

    Scores candidate paths by: (crowd_density × 15) + (distance × 0.01).
    Lower score wins. Up to 3 candidate paths are evaluated via BFS.

    Args:
        request: FastAPI request object (required by slowapi rate limiter).
        body: RouteRequest containing origin, destination, and wheelchair flag.

    Returns:
        RouteResponse with the best path, estimated time, crowd level,
        accessibility flag, and optional route notes.

    Raises:
        HTTPException: 400 if no path exists between origin and destination,
            or if wheelchair mode is requested but no step-free path exists.
        HTTPException: 503 if the routing service encounters an unexpected error.

    Example::

        POST /api/route
        Body: {"origin": "gate_C", "destination": "section_F", "wheelchair": true}
        Response: {"path": ["gate_C", "lift_W1", "section_F"], "accessible": true, ...}
    """
    try:
        result = await get_best_route(
            origin=body.origin,
            destination=body.destination,
            wheelchair=body.wheelchair,
            avoid_dense=True,
        )
        logger.info(
            "route computed origin=%s dest=%s wheelchair=%s distance_m=%d",
            body.origin, body.destination, body.wheelchair, result.distance_meters,
        )
        return result
    except ValueError as exc:
        logger.warning("route not found: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("routing service error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Routing service temporarily unavailable. Please try again.",
        )
