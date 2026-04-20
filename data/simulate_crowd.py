"""
Simulates gate/turnstile sensor events by publishing to Pub/Sub.
Run locally or on Cloud Run to generate demo crowd data.
Usage: python data/simulate_crowd.py
"""
import json, os, random, time
from google.cloud import pubsub_v1

PROJECT = os.environ.get("GCP_PROJECT", "demo-project")
TOPIC = os.environ.get("CROWD_PUBSUB_TOPIC", "venue-crowd-events")

ZONES = [
    "gate_A", "gate_B", "gate_C",
    "concourse_north", "concourse_south",
    "food_court_E", "restroom_accessible_F",
    "exit_main", "exit_north"
]

BASE_OCCUPANCY = {
    "gate_A": 40, "gate_B": 70, "gate_C": 25,
    "concourse_north": 55, "concourse_south": 35,
    "food_court_E": 90, "restroom_accessible_F": 15,
    "exit_main": 50, "exit_north": 20
}

def get_phase(elapsed_min: int) -> str:
    if elapsed_min < 30: return "pre_match"
    if elapsed_min < 210: return "in_play"
    return "post_match"

def occupancy(zone: str, phase: str) -> float:
    surge = 1.4 if phase == "post_match" and "exit" in zone else 1.0
    return min(100, BASE_OCCUPANCY.get(zone, 50) * surge + random.uniform(-10, 10))

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT, TOPIC)
start = time.time()

print(f"Publishing to {topic_path}. Press Ctrl+C to stop.")
while True:
    elapsed = int((time.time() - start) / 60)
    phase = get_phase(elapsed)
    for zone in ZONES:
        payload = json.dumps({
            "zone_id": zone,
            "count": round(occupancy(zone, phase), 1),
            "phase": phase,
            "ts": time.time()
        }).encode()
        publisher.publish(topic_path, data=payload)
    print(f"[sim] t+{elapsed}min  phase={phase}")
    time.sleep(15)
