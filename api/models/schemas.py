"""
Pydantic data models for VenueFlow API.

All request and response schemas are defined here with full type annotations,
field validation, and documentation. These models serve three purposes:

    1. Input validation — FastAPI automatically rejects malformed requests.
    2. API documentation — Field descriptions appear in /docs (Swagger UI).
    3. Type safety — mypy and editors can catch type errors at write time.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    """Request body for POST /api/route.

    Attributes:
        origin: Zone ID of the starting point (must exist in venue graph).
        destination: Zone ID of the target location.
        wheelchair: If True, enforces step-free routing as a hard constraint.
    """

    origin: str = Field(
        ...,
        min_length=1,
        max_length=64,
        example="gate_C",
        description="Zone ID of the starting location.",
    )
    destination: str = Field(
        ...,
        min_length=1,
        max_length=64,
        example="section_F",
        description="Zone ID of the target destination.",
    )
    wheelchair: bool = Field(
        default=False,
        description=(
            "If True, only step-free paths are considered. "
            "Stairs and escalators are removed from the graph entirely."
        ),
    )


class RouteResponse(BaseModel):
    """Response body for POST /api/route.

    Attributes:
        path: Ordered list of zone IDs from origin to destination.
        distance_meters: Total walking distance in metres.
        estimated_minutes: Estimated total journey time including crowd delays.
        crowd_level: Average crowd density along the route (1=clear, 5=packed).
        accessible: True if the route is fully step-free.
        notes: Optional human-readable notes about the route.
    """

    path: List[str] = Field(
        ...,
        description="Ordered list of zone IDs forming the route.",
    )
    distance_meters: int = Field(
        ...,
        ge=0,
        description="Total walking distance in metres.",
    )
    estimated_minutes: int = Field(
        ...,
        ge=0,
        description="Estimated journey time including crowd delay adjustment.",
    )
    crowd_level: int = Field(
        ...,
        ge=1,
        le=5,
        description="Average crowd density along the route (1=clear, 5=packed).",
    )
    accessible: bool = Field(
        ...,
        description="True if the entire route is step-free and ramp-accessible.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Human-readable notes about crowd conditions or accessibility.",
    )


class ZoneDensityResponse(BaseModel):
    """Crowd density reading for a single venue zone.

    Attributes:
        zone_id: Unique zone identifier (matches venue graph node IDs).
        density_level: Occupancy level from 1 (clear) to 5 (packed).
        capacity_pct: Occupancy as a fraction of maximum safe capacity.
        wait_time_minutes: Estimated queue wait time in minutes, if applicable.
        last_updated: ISO 8601 timestamp of the most recent sensor reading.
    """

    zone_id: str = Field(
        ...,
        description="Unique zone identifier (e.g. 'gate_A', 'food_court_E').",
    )
    density_level: int = Field(
        ...,
        ge=1,
        le=5,
        description="Crowd density: 1=Clear 2=Light 3=Moderate 4=Busy 5=Packed.",
    )
    capacity_pct: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fraction of maximum safe capacity currently occupied (0.0–1.0).",
    )
    wait_time_minutes: Optional[int] = Field(
        default=None,
        ge=0,
        description="Estimated queue wait time in minutes. Null if not applicable.",
    )
    last_updated: str = Field(
        ...,
        description="ISO 8601 timestamp of the most recent sensor update.",
    )


class WaitTimeResponse(BaseModel):
    """Predicted queue wait time for a single zone.

    Attributes:
        zone_id: Zone identifier.
        wait_minutes: Predicted wait time in minutes.
        confidence: Reliability of the prediction based on available data.
    """

    zone_id: str = Field(
        ...,
        description="Zone identifier matching the venue graph.",
    )
    wait_minutes: int = Field(
        ...,
        ge=0,
        description="Predicted queue wait time in minutes.",
    )
    confidence: str = Field(
        ...,
        pattern="^(high|medium|low)$",
        description=(
            "Prediction confidence: "
            "high=live+historical, medium=live only, low=historical only."
        ),
    )


class AlertResponse(BaseModel):
    """A venue alert or safety notification.

    Attributes:
        alert_id: Unique identifier for this alert (used for deduplication).
        type: Alert category determining display style and client behaviour.
        message: Human-readable alert text shown to the attendee.
        zone_id: The venue zone this alert relates to, if applicable.
        severity: Numeric severity from 1 (informational) to 5 (critical).
        timestamp: ISO 8601 creation timestamp.
    """

    alert_id: str = Field(
        ...,
        description="Unique alert identifier for client-side deduplication.",
    )
    type: str = Field(
        ...,
        pattern="^(emergency|nudge|info)$",
        description=(
            "Alert type: emergency=immediate danger, "
            "nudge=proactive recommendation, info=general update."
        ),
    )
    message: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Human-readable alert text displayed to the attendee.",
    )
    zone_id: Optional[str] = Field(
        default=None,
        description="Zone identifier if the alert is location-specific.",
    )
    severity: int = Field(
        ...,
        ge=1,
        le=5,
        description="Severity from 1 (informational) to 5 (critical emergency).",
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 creation timestamp.",
    )
