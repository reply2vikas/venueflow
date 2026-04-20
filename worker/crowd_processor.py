"""
Pub/Sub crowd sensor worker.

Subscribes to the venue-crowd-events Pub/Sub topic, aggregates sensor
counts per zone every 30 seconds, and writes crowd density to Firestore.

This worker runs as a separate Cloud Run service (always-on, min 1 instance).
It is the bridge between raw gate sensor hardware and the live crowd map
that attendees see in the VenueFlow app.

Data flow:
    Gate sensor → Pub/Sub topic → This worker → Firestore zones collection
                                                      ↓
                                          VenueFlow API reads Firestore
                                                      ↓
                                          Attendee sees live crowd map

Density classification thresholds (based on crowd safety research):
    < 30% capacity  → Level 1 (Clear)
    30–50%          → Level 2 (Light)
    50–65%          → Level 3 (Moderate)
    65–80%          → Level 4 (Busy)
    > 80%           → Level 5 (Packed — approaching safety threshold)
"""

import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

from google.cloud import firestore
from google.cloud import pubsub_v1

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
PROJECT: str = os.environ["GCP_PROJECT"]
SUBSCRIPTION: str = os.getenv("PUBSUB_SUBSCRIPTION", "venue-crowd-events-sub")
FLUSH_INTERVAL: int = 30  # seconds between Firestore writes

# ── Clients ───────────────────────────────────────────────────────────────────
db = firestore.Client()
subscriber = pubsub_v1.SubscriberClient()
subscription_path = subscriber.subscription_path(PROJECT, SUBSCRIPTION)

# ── In-memory buffer ──────────────────────────────────────────────────────────
# Accumulates raw sensor counts between flush cycles.
# Key: zone_id, Value: list of capacity percentages from sensors.
zone_buffer: Dict[str, List[float]] = defaultdict(list)


def classify_density(capacity_pct: float) -> int:
    """Convert a capacity percentage to a crowd density level (1–5).

    Thresholds are based on crowd safety research. Level 5 triggers the
    stampede prevention system in the VenueFlow API.

    Args:
        capacity_pct: Current occupancy as a fraction of maximum capacity
            (e.g. 0.72 = 72% full).

    Returns:
        Integer density level from 1 (clear) to 5 (packed/dangerous).
    """
    if capacity_pct < 0.30:
        return 1
    if capacity_pct < 0.50:
        return 2
    if capacity_pct < 0.65:
        return 3
    if capacity_pct < 0.80:
        return 4
    return 5


def on_message(message: pubsub_v1.subscriber.message.Message) -> None:
    """Handle a single Pub/Sub message from a gate sensor.

    Parses the JSON payload, extracts zone_id and count, and appends
    the count to the in-memory buffer for that zone. Always acknowledges
    the message to prevent it from being redelivered.

    Args:
        message: The Pub/Sub message containing sensor data.
            Expected JSON format: {"zone_id": "gate_A", "count": 45}
    """
    try:
        event = json.loads(message.data.decode("utf-8"))
        zone_id: str = event.get("zone_id", "")
        count: float = float(event.get("count", 0))
        if zone_id:
            zone_buffer[zone_id].append(count)
            logger.debug("sensor event received zone=%s count=%.0f", zone_id, count)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("malformed sensor message: %s | data=%s", exc, message.data[:100])
    finally:
        message.ack()


def flush() -> None:
    """Write aggregated zone densities to Firestore.

    Computes the average capacity percentage for each zone in the buffer,
    classifies it as a density level, and performs a Firestore merge write.
    Clears the buffer after writing.

    The merge=True flag preserves any existing fields in the Firestore
    document (e.g. zone labels) while updating only the density fields.
    """
    if not zone_buffer:
        logger.debug("flush called but buffer is empty — skipping")
        return

    now: str = datetime.now(timezone.utc).isoformat()
    written_count: int = 0

    for zone_id, counts in list(zone_buffer.items()):
        if not counts:
            continue
        avg_pct: float = sum(counts) / len(counts) / 100.0
        db.collection("zones").document(zone_id).set(
            {
                "density_level": classify_density(avg_pct),
                "capacity_pct": round(avg_pct, 3),
                "last_updated": now,
            },
            merge=True,
        )
        written_count += 1

    logger.info("flush complete zones_written=%d", written_count)
    zone_buffer.clear()


if __name__ == "__main__":
    logger.info(
        "crowd worker starting project=%s subscription=%s flush_interval=%ds",
        PROJECT, SUBSCRIPTION, FLUSH_INTERVAL,
    )
    subscriber.subscribe(subscription_path, callback=on_message)
    logger.info("crowd worker listening for sensor events")
    while True:
        time.sleep(FLUSH_INTERVAL)
        flush()
