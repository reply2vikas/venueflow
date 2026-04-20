from typing import Optional, List
"""
Stampede Prevention and Emergency Management System.

This module was built in memory of the victims of the Chinnaswamy Stadium
stampede in Bengaluru, where overcrowding led to tragic loss of life.

VenueFlow detects dangerously high crowd density BEFORE it becomes fatal,
automatically triggers emergency protocols, and guides people to the
nearest safe exits — all in real time.

How it works:
  1. Every 30 seconds, zone density is checked against safety thresholds
  2. Any zone above 85% capacity is flagged as "critical" (stampede risk)
  3. Emergency alerts are written to Firestore immediately
  4. All connected users in that zone receive a WebSocket push instantly
  5. Three alternate safe exit routes are calculated and shared
  6. A post-incident log is maintained for venue safety teams

Design principle: Better to alert 100 times unnecessarily than to miss
one genuine emergency.
"""



import logging
from datetime import datetime, timezone
from typing import Optional

from api.models.schemas import ZoneDensityResponse, AlertResponse

logger = logging.getLogger(__name__)

# ── Safety thresholds ─────────────────────────────────────────────────────────
# Based on crowd safety research: above 85% capacity in an enclosed zone,
# the risk of crowd crush and stampede increases sharply.
STAMPEDE_RISK_THRESHOLD = 0.85   # 85% capacity = critical
WARNING_THRESHOLD       = 0.70   # 70% capacity = warning (early alert)

# Zones that are always exits — used when routing people to safety
EXIT_ZONES = {"exit_main", "exit_north", "gate_A", "gate_B", "gate_C"}


# ── Core stampede detection ───────────────────────────────────────────────────

def check_stampede_risk(zones: List[ZoneDensityResponse]) -> list[ZoneDensityResponse]:
    """
    Scan all zones and return those at critical stampede risk.

    A zone is "critical" when:
      - capacity_pct > 85%  (dangerously overcrowded)
      - density_level == 5  (maximum density reading)

    Both conditions must be true to avoid false positives.

    Args:
        zones: Current snapshot of all zone density readings.

    Returns:
        List of zones that are at critical stampede risk.
        Empty list = venue is safe.
    """
    critical = [
        z for z in zones
        if z.capacity_pct > STAMPEDE_RISK_THRESHOLD
        and z.density_level >= 5
    ]
    if critical:
        zone_names = [z.zone_id for z in critical]
        logger.warning("STAMPEDE RISK detected in zones: %s", zone_names)
    return critical


def check_warning_zones(zones: List[ZoneDensityResponse]) -> list[ZoneDensityResponse]:
    """
    Return zones approaching dangerous levels (70-85% capacity).

    These zones get a "heads up" alert — not an emergency, but a nudge
    to move people out before the situation becomes critical.

    Args:
        zones: Current zone density snapshot.

    Returns:
        List of zones in warning range.
    """
    return [
        z for z in zones
        if WARNING_THRESHOLD < z.capacity_pct <= STAMPEDE_RISK_THRESHOLD
        and z.density_level >= 4
    ]


# ── Emergency exit routing ────────────────────────────────────────────────────

def get_emergency_exits(
    zone_id: str,
    venue_graph: dict,
    current_zones: List[ZoneDensityResponse],
) -> list[dict]:
    """
    Find the 3 nearest safe exits from a dangerous zone.

    "Safe" means:
      - It is an exit node (gate or exit)
      - It is NOT itself overcrowded (density < 4)
      - It is accessible (ramp-friendly where possible)

    Args:
        zone_id:       The zone that is in danger.
        venue_graph:   The venue node/edge graph from venue_graph.json.
        current_zones: Live zone density for filtering unsafe exits.

    Returns:
        List of up to 3 safe exit options, each with zone_id, label,
        distance_m, and accessible flag.
    """
    # Build a set of overcrowded zone IDs for fast lookup
    crowded = {
        z.zone_id for z in current_zones
        if z.density_level >= 4
    }

    nodes = venue_graph.get("nodes", {})
    edges = venue_graph.get("edges", {})

    safe_exits = []

    # BFS from the dangerous zone outward — collect exit nodes
    visited  = {zone_id}
    queue    = [(zone_id, 0, True)]   # (node, distance_m, accessible_so_far)

    while queue and len(safe_exits) < 3:
        current, dist, accessible = queue.pop(0)

        # If this is a safe exit node — add it to results
        if current in EXIT_ZONES and current not in crowded and current != zone_id:
            node_info = nodes.get(current, {})
            safe_exits.append({
                "zone_id":    current,
                "label":      node_info.get("label", current),
                "distance_m": dist,
                "accessible": node_info.get("accessible", True) and accessible,
            })
            continue   # Don't expand further from exit nodes

        # Expand to neighbours
        for neighbour, edge in edges.get(current, {}).items():
            if neighbour in visited:
                continue
            visited.add(neighbour)
            neighbour_accessible = accessible and edge.get("accessible", True)
            queue.append((
                neighbour,
                dist + edge.get("distance_m", 100),
                neighbour_accessible,
            ))

    # Sort: accessible exits first, then by distance
    safe_exits.sort(key=lambda x: (not x["accessible"], x["distance_m"]))

    if not safe_exits:
        # Hard fallback — always give at least one exit option
        logger.error("No safe exits found from zone %s — using hardcoded fallback", zone_id)
        safe_exits = [{
            "zone_id":    "exit_north",
            "label":      "North Exit (Accessible)",
            "distance_m": 200,
            "accessible": True,
        }]

    return safe_exits[:3]


