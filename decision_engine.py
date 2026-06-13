"""
decision_engine.py — Decision & Suggestion Engine
Produces structured, actionable control-room recommendations.
NOT just "HIGH RISK" — outputs WHAT, WHERE, HOW URGENT.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
from core import Zone, CrowdManager, RISK_SAFE, RISK_MODERATE, RISK_HIGH, RISK_CRITICAL


# ─────────────────────────────────────────────
# Decision data structure
# ─────────────────────────────────────────────
@dataclass
class Decision:
    tick:         int
    zone_id:      str
    zone_name:    str
    risk_level:   str
    urgency:      str          # P1 CRITICAL / P2 HIGH / P3 MODERATE / P4 LOW
    action:       str          # What to do
    target_zones: List[str]    # Where to redirect people (if applicable)
    message:      str          # Human-readable instruction for operators
    predicted_density_5min: Optional[float] = None
    auto_applied: bool = False  # whether system auto-applied this

    def display(self):
        urgency_icon = {"CRITICAL": "🚨", "HIGH": "⚠️",
                        "MODERATE": "🟡", "LOW": "ℹ️"}.get(self.urgency, "")
        print(f"\n  {urgency_icon} [{self.urgency}]  Zone: {self.zone_name}  ({self.zone_id})")
        print(f"     Risk     → {self.risk_level}")
        print(f"     Action   → {self.action}")
        if self.target_zones:
            print(f"     Redirect → {', '.join(self.target_zones)}")
        print(f"     Message  → {self.message}")
        if self.predicted_density_5min:
            print(f"     Forecast → Density in 5 min: {self.predicted_density_5min:.2f}/m²")
        if self.auto_applied:
            print(f"     Status   → ✅ Auto-applied")


# ─────────────────────────────────────────────
# Decision Engine
# ─────────────────────────────────────────────
class DecisionEngine:
    """
    Evaluates each zone's current state + ML forecast and produces
    structured, prioritised decisions for control-room operators.
    """

    def __init__(self, manager: CrowdManager, predictor=None, auto_apply: bool = False):
        self.manager    = manager
        self.predictor  = predictor     # step2_ml.CrowdPredictor (optional)
        self.auto_apply = auto_apply    # if True, automatically adjusts flow rates
        self.decision_log: List[Decision] = []
        self.alert_log: List[str] = []

    # ── main evaluation ─────────────────────
    def evaluate(self, tick: int, redistribution_plans=None) -> List[Decision]:
        """
        Runs once per tick.  Returns list of Decisions sorted by urgency.
        """
        decisions: List[Decision] = []
        safe_zones = [z for z in self.manager.zones.values()
                      if z.risk_level in (RISK_SAFE, RISK_MODERATE)]

        for zone in self.manager.sorted_by_density():
            d = self._evaluate_zone(zone, tick, safe_zones, redistribution_plans)
            if d:
                decisions.append(d)

        # Sort: P1 first
        priority_map = {"P1 CRITICAL": 0, "P2 HIGH": 1, "P3 MODERATE": 2, "P4 LOW": 3}
        decisions.sort(key=lambda x: priority_map.get(x.urgency, 9))

        self.decision_log.extend(decisions)

        # Auto-apply if enabled
        if self.auto_apply:
            for d in decisions:
                self._auto_apply(d)

        return decisions

    def _evaluate_zone(self, zone: Zone, tick: int, safe_zones: List[Zone], plans=None) -> Optional[Decision]:
        risk    = zone.risk_level
        density = zone.density

        # Get ML forecast if predictor available
        pred_density_5 = None
        if self.predictor:
            pred = self.predictor.predict_at_minutes(zone.zone_id, 5)
            if pred["predicted_count"]:
                pred_density_5 = round(pred["predicted_count"] / zone.area_sqm, 2)

        if plans:
            target_zone_ids = [p.to_zone for p in plans if p.from_zone == zone.zone_id]
            safe_zone_names = []
            for zid in target_zone_ids:
                z = self.manager.get_zone(zid)
                if z and z.name not in safe_zone_names:
                    safe_zone_names.append(z.name)
        else:
            safe_zone_names = []

        safe_zone_str = ', '.join(safe_zone_names) if safe_zone_names else "safe locations (no connected safe zones found)"

        # ── CRITICAL: immediate action ───────
        if risk == RISK_CRITICAL or (pred_density_5 and pred_density_5 >= 6.0):
            urgency    = "P1 CRITICAL"
            action     = "CLOSE ALL ENTRY GATES IMMEDIATELY. Activate emergency evacuation protocols."
            message    = (
                f"⚠️  STAMPEDE RISK at {zone.name}! "
                f"Density {density:.2f}/m² exceeds safe limit. "
                f"Dispatch crowd control personnel. "
                f"Open emergency exits. Redirect all inflow to {safe_zone_str}."
            )
            target_zones = safe_zone_names

        # ── HIGH: controlled action ──────────
        elif risk == RISK_HIGH or (pred_density_5 and pred_density_5 >= 4.0):
            urgency    = "P2 HIGH"
            action     = f"Reduce entry by 40%. Open additional exit lanes. Announce diversions."
            message    = (
                f"High crowding at {zone.name} (density {density:.2f}/m²). "
                f"Throttle entry gates. Deploy PA system: redirect crowd to "
                f"{safe_zone_str}. "
                f"Monitor next 5 minutes closely."
            )
            target_zones = safe_zone_names

        # ── MODERATE: preventive action ──────
        elif risk == RISK_MODERATE:
            if zone.net_flow > 5:           # still filling fast
                urgency  = "P3 MODERATE"
                action   = "Reduce entry by 20%. Monitor density trend."
                message  = (
                    f"{zone.name} filling at +{zone.net_flow:.1f} people/tick. "
                    f"Pre-emptive slowdown recommended. "
                    f"Alert nearby zones to expect overflow."
                )
                target_zones = safe_zone_names[:2]
            else:
                return None  # no action needed for stable moderate zones

        # ── SAFE: check if overcrowded neighbour can send crowd here ─
        elif risk == RISK_SAFE:
            slack = zone.capacity - zone.people_count
            if slack > 100:
                urgency      = "P4 LOW"
                action       = "Zone has capacity. Ready to receive redirected crowd."
                message      = f"{zone.name} has {slack} free slots. Can accept overflow from high-risk zones."
                target_zones = []
            else:
                return None

        else:
            return None

        dec = Decision(
            tick         = tick,
            zone_id      = zone.zone_id,
            zone_name    = zone.name,
            risk_level   = risk,
            urgency      = urgency,
            action       = action,
            target_zones = target_zones,
            message      = message,
            predicted_density_5min = pred_density_5,
        )
        return dec

    # ── auto-apply logic ─────────────────────
    def _auto_apply(self, decision: Decision):
        zone = self.manager.get_zone(decision.zone_id)
        if not zone:
            return

        if decision.urgency == "P1 CRITICAL" and not zone.is_emergency:
            zone.declare_emergency()
            decision.auto_applied = True
            self.alert_log.append(
                f"[TICK {decision.tick}] AUTO: Emergency declared at {zone.name}"
            )

        elif decision.urgency == "P2 HIGH" and not zone.is_entry_restricted:
            zone.reduce_entry(factor=0.4)
            zone.increase_exit(factor=0.3)
            decision.auto_applied = True
            self.alert_log.append(
                f"[TICK {decision.tick}] AUTO: Entry reduced 40% at {zone.name}"
            )

        elif decision.urgency == "P3 MODERATE" and not zone.is_entry_restricted:
            zone.reduce_entry(factor=0.2)
            decision.auto_applied = True

    # ── report ───────────────────────────────
    def print_decisions(self, decisions: List[Decision], tick: int):
        print(f"\n  {'─'*80}")
        print(f"  🧠 DECISION ENGINE — TICK #{tick}  [{datetime.now().strftime('%H:%M:%S')}]")
        print(f"  {'─'*80}")

        if not decisions:
            print("  ✅ All zones nominal. No action required.")
            return

        p1 = [d for d in decisions if d.urgency == "P1 CRITICAL"]
        p2 = [d for d in decisions if d.urgency == "P2 HIGH"]
        p3 = [d for d in decisions if d.urgency == "P3 MODERATE"]
        p4 = [d for d in decisions if d.urgency == "P4 LOW"]

        print(f"  Summary: 🚨 P1={len(p1)}  ⚠️  P2={len(p2)}  🟡 P3={len(p3)}  ℹ️  P4={len(p4)}")

        for d in decisions:
            d.display()

    def print_alert_log(self):
        if self.alert_log:
            print("\n  📋 AUTO-ACTION LOG:")
            for line in self.alert_log[-10:]:
                print(f"     {line}")

    def summary_report(self) -> str:
        total     = len(self.decision_log)
        critical  = sum(1 for d in self.decision_log if d.urgency == "P1 CRITICAL")
        auto_acts = sum(1 for d in self.decision_log if d.auto_applied)
        return (
            f"Decision Summary: {total} decisions issued | "
            f"{critical} critical alerts | {auto_acts} auto-applied"
        )
