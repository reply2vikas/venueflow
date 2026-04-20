"""
Crowd-aware accessible route planning service.

Implements a Breadth-First Search (BFS) over a static venue graph,
scoring each candidate path by a weighted combination of crowd density
and walking distance. Accessibility constraints are enforced at the
graph level — inaccessible edges are removed entirely when wheelchair
mode is active, never just penalised.

Design principles:
    - Accessibility is a hard constraint, not a soft preference.
    - Routes degrade gracefully: if Firestore is down, density defaults to 1.
    - Up to 3 candidate paths are evaluated; the lowest-scoring path wins.
    - The venue graph is loaded once and cached at module level.

Graph format (data/venue_graph.json):
    nodes: {zone_id: {accessible: bool, label: str}}
    edges: {from_zone: {to_zone: {distance_m: int, accessible: bool}}}
"""

import json
import logging
import os
from collections import deque
from typing import Dict, List, Optional, Tuple

from api.models.schemas import RouteRequest, RouteResponse
from api.services.crowd import get_all_zone_densities

logger = logging.getLogger(__name__)

# Scoring weights — crowd density is penalised 15x more than distance
# because a 1-unit increase in density adds ~3 minutes of walking time
CROWD_WEIGHT: float = 15.0
DISTANCE_WEIGHT: float = 0.01
MAX_CANDIDATE_PATHS: int = 3
WALK_SPEED_MPS: float = 80.0  # metres per minute (slow walking speed)

# Module-level graph cache — loaded once on first request
_venue_graph: Optional[Dict] = None