# ── Firestore emergency logging ───────────────────────────────────────────────

async def trigger_emergency_protocol(
    zone_id: str,
    safe_exits: List[dict],
    capacity_pct: float,
) -> Optional[str]:
    """
    Write an emergency alert to Firestore and return the document ID.

    This creates a permanent record of the emergency event for:
      - Post-incident safety review
      - Venue management reporting
      - Insurance / regulatory compliance

    Args:
        zone_id:      The zone that triggered the emergency.
        safe_exits:   Pre-calculated safe exit routes.
        capacity_pct: Current occupancy as a decimal (e.g. 0.92 = 92%).

    Returns:
        Firestore document ID of the created alert, or None on failure.
    """
    exit_labels = [e["label"] for e in safe_exits]
    message = (
        f"EMERGENCY: {zone_id.replace('_', ' ').title()} is dangerously overcrowded "
        f"({int(capacity_pct * 100)}% full). "
        f"Move immediately to: {', '.join(exit_labels)}. "
        f"Follow steward directions. Do not push."
    )

    alert_data = {
        "type":        "emergency",
        "zone_id":     zone_id,
        "message":     message,
        "severity":    5,
        "capacity_pct": round(capacity_pct, 3),
        "safe_exits":  exit_labels,
        "active":      True,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "resolved":    False,
        # Post-incident fields — set by venue staff when situation clears
        "resolved_at": None,
        "resolved_by": None,
    }

    try:
        from google.cloud import firestore
        db = firestore.Client()
        doc_ref = db.collection("alerts").add(alert_data)
        doc_id = doc_ref[1].id
        logger.critical(
            "Emergency alert created — zone=%s capacity=%.0f%% doc_id=%s",
            zone_id, capacity_pct * 100, doc_id,
        )
        return doc_id

    except Exception as exc:
        logger.error("Failed to write emergency alert to Firestore: %s", exc)
        return None


async def resolve_emergency(zone_id: str, resolved_by: str = "system") -> bool:
    """
    Mark all active emergencies for a zone as resolved.

    Called automatically when density drops below threshold,
    or manually by venue staff via the admin panel.

    Args:
        zone_id:     The zone that is now safe.
        resolved_by: Who resolved it ("system", "steward", admin name).

    Returns:
        True if at least one alert was resolved.
    """
    try:
        from google.cloud import firestore
        db = firestore.Client()
        docs = (
            db.collection("alerts")
            .where("zone_id", "==", zone_id)
            .where("active",  "==", True)
            .where("type",    "==", "emergency")
            .stream()
        )
        resolved_count = 0
        for doc in docs:
            doc.reference.update({
                "active":      False,
                "resolved":    True,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
                "resolved_by": resolved_by,
            })
            resolved_count += 1

        if resolved_count:
            logger.info("Resolved %d emergency alerts for zone %s", resolved_count, zone_id)
        return resolved_count > 0

    except Exception as exc:
        logger.error("Failed to resolve emergencies for zone %s: %s", zone_id, exc)
        return False


# ── Human-readable helpers ────────────────────────────────────────────────────

def build_warning_alert(zone: ZoneDensityResponse) -> AlertResponse:
    """
    Build a non-emergency "heads up" alert for a zone approaching capacity.
    Sent as a gentle nudge before the situation becomes critical.
    """
    pct = int(zone.capacity_pct * 100)
    return AlertResponse(
        alert_id  = f"warn_{zone.zone_id}_{int(datetime.now().timestamp())}",
        type      = "nudge",
        message   = (
            f"{zone.zone_id.replace('_', ' ').title()} is filling up ({pct}% full). "
            f"Consider moving to a less crowded area now to avoid congestion."
        ),
        zone_id   = zone.zone_id,
        severity  = 3,
        timestamp = datetime.now(timezone.utc).isoformat(),
    )


def build_emergency_alert(
    zone: ZoneDensityResponse,
    safe_exits: List[dict],
) -> AlertResponse:
    """
    Build a critical emergency alert object for immediate display.
    This is shown in RED with vibration and audio on the frontend.
    """
    exit_labels = [e["label"] for e in safe_exits]
    pct = int(zone.capacity_pct * 100)
    return AlertResponse(
        alert_id  = f"emergency_{zone.zone_id}_{int(datetime.now().timestamp())}",
        type      = "emergency",
        message   = (
            f"CRITICAL ALERT: {zone.zone_id.replace('_', ' ').title()} "
            f"is at {pct}% capacity — dangerous overcrowding. "
            f"Move immediately to: {', '.join(exit_labels)}."
        ),
        zone_id   = zone.zone_id,
        severity  = 5,
        timestamp = datetime.now(timezone.utc).isoformat(),
    )
