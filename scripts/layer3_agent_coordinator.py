#!/usr/bin/env python3
"""Layer 3: Agent coordination for evacuation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from layer1_disaster_data import find_nearest_evacuation, haversine_m

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = BASE_DIR / "data" / "disaster" / "coordination_test_result.json"


@dataclass
class ChildAgent:
    agent_id: str
    child_name: str
    lat: float
    lon: float
    elevation_m: float
    state: str = "NORMAL"
    assigned_route_id: Optional[str] = None


class AgentCoordinator:
    def __init__(self) -> None:
        self.agents: Dict[str, ChildAgent] = {}
        self._last_center_lat: float = 0.0
        self._last_center_lon: float = 0.0

    def register_agent(self, agent: ChildAgent) -> None:
        self.agents[agent.agent_id] = agent

    def coordinate_evacuation(
        self,
        disaster_type: str,
        affected_region_lat: float,
        affected_region_lon: float,
        severity: int,
    ) -> Dict[str, Any]:
        self._last_center_lat = affected_region_lat
        self._last_center_lon = affected_region_lon

        affected = [
            a
            for a in self.agents.values()
            if self._is_in_affected_zone(
                a.lat, a.lon, affected_region_lat, affected_region_lon, disaster_type
            )
        ]
        affected.sort(key=lambda a: a.elevation_m)

        routes = self._get_evacuation_routes(affected, disaster_type)
        assignments = self._assign_routes_balanced(affected, routes, disaster_type)

        instructions = []
        for agent in affected:
            route = assignments.get(agent.agent_id)
            if route is None:
                continue
            agent.assigned_route_id = route["route_id"]
            agent.state = "EVACUATING" if severity >= 3 else "ALERT"
            instructions.append(self._send_evacuation_instruction(agent.agent_id, route, disaster_type))

        return {
            "disaster_type": disaster_type,
            "severity": severity,
            "affected_agents": affected,
            "routes": routes,
            "assignments": assignments,
            "instructions": instructions,
            "process_order": [a.agent_id for a in affected],
        }

    def _is_in_affected_zone(
        self,
        lat: float,
        lon: float,
        center_lat: float,
        center_lon: float,
        disaster_type: str,
    ) -> bool:
        thresholds_km = {
            "tsunami": 20.0,
            "earthquake": 100.0,
            "flood": 5.0,
            "flood_wind": 5.0,
        }
        threshold_km = thresholds_km.get(disaster_type, 20.0)
        return haversine_m(lat, lon, center_lat, center_lon) <= threshold_km * 1000

    def _get_evacuation_routes(self, agents: List[ChildAgent], disaster_type: str) -> List[Dict[str, Any]]:
        if not agents:
            return []

        nearest = find_nearest_evacuation(
            self._last_center_lat,
            self._last_center_lon,
            disaster_type,
            max_results=5,
        )

        routes: List[Dict[str, Any]] = []
        for idx, site in enumerate(nearest):
            routes.append(
                {
                    "route_id": f"route_{idx}",
                    "start": {"lat": self._last_center_lat, "lon": self._last_center_lon},
                    "end": {"lat": site["lat"], "lon": site["lon"]},
                    "dest_name": site.get("name", ""),
                    "distance_m": float(site.get("_dist_m", 0.0)),
                    "max_elevation_m": float(site.get("elevation_m", 0.0) or 0.0),
                    "capacity": site.get("capacity"),
                    "load": 0,
                }
            )
        return routes

    def _assign_routes_balanced(
        self,
        agents: List[ChildAgent],
        routes: List[Dict[str, Any]],
        disaster_type: str,
    ) -> Dict[str, Dict[str, Any]]:
        assignments: Dict[str, Dict[str, Any]] = {}
        if not routes:
            return assignments

        for agent in sorted(agents, key=lambda x: x.elevation_m):
            best_route = None
            best_score = float("inf")

            for route in routes:
                cap = route.get("capacity")
                if cap is not None and isinstance(cap, int) and cap > 0 and route["load"] >= cap:
                    continue

                dist = haversine_m(agent.lat, agent.lon, route["end"]["lat"], route["end"]["lon"])
                dist_score = dist / 1000.0
                congestion_penalty = route["load"] * 0.3
                elevation_bonus = route["max_elevation_m"] * 0.05 if disaster_type == "tsunami" else 0.0
                score = dist_score + congestion_penalty - elevation_bonus

                if score < best_score:
                    best_score = score
                    best_route = route

            if best_route is None:
                best_route = min(routes, key=lambda r: r["load"])

            best_route["load"] += 1
            assignments[agent.agent_id] = {
                **best_route,
                "agent_distance_m": haversine_m(
                    agent.lat,
                    agent.lon,
                    best_route["end"]["lat"],
                    best_route["end"]["lon"],
                ),
            }

        return assignments

    def _send_evacuation_instruction(
        self,
        agent_id: str,
        route: Dict[str, Any],
        disaster_type: str,
    ) -> Dict[str, Any]:
        instruction = {
            "agent_id": agent_id,
            "disaster_type": disaster_type,
            "route_id": route["route_id"],
            "destination": route.get("dest_name", ""),
            "distance_m": round(route.get("agent_distance_m", route.get("distance_m", 0.0)), 1),
        }
        print(
            f"[INSTRUCTION] {agent_id} -> {instruction['route_id']}"
            f" ({instruction['destination']}, {instruction['distance_m']}m)"
        )
        return instruction


def test_coordination() -> Dict[str, Any]:
    coordinator = AgentCoordinator()

    agents = [
        ChildAgent("agent_alice", "Alice", 35.6581, 139.7516, 5.0),
        ChildAgent("agent_bob", "Bob", 35.6581, 139.7516, 8.0),
        ChildAgent("agent_charlie", "Charlie", 35.6895, 139.6917, 30.0),
        ChildAgent("agent_daisy", "Daisy", 35.7090, 139.7319, 15.0),
        ChildAgent("agent_ethan", "Ethan", 35.6284, 139.7387, 3.0),
    ]
    for agent in agents:
        coordinator.register_agent(agent)

    result = coordinator.coordinate_evacuation("tsunami", 35.665, 139.74, 4)

    affected_agents = result["affected_agents"]
    assignments = result["assignments"]

    assignment_rows = []
    route_distribution: Dict[str, int] = {}
    for agent in affected_agents:
        route = assignments.get(agent.agent_id)
        if not route:
            continue
        route_id = route["route_id"]
        route_distribution[route_id] = route_distribution.get(route_id, 0) + 1
        assignment_rows.append(
            {
                "agent_id": agent.agent_id,
                "route_id": route_id,
                "distance_m": round(route.get("agent_distance_m", 0.0), 1),
                "max_elevation_m": route.get("max_elevation_m", 0.0),
            }
        )

    process_order = result.get("process_order", [])
    lowest_elevation_first = process_order[:2] == ["agent_ethan", "agent_alice"]
    ethan_order = process_order.index("agent_ethan") + 1 if "agent_ethan" in process_order else -1

    output = {
        "test_case": "5_agents_tsunami",
        "total_agents": len(agents),
        "affected_agents": len(affected_agents),
        "assignments": assignment_rows,
        "route_distribution": route_distribution,
        "lowest_elevation_first": lowest_elevation_first,
        "ethan_order": ethan_order,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    return output


if __name__ == "__main__":
    test = test_coordination()
    print(json.dumps(test, ensure_ascii=False, indent=2))
