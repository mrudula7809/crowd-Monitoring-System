"""
step1_core.py — Zone and CrowdManager OOP Core
Real-Time Crowd Intelligence and Decision Support System
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional
import random


# ─────────────────────────────────────────────
# Risk Level Constants
# ─────────────────────────────────────────────
RISK_SAFE     = "SAFE"
RISK_MODERATE = "MODERATE"
RISK_HIGH     = "HIGH"
RISK_CRITICAL = "CRITICAL"

DENSITY_THRESHOLDS = {
    RISK_SAFE:     (0.0,  2.0),
    RISK_MODERATE: (2.0,  4.0),
    RISK_HIGH:     (4.0,  6.0),
    RISK_CRITICAL: (6.0, float("inf")),
}

RISK_COLOR = {
    RISK_SAFE:     "🟢",
    RISK_MODERATE: "🟡",
    RISK_HIGH:     "🟠",
    RISK_CRITICAL: "🔴",
}


# ─────────────────────────────────────────────
# Data snapshot stored each tick
# ─────────────────────────────────────────────
@dataclass
class ZoneSnapshot:
    timestamp: datetime
    people_count: int
    density: float
    entry_rate: float
    exit_rate: float
    risk_level: str


# ─────────────────────────────────────────────
# Zone — physical location unit
# ─────────────────────────────────────────────
class Zone:
    def __init__(
        self,
        zone_id: str,
        name: str,
        area_sqm: float,
        capacity: int,
        initial_count: int = 0,
        entry_rate: float = 0.0,
        exit_rate: float = 0.0,
        adjacent_zones: Optional[List[str]] = None,
    ):
        self.zone_id        = zone_id
        self.name           = name
        self.area_sqm       = area_sqm          # m²
        self.capacity       = capacity          # max safe occupancy
        self.people_count   = initial_count
        self.entry_rate     = entry_rate        # people / tick
        self.exit_rate      = exit_rate         # people / tick
        self.adjacent_zones = adjacent_zones or []
        self.history: List[ZoneSnapshot] = []
        self.is_entry_restricted = False
        self.is_emergency         = False

    # ── derived metrics ─────────────────────
    @property
    def density(self) -> float:
        """people per m²"""
        return round(self.people_count / self.area_sqm, 4) if self.area_sqm > 0 else 0.0

    @property
    def occupancy_pct(self) -> float:
        return round((self.people_count / self.capacity) * 100, 1) if self.capacity > 0 else 0.0

    @property
    def risk_level(self) -> str:
        d = self.density
        for level, (lo, hi) in DENSITY_THRESHOLDS.items():
            if lo <= d < hi:
                return level
        return RISK_CRITICAL

    @property
    def net_flow(self) -> float:
        return self.entry_rate - self.exit_rate

    # ── tick update ──────────────────────────
    def tick(self, noise_factor: float = 0.15):
        """
        Advance simulation by one time step.
        Applies random noise to simulate real-world variability.
        """
        noisy_entry = max(0.0, self.entry_rate * (1 + random.uniform(-noise_factor, noise_factor)))
        noisy_exit  = max(0.0, self.exit_rate  * (1 + random.uniform(-noise_factor, noise_factor)))

        delta = int(noisy_entry - noisy_exit)
        self.people_count = max(0, self.people_count + delta)

        # Hard physical cap — cannot exceed 2× declared capacity
        self.people_count = min(self.people_count, self.capacity * 2)

        self._record_snapshot()

    def _record_snapshot(self):
        snap = ZoneSnapshot(
            timestamp    = datetime.now(),
            people_count = self.people_count,
            density      = self.density,
            entry_rate   = self.entry_rate,
            exit_rate    = self.exit_rate,
            risk_level   = self.risk_level,
        )
        self.history.append(snap)

    # ── control actions ──────────────────────
    def reduce_entry(self, factor: float = 0.3):
        self.entry_rate = max(0.0, self.entry_rate * (1 - factor))
        self.is_entry_restricted = True

    def increase_exit(self, factor: float = 0.4):
        self.exit_rate = self.exit_rate * (1 + factor)

    def close_entry(self):
        self.entry_rate = 0.0
        self.is_entry_restricted = True

    def open_entry(self, rate: float):
        self.entry_rate = rate
        self.is_entry_restricted = False

    def declare_emergency(self):
        self.is_emergency = True
        self.close_entry()
        self.exit_rate *= 2.0          # emergency exit boost

    # ── display ──────────────────────────────
    def status_line(self) -> str:
        icon = RISK_COLOR.get(self.risk_level, "⚪")
        return (
            f"{icon} [{self.zone_id}] {self.name:<22} | "
            f"People: {self.people_count:>5} | "
            f"Density: {self.density:>5.2f}/m² | "
            f"Occ: {self.occupancy_pct:>5.1f}% | "
            f"Risk: {self.risk_level:<8} | "
            f"Entry: {self.entry_rate:>5.1f}  Exit: {self.exit_rate:>5.1f}"
        )

    def __repr__(self):
        return f"Zone({self.zone_id}, {self.name}, density={self.density}, risk={self.risk_level})"


# ─────────────────────────────────────────────
# CrowdManager — manages all zones
# ─────────────────────────────────────────────
class CrowdManager:
    def __init__(self, venue_name: str):
        self.venue_name   = venue_name
        self.zones: Dict[str, Zone] = {}
        self.tick_number  = 0
        self.tick_log: List[Dict] = []

    def add_zone(self, zone: Zone):
        self.zones[zone.zone_id] = zone

    def get_zone(self, zone_id: str) -> Optional[Zone]:
        return self.zones.get(zone_id)

    def get_all_zones(self) -> List[Zone]:
        """Return all registered zones as a list of Zone objects."""
        return list(self.zones.values())

    def zone_exists(self, zone_id: str) -> bool:
        """Check whether a zone ID is registered."""
        return zone_id in self.zones

    def update_zone(self, zone_id: str, **kwargs):
        """
        Update attributes of an existing zone in-place.
        Supported keys: name, area_sqm, capacity, people_count,
                        entry_rate, exit_rate.
        Returns the updated Zone or None if not found.
        """
        zone = self.zones.get(zone_id)
        if zone is None:
            return None
        for attr in ("name", "area_sqm", "capacity", "people_count",
                     "entry_rate", "exit_rate"):
            if attr in kwargs:
                setattr(zone, attr, kwargs[attr])
        return zone

    def tick_all(self):
        """Advance all zones by one tick."""
        self.tick_number += 1
        for zone in self.zones.values():
            zone.tick()
        self._log_tick()

    def _log_tick(self):
        snapshot = {
            "tick": self.tick_number,
            "timestamp": datetime.now().isoformat(),
            "zones": {
                zid: {
                    "people": z.people_count,
                    "density": z.density,
                    "risk": z.risk_level,
                    "entry_rate": z.entry_rate,
                    "exit_rate": z.exit_rate,
                }
                for zid, z in self.zones.items()
            },
        }
        self.tick_log.append(snapshot)

    # ── summary helpers ──────────────────────
    def total_people(self) -> int:
        return sum(z.people_count for z in self.zones.values())

    def critical_zones(self) -> List[Zone]:
        return [z for z in self.zones.values() if z.risk_level == RISK_CRITICAL]

    def high_risk_zones(self) -> List[Zone]:
        return [z for z in self.zones.values() if z.risk_level in (RISK_HIGH, RISK_CRITICAL)]

    def safe_zones(self) -> List[Zone]:
        return [z for z in self.zones.values() if z.risk_level in (RISK_SAFE, RISK_MODERATE)]

    def sorted_by_density(self, ascending: bool = False) -> List[Zone]:
        return sorted(self.zones.values(), key=lambda z: z.density, reverse=not ascending)

    def print_dashboard(self):
        print("\n" + "═" * 100)
        print(f"  🏟  {self.venue_name.upper()}  —  TICK #{self.tick_number}  —  {datetime.now().strftime('%H:%M:%S')}")
        print(f"  Total People: {self.total_people():,}    Critical Zones: {len(self.critical_zones())}    High-Risk: {len(self.high_risk_zones())}")
        print("═" * 100)
        for zone in self.sorted_by_density():
            print("  " + zone.status_line())
        print("═" * 100)