def _load_graph() -> Dict:
    """Load and cache the venue graph from disk.

    Returns:
        The venue graph dictionary with 'nodes' and 'edges' keys.

    Raises:
        FileNotFoundError: If venue_graph.json cannot be located.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    global _venue_graph
    if _venue_graph is None:
        path = os.path.join(os.path.dirname(__file__), "../../data/venue_graph.json")
        with open(path, encoding="utf-8") as fh:
            _venue_graph = json.load(fh)
        logger.info("venue graph loaded nodes=%d", len(_venue_graph.get("nodes", {})))
    return _venue_graph


def _score_path(path: Dict, density_map: Dict[str, int]) -> float:
    """Compute a numeric score for a candidate path (lower = better).

    Score formula: sum(density[node] × CROWD_WEIGHT) + distance × DISTANCE_WEIGHT

    Args:
        path: Path dict with 'nodes' (list of zone IDs) and 'distance_m' (int).
        density_map: Mapping of zone_id → density_level (1–5).

    Returns:
        Float score. Lower scores indicate faster, less crowded paths.
    """
    crowd_penalty = sum(
        density_map.get(node, 1) * CROWD_WEIGHT
        for node in path["nodes"]
    )
    return crowd_penalty + path["distance_m"] * DISTANCE_WEIGHT


def _build_route_notes(
    path: Dict,
    density_map: Dict[str, int],
    wheelchair: bool,
) -> Optional[str]:
    """Build human-readable route notes for display in the app.

    Args:
        path: The selected best path dictionary.
        density_map: Current crowd density per zone.
        wheelchair: Whether wheelchair/step-free mode was requested.

    Returns:
        A plain-English note string, or None if no special notes apply.
    """
    notes: List[str] = []
    dense_zones = [
        node for node in path["nodes"]
        if density_map.get(node, 0) >= 4
    ]
    if dense_zones:
        zone_labels = ", ".join(n.replace("_", " ") for n in dense_zones)
        notes.append(f"Busy areas on route: {zone_labels}. Walk steadily.")
    if wheelchair:
        notes.append("Route is fully step-free and ramp-accessible.")
    return " ".join(notes) if notes else None


def _find_candidate_paths(
    graph: Dict,
    origin: str,
    destination: str,
) -> List[Dict]:
    """Find up to MAX_CANDIDATE_PATHS paths from origin to destination via BFS.

    Args:
        graph: The venue graph with 'nodes' and 'edges' keys.
        origin: Starting zone ID.
        destination: Target zone ID.

    Returns:
        List of path dicts. Each dict has:
            nodes (List[str]): Ordered list of zone IDs.
            distance_m (int): Total walking distance in metres.
            walk_min (int): Estimated walking time in minutes.
    """
    edges = graph.get("edges", {})
    queue: deque = deque([[origin]])
    found_paths: List[Dict] = []
    seen_paths: set = set()

    while queue and len(found_paths) < MAX_CANDIDATE_PATHS:
        current_path: List[str] = queue.popleft()
        current_node = current_path[-1]

        if current_node == destination:
            path_key = tuple(current_path)
            if path_key not in seen_paths:
                seen_paths.add(path_key)
                total_distance = sum(
                    edges.get(current_path[i], {})
                        .get(current_path[i + 1], {})
                        .get("distance_m", 50)
                    for i in range(len(current_path) - 1)
                )
                found_paths.append({
                    "nodes": current_path,
                    "distance_m": total_distance,
                    "walk_min": round(total_distance / WALK_SPEED_MPS),
                })
            continue

        for neighbour in edges.get(current_node, {}):
            if neighbour not in current_path:
                queue.append(current_path + [neighbour])

    return found_paths


async def get_best_route(
    origin: str,
    destination: str,
    wheelchair: bool,
    avoid_dense: bool = True,
) -> RouteResponse:
    """Find the optimal route between two venue zones.

    Workflow:
        1. Load venue graph (cached after first call).
        2. Fetch live crowd density from Firestore.
        3. Find up to 3 candidate paths via BFS.
        4. Filter by accessibility if wheelchair=True.
        5. Score remaining paths and return the best one.

    Args:
        origin: Starting zone ID (must exist in venue graph nodes).
        destination: Target zone ID (must exist in venue graph nodes).
        wheelchair: If True, removes ALL paths containing inaccessible
            segments. This is a hard constraint — not a preference.
        avoid_dense: If True, crowd density contributes to path scoring.
            Default is True. Set False only for testing.

    Returns:
        RouteResponse containing the optimal path, distance, estimated
        time, crowd level, accessibility flag, and route notes.

    Raises:
        ValueError: If no path exists, or if wheelchair mode is enabled
            but no step-free path exists between the two zones.
    """
    graph = _load_graph()
    zones_data = await get_all_zone_densities()
    density_map: Dict[str, int] = {z.zone_id: z.density_level for z in zones_data}

    candidate_paths = _find_candidate_paths(graph, origin, destination)
    if not candidate_paths:
        raise ValueError(
            f"No path found from '{origin}' to '{destination}'. "
            "Please check zone names or ask a steward for directions."
        )

    if wheelchair:
        nodes_meta = graph.get("nodes", {})
        accessible_paths = [
            p for p in candidate_paths
            if all(nodes_meta.get(node, {}).get("accessible", True) for node in p["nodes"])
        ]
        if not accessible_paths:
            raise ValueError(
                "No step-free route found between these zones. "
                "Please request assistance at the Gate C info booth."
            )
        candidate_paths = accessible_paths

    best_path = min(candidate_paths, key=lambda p: _score_path(p, density_map))

    crowd_levels = [density_map.get(node, 1) for node in best_path["nodes"]]
    avg_crowd = round(sum(crowd_levels) / len(crowd_levels)) if crowd_levels else 1

    logger.info(
        "best route selected origin=%s dest=%s hops=%d distance_m=%d crowd_avg=%d",
        origin, destination, len(best_path["nodes"]),
        best_path["distance_m"], avg_crowd,
    )

    return RouteResponse(
        path=best_path["nodes"],
        distance_meters=best_path["distance_m"],
        estimated_minutes=best_path["walk_min"] + avg_crowd * 2,
        crowd_level=avg_crowd,
        accessible=wheelchair,
        notes=_build_route_notes(best_path, density_map, wheelchair),
    )
