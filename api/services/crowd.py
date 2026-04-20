"""
Crowd density service.
Primary source: Firestore zones collection.
Fallback: in-memory cache (max 90s old), then realistic mock data.
Mock data ensures the app always works even without Firestore.
"""
import os
import time
from typing import List, Optional
from datetime import datetime, timezone
from api.models.schemas import ZoneDensityResponse

_cache: List[ZoneDensityResponse] = []
_cache_ts: float = 0
CACHE_TTL = 90  # seconds

MOCK_ZONES = [
    {"zone_id": "gate_A",                "density_level": 2, "capacity_pct": 0.42, "wait_time_minutes": 3},
    {"zone_id": "gate_B",                "density_level": 4, "capacity_pct": 0.81, "wait_time_minutes": 12},
    {"zone_id": "gate_C",                "density_level": 1, "capacity_pct": 0.20, "wait_time_minutes": 1},
    {"zone_id": "concourse_north",       "density_level": 3, "capacity_pct": 0.65, "wait_time_minutes": 6},
    {"zone_id": "concourse_south",       "density_level": 2, "capacity_pct": 0.38, "wait_time_minutes": 2},
    {"zone_id": "food_court_E",          "density_level": 4, "capacity_pct": 0.78, "wait_time_minutes": 18},
    {"zone_id": "restroom_accessible_F", "density_level": 1, "capacity_pct": 0.15, "wait_time_minutes": 1},
    {"zone_id": "exit_main",             "density_level": 3, "capacity_pct": 0.60, "wait_time_minutes": 5},
]


async def get_all_zone_densities() -> List[ZoneDensityResponse]:
    """
    Return live crowd density for all zones.

    Priority order:
    1. Firestore (live data, updated every 30s by the sensor worker)
    2. In-memory cache (if Firestore is down but cache is fresh)
    3. Mock data (always works — ensures app never crashes)
    """
    global _cache, _cache_ts
    now = datetime.now(timezone.utc).isoformat()

    try:
        db = _get_firestore()
        docs = list(db.collection(os.getenv("FIRESTORE_COLLECTION_ZONES", "zones")).stream())
        if docs:
            result = [
                ZoneDensityResponse(
                    zone_id=doc.id,
                    density_level=int(doc.to_dict().get("density_level", 1)),
                    capacity_pct=float(doc.to_dict().get("capacity_pct", 0.0)),
                    wait_time_minutes=doc.to_dict().get("wait_time_minutes"),
                    last_updated=now,
                )
                for doc in docs
            ]
            _cache = result
            _cache_ts = time.time()
            return result
    except Exception:
        pass

    # Fallback 1: fresh cache
    if _cache and (time.time() - _cache_ts) < CACHE_TTL:
        return _cache

    # Fallback 2: mock data (always works)
    return [ZoneDensityResponse(**z, last_updated=now) for z in MOCK_ZONES]


def _get_firestore():
    """Lazy Firestore client — only imported when needed."""
    from google.cloud import firestore
    return firestore.Client()
