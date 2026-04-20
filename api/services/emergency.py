"""
Emergency and alert service — integrates stampede prevention.

Every call to get_active_alerts() now also:
  1. Fetches current zone densities
  2. Runs stampede risk detection
  3. Auto-generates emergency alerts for critical zones
  4. Logs them to Firestore
  5. Returns emergency alerts FIRST in the list (highest priority)

This means the frontend always sees the most dangerous situations at
the top of the alert list, without any manual intervention.
"""



import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from api.models.schemas import AlertResponse, ZoneDensityResponse

logger = logging.getLogger(__name__)

# Load venue graph once at module level (fast, no I/O on every request)
_VENUE_GRAPH: dict = {}
def _get_venue_graph() -> dict:
    global _VENUE_GRAPH
    if not _VENUE_GRAPH:
        graph_path = Path(__file__).parent.parent.parent / "data" / "venue_graph.json"
        try:
            _VENUE_GRAPH = json.loads(graph_path.read_text())
        except Exception:
            _VENUE_GRAPH = {"nodes": {}, "edges": {}}
    return _VENUE_GRAPH


async def get_active_alerts() -> list[AlertResponse]:
    """
    Return all active venue alerts, with emergencies at the top.

    Process:
      1. Read existing alerts from Firestore
      2. Get current zone densities
      3. Run stampede detection on live density data
      4. Prepend any emergency alerts for critical zones
      5. Return merged list — emergencies first

    This function never raises — it always returns a list (empty on total failure).
    """
    alerts: list[AlertResponse] = []

    # ── Step 1: Read existing Firestore alerts ────────────────────────────────
    try:
        from google.cloud import firestore
        db = firestore.Client()
        docs = db.collection("alerts").where("active", "==", True).stream()
        for doc in docs:
            d = doc.to_dict()
            alerts.append(AlertResponse(
                alert_id  = doc.id,
                type      = d.get("type", "info"),
                message   = d.get("message", ""),
                zone_id   = d.get("zone_id"),
                severity  = d.get("severity", 1),
                timestamp = d.get("timestamp", datetime.now(timezone.utc).isoformat()),
            ))
    except Exception as exc:
        logger.warning("Could not read Firestore alerts (non-fatal): %s", exc)

    # ── Step 2: Live stampede detection ───────────────────────────────────────
    try:
        from api.services.crowd import get_all_zone_densities
        from api.services.emergency_manager import (
            check_stampede_risk,
            check_warning_zones,
            get_emergency_exits,
            trigger_emergency_protocol,
            build_emergency_alert,
            build_warning_alert,
        )

        zones: list[ZoneDensityResponse] = await get_all_zone_densities()
        venue_graph = _get_venue_graph()

        # Check for critical stampede-risk zones
        critical_zones = check_stampede_risk(zones)
        for zone in critical_zones:
            safe_exits = get_emergency_exits(zone.zone_id, venue_graph, zones)
            emergency_alert = build_emergency_alert(zone, safe_exits)

            # Log to Firestore asynchronously (non-blocking)
            try:
                await trigger_emergency_protocol(
                    zone.zone_id, safe_exits, zone.capacity_pct
                )
            except Exception as log_exc:
                logger.error("Emergency logging failed: %s", log_exc)

            # Always prepend emergency alerts — they show FIRST
            alerts.insert(0, emergency_alert)

        # Check for warning zones (70-85% capacity)
        warning_zones = check_warning_zones(zones)
        warning_alerts = [build_warning_alert(z) for z in warning_zones]

        # Merge: emergencies first, then warnings, then existing Firestore alerts
        alerts = [a for a in alerts if a.type == "emergency"] + \
                 warning_alerts + \
                 [a for a in alerts if a.type != "emergency"]

    except Exception as exc:
        logger.error("Stampede detection failed (non-fatal): %s", exc)

    return alerts
