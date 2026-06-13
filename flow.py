"""
step3_flow.py — Flow Optimization Module
Graph-based crowd redistribution engine.
Zones = nodes, corridors/gates = weighted directed edges.
"""

from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
from core import Zone, CrowdManager, RISK_HIGH, RISK_CRITICAL, RISK_SAFE, RISK_MODERATE


# ─────────────────────────────────────────────
# Edge: corridor / gate between two zones
# ─────────────────────────────────────────────
@dataclass
class FlowEdge:
    from_zone: str
    to_zone:   str
    capacity:  float          # max people/tick that can move through
    is_open:   bool = True
    label:     str  = ""      # e.g. "Gate-4", "Corridor-B"

    @property
    def effective_capacity(self) -> float:
        return self.capacity if self.is_open else 0.0


# ─────────────────────────────────────────────
# Redistribution recommendation
# ─────────────────────────────────────────────
@dataclass
class RedistributionPlan:
    from_zone:  str
    to_zone:    str
    move_count: int
    urgency:    str           # IMMEDIATE / GRADUAL / ADVISORY
    via_edge:   str           # corridor/gate label
    rationale:  str


# ─────────────────────────────────────────────
# Flow Optimizer
# ─────────────────────────────────────────────
class FlowOptimizer:
    """
    Treats the venue as a directed graph.
    Detects overloaded zones and finds viable redistribution paths.
    Uses a greedy pressure-based algorithm (no heavy graph libraries needed).
    """

    def __init__(self, manager: CrowdManager):
        self.manager = manager
        self.edges: List[FlowEdge] = []
        self._adjacency: Dict[str, List[FlowEdge]] = {}   # from_zone → edges

    def add_edge(self, from_zone: str, to_zone: str, capacity: float, label: str = ""):
        """Add a directed edge. Validates both zones exist in the manager."""
        if not self.manager.zone_exists(from_zone):
            raise ValueError(f"Source zone '{from_zone}' does not exist in the system.")
        if not self.manager.zone_exists(to_zone):
            raise ValueError(f"Target zone '{to_zone}' does not exist in the system.")
        edge = FlowEdge(from_zone=from_zone, to_zone=to_zone, capacity=capacity, label=label)
        self.edges.append(edge)
        self._adjacency.setdefault(from_zone, []).append(edge)

    def add_bidirectional(self, zone_a: str, zone_b: str, capacity: float, label: str = ""):
        self.add_edge(zone_a, zone_b, capacity, label)
        self.add_edge(zone_b, zone_a, capacity, label)

    # ── edge query / update helpers ────────
    def get_edge(self, from_zone: str, to_zone: str) -> Optional[FlowEdge]:
        """Return the first open edge between two zones, or None."""
        for e in self._adjacency.get(from_zone, []):
            if e.to_zone == to_zone:
                return e
        return None

    def edge_exists(self, from_zone: str, to_zone: str) -> bool:
        return self.get_edge(from_zone, to_zone) is not None

    def update_edge_capacity(self, from_zone: str, to_zone: str, new_capacity: float) -> bool:
        """Update capacity of an existing edge (both directions). Returns True if found."""
        updated = False
        for e in self._adjacency.get(from_zone, []):
            if e.to_zone == to_zone:
                e.capacity = new_capacity
                updated = True
        for e in self._adjacency.get(to_zone, []):
            if e.to_zone == from_zone:
                e.capacity = new_capacity
                updated = True
        return updated

    def get_all_edges_summary(self) -> List[Dict]:
        """Return a deduplicated list of edge summaries for dashboard display."""
        seen = set()
        result = []
        for edge in self.edges:
            key = tuple(sorted([edge.from_zone, edge.to_zone]))
            if key in seen:
                continue
            seen.add(key)
            src = self.manager.get_zone(edge.from_zone)
            tgt = self.manager.get_zone(edge.to_zone)
            result.append({
                "from_id": edge.from_zone,
                "to_id": edge.to_zone,
                "from_name": src.name if src else edge.from_zone,
                "to_name": tgt.name if tgt else edge.to_zone,
                "capacity": edge.capacity,
                "is_open": edge.is_open,
                "label": edge.label,
            })
        return result

    def get_bottlenecks(self) -> List[Dict]:
        """
        Identify overloaded corridors — edges where the connected source zone
        has HIGH/CRITICAL risk and the corridor capacity is < net inflow.
        """
        bottlenecks = []
        seen = set()
        for edge in self.edges:
            key = tuple(sorted([edge.from_zone, edge.to_zone]))
            if key in seen:
                continue
            seen.add(key)
            src = self.manager.get_zone(edge.from_zone)
            if src and src.risk_level in (RISK_HIGH, RISK_CRITICAL):
                if src.net_flow > edge.capacity:
                    bottlenecks.append({
                        "edge": edge,
                        "from_name": src.name,
                        "to_name": (self.manager.get_zone(edge.to_zone) or edge).to_zone
                                   if not self.manager.get_zone(edge.to_zone)
                                   else self.manager.get_zone(edge.to_zone).name,
                        "overflow": src.net_flow - edge.capacity,
                    })
        return bottlenecks

    # ── graph queries ──────────────────────
    def reachable_safe_zones(self, from_zone: str, visited: Optional[Set[str]] = None) -> List[str]:
        """BFS to find all safe zones reachable from a given zone."""
        if visited is None:
            visited = set()
        visited.add(from_zone)
        result = []
        for edge in self._adjacency.get(from_zone, []):
            if not edge.is_open or edge.to_zone in visited:
                continue
            z = self.manager.get_zone(edge.to_zone)
            if z and z.risk_level in (RISK_SAFE, RISK_MODERATE):
                result.append(edge.to_zone)
            # recurse
            result.extend(self.reachable_safe_zones(edge.to_zone, visited))
        return list(dict.fromkeys(result))   # deduplicate, preserve order

    def _pressure_score(self, zone: Zone) -> float:
        """Higher = more urgent to relieve pressure."""
        return zone.density * (zone.people_count / max(zone.capacity, 1))

    def _slack_score(self, zone: Zone) -> float:
        """Higher = more room to absorb incoming crowd."""
        remaining = zone.capacity - zone.people_count
        return max(0.0, remaining / max(zone.capacity, 1))

    # ── main optimization ──────────────────
    def compute_redistribution(self) -> List[RedistributionPlan]:
        plans: List[RedistributionPlan] = []
        overloaded = self.manager.high_risk_zones()

        for src in sorted(overloaded, key=self._pressure_score, reverse=True):
            safe_targets = self.reachable_safe_zones(src.zone_id)
            if not safe_targets:
                continue

            # Sort targets by slack (most room first)
            target_zones = [
                self.manager.get_zone(zid)
                for zid in safe_targets
                if self.manager.get_zone(zid) is not None
            ]
            target_zones.sort(key=self._slack_score, reverse=True)

            surplus_people = max(0, src.people_count - src.capacity)
            if surplus_people == 0:
                surplus_people = max(0, src.people_count - int(src.capacity * 0.75))

            remaining_to_move = surplus_people

            for tgt in target_zones:
                if remaining_to_move <= 0:
                    break

                # find best edge between src and tgt
                edge = self._best_edge(src.zone_id, tgt.zone_id)
                if edge is None or not edge.is_open:
                    continue

                space_in_target = tgt.capacity - tgt.people_count
                moveable = min(
                    remaining_to_move,
                    int(edge.capacity),
                    max(0, space_in_target),
                )
                if moveable <= 0:
                    continue

                urgency = (
                    "IMMEDIATE" if src.risk_level == RISK_CRITICAL else
                    "GRADUAL"   if src.risk_level == RISK_HIGH      else
                    "ADVISORY"
                )

                plans.append(RedistributionPlan(
                    from_zone  = src.zone_id,
                    to_zone    = tgt.zone_id,
                    move_count = moveable,
                    urgency    = urgency,
                    via_edge   = edge.label or f"{src.zone_id}→{tgt.zone_id}",
                    rationale  = (
                        f"{src.name} at {src.occupancy_pct:.0f}% capacity "
                        f"(density {src.density:.2f}/m²); "
                        f"{tgt.name} has {space_in_target} free slots."
                    ),
                ))
                remaining_to_move -= moveable

        return plans

    def _best_edge(self, from_id: str, to_id: str) -> Optional[FlowEdge]:
        candidates = [
            e for e in self._adjacency.get(from_id, [])
            if e.to_zone == to_id and e.is_open
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda e: e.capacity)

    # ── control actions ────────────────────
    def close_edge(self, from_zone: str, to_zone: str):
        for e in self._adjacency.get(from_zone, []):
            if e.to_zone == to_zone:
                e.is_open = False

    def open_edge(self, from_zone: str, to_zone: str):
        for e in self._adjacency.get(from_zone, []):
            if e.to_zone == to_zone:
                e.is_open = True

    # ── display ────────────────────────────
    def print_flow_summary(self, plans: List[RedistributionPlan]):
        if not plans:
            print("  ✅ No redistribution needed. All zones within safe limits.")
            return
        print(f"\n  📦 FLOW REDISTRIBUTION PLAN  ({len(plans)} actions)")
        print("  " + "─" * 80)
        for i, p in enumerate(plans, 1):
            urgency_icon = {"IMMEDIATE": "🚨", "GRADUAL": "⚠️", "ADVISORY": "ℹ️"}.get(p.urgency, "")
            src = self.manager.get_zone(p.from_zone)
            tgt = self.manager.get_zone(p.to_zone)
            print(f"  {i}. {urgency_icon} [{p.urgency}]")
            print(f"     FROM  → {src.name if src else p.from_zone}")
            print(f"     TO    → {tgt.name if tgt else p.to_zone}")
            print(f"     MOVE  → {p.move_count} people  via {p.via_edge}")
            print(f"     WHY   → {p.rationale}")
            print()

    def print_graph_topology(self):
        print("\n  🗺  VENUE GRAPH TOPOLOGY")
        print("  " + "─" * 60)
        seen = set()
        for edge in self.edges:
            key = tuple(sorted([edge.from_zone, edge.to_zone]))
            if key in seen:
                continue
            seen.add(key)
            status = "OPEN" if edge.is_open else "CLOSED"
            print(f"  {edge.from_zone} ↔ {edge.to_zone}  [{edge.label}]  cap={edge.capacity}  {status}")
