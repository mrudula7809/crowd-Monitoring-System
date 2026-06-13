"""
main.py — Real-Time Crowd Intelligence Control Terminal
Interactive control-room style system with live menu loop.

Usage:
    python main.py
"""

import sys
import time
import os
import random
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

BANNER = """
╔══════════════════════════════════════════════════════════════════════════╗
║       CROWD INTELLIGENCE — REAL-TIME CONTROL TERMINAL                  ║
║       Live Interactive Decision Support System                         ║
╚════════════════════════════════════════════════════════════════════╝"""

MENU = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  CONTROL ROOM — MAIN MENU
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [1]  Add / Update Zone
  [2]  Update Crowd in Zone
  [3]  Define / Update Graph Edge
  [4]  Run Forecast (ML)
  [5]  Run Risk Analysis
  [6]  Trigger Live Simulation Tick
  [7]  Emergency Mode (Auto Control)
  [8]  View System State Dashboard
  [9]  Exit System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""

RISK_ICON = {"SAFE": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}


def get_int(prompt, default=0, lo=0, hi=10_000_000):
    while True:
        try:
            raw = input(f"  {prompt} [{default}]: ").strip()
            v = int(raw) if raw else default
            if lo <= v <= hi:
                return v
            print(f"    ↳ Must be {lo}–{hi}")
        except ValueError:
            print("    ↳ Enter a valid integer.")


def get_float(prompt, default=0.0, lo=0.0, hi=1e9):
    while True:
        try:
            raw = input(f"  {prompt} [{default}]: ").strip()
            v = float(raw) if raw else default
            if lo <= v <= hi:
                return v
            print(f"    ↳ Must be {lo}–{hi}")
        except ValueError:
            print("    ↳ Enter a valid number.")


def get_str(prompt, default=""):
    raw = input(f"  {prompt} [{default}]: ").strip()
    return raw if raw else default


def section(title):
    w = 60
    print(f"\n{'━' * w}")
    print(f"  {title}")
    print(f"{'━' * w}")


# ─────────────────────────────────────────────────────────────────────────
# CrowdControlTerminal — main interactive controller
# ─────────────────────────────────────────────────────────────────────────
class CrowdControlTerminal:

    def __init__(self):
        from core import CrowdManager
        from ml import CrowdPredictor
        from flow import FlowOptimizer
        from db import DatabaseManager
        from decision_engine import DecisionEngine

        self.venue = get_str("Venue / Event Name", "Control Room")
        self.manager = CrowdManager(self.venue)
        self.predictor = CrowdPredictor(tick_seconds=60)
        self.optimizer = FlowOptimizer(self.manager)
        self.engine = DecisionEngine(self.manager, predictor=self.predictor, auto_apply=True)
        self.db = DatabaseManager(use_mysql=True, verbose=False)
        self.emergency_active = False
        self.tick = 0
        self.zone_histories = {}
        self.risk_timelines = {}

    # ── main loop ────────────────────────────
    def run(self):
        clear_screen()
        print(BANNER)
        print(f"\n  System initialised for: {self.venue}")
        print("  Add zones to begin.\n")

        while True:
            print(MENU)
            choice = input("  Select option ▶ ").strip()

            if   choice == "1": self._add_update_zone()
            elif choice == "2": self._update_crowd()
            elif choice == "3": self._define_edge()
            elif choice == "4": self._run_forecast()
            elif choice == "5": self._run_risk_analysis()
            elif choice == "6": self._live_simulation()
            elif choice == "7": self._emergency_mode()
            elif choice == "8": self._dashboard()
            elif choice == "9":
                print("\n  ⛔ Shutting down control terminal.\n")
                break
            else:
                print("  ↳ Invalid option. Enter 1–9.")

    # ════════════════════════════════════════
    # [1] ADD / UPDATE ZONE
    # ════════════════════════════════════════
    def _add_update_zone(self):
        from core import Zone
        section("ADD / UPDATE ZONE")

        zone_id = get_str("Zone ID (e.g. Z1)", "").upper()
        if not zone_id:
            print("  ✗ Zone ID cannot be empty."); return

        if self.manager.zone_exists(zone_id):
            print(f"  ℹ Zone '{zone_id}' exists — entering UPDATE mode.")
            old = self.manager.get_zone(zone_id)
            name = get_str("  Zone Name", old.name)
            area = get_float("  Area (m²)", old.area_sqm, 1)
            cap  = get_int("  Capacity", old.capacity, 1)
            ppl  = get_int("  People count", old.people_count, 0, cap * 2)
            self.manager.update_zone(zone_id, name=name, area_sqm=area,
                                     capacity=cap, people_count=ppl)
            print(f"  ✅ Zone '{zone_id}' updated.")
        else:
            name = get_str("  Zone Name", zone_id)
            area = get_float("  Area (m²)", 500.0, 1)
            cap  = get_int("  Capacity", 1000, 1)
            ppl  = get_int("  Initial People (optional)", 0, 0, cap * 2)
            z = Zone(zone_id=zone_id, name=name, area_sqm=area,
                     capacity=cap, initial_count=ppl)
            self.manager.add_zone(z)
            self.zone_histories[zone_id] = []
            self.risk_timelines[zone_id] = []
            print(f"  ✅ Zone '{zone_id}' ({name}) added.")
            
        # Log to backend database
        z = self.manager.get_zone(zone_id)
        if z:
            self.db.insert_crowd_log(
                zone_id=z.zone_id,
                zone_name=z.name,
                entry_rate=z.entry_rate,
                exit_rate=z.exit_rate,
                people=z.people_count,
                density=z.density,
                capacity=z.capacity
            )

        self._reactive_check()

    # ════════════════════════════════════════
    # [2] UPDATE CROWD
    # ════════════════════════════════════════
    def _update_crowd(self):
        section("UPDATE CROWD IN ZONE")
        if not self.manager.get_all_zones():
            print("  ✗ No zones registered. Add zones first."); return

        self._list_zone_ids()
        zone_id = get_str("Zone ID to update", "").upper()

        if not self.manager.zone_exists(zone_id):
            print(f"  ✗ Zone '{zone_id}' does NOT exist. Use option [1] to create it first.")
            return

        zone = self.manager.get_zone(zone_id)
        print(f"  Current → People: {zone.people_count}  Entry: {zone.entry_rate}  Exit: {zone.exit_rate}")

        ppl = get_int("  New people count", zone.people_count, 0, zone.capacity * 2)
        ent = get_float("  Entry rate (ppl/tick)", zone.entry_rate, 0)
        ext = get_float("  Exit rate  (ppl/tick)", zone.exit_rate, 0)

        zone.people_count = ppl
        zone.entry_rate = ent
        zone.exit_rate = ext
        print(f"  ✅ Zone '{zone_id}' crowd updated.")
        self._reactive_check()

    # ════════════════════════════════════════
    # [3] DEFINE / UPDATE GRAPH EDGE
    # ════════════════════════════════════════
    def _define_edge(self):
        section("DEFINE / UPDATE GRAPH EDGE")
        if len(self.manager.get_all_zones()) < 2:
            print("  ✗ Need at least 2 zones to create edges."); return

        self._list_zone_ids()
        fz = get_str("From Zone ID", "").upper()
        tz = get_str("To Zone ID", "").upper()

        if not self.manager.zone_exists(fz):
            print(f"  ✗ Zone '{fz}' does not exist."); return
        if not self.manager.zone_exists(tz):
            print(f"  ✗ Zone '{tz}' does not exist."); return
        if fz == tz:
            print("  ✗ Cannot create edge from a zone to itself."); return

        cap = get_float("Corridor capacity (ppl/tick)", 100, 1)
        label = get_str("Label (e.g. Gate-1)", f"{fz}→{tz}")

        if self.optimizer.edge_exists(fz, tz):
            self.optimizer.update_edge_capacity(fz, tz, cap)
            print(f"  ✅ Edge {fz} ↔ {tz} updated (capacity={cap}).")
        else:
            try:
                self.optimizer.add_bidirectional(fz, tz, cap, label)
                print(f"  ✅ Edge {fz} ↔ {tz} created (capacity={cap}, label={label}).")
            except ValueError as e:
                print(f"  ✗ {e}"); return

        self._reactive_check()

    # ════════════════════════════════════════
    # [4] RUN FORECAST (ML)
    # ════════════════════════════════════════
    def _run_forecast(self):
        section("ML FORECAST")
        zones = self.manager.get_all_zones()
        if not zones:
            print("  ✗ No zones. Add zones and run ticks first."); return

        for zone in zones:
            self.predictor.feed(zone.zone_id, zone.people_count)

        print(f"\n  {'Zone':<20} {'Now':>7} {'  +5min':>7} {'  +10min':>8} {' +15min':>8}  {'Trend':<24}")
        print("  " + "─" * 82)
        for zone in zones:
            preds = self.predictor.predict_range(zone.zone_id)
            p5  = preds[0].get("predicted_count", "—") if len(preds) > 0 else "—"
            p10 = preds[1].get("predicted_count", "—") if len(preds) > 1 else "—"
            p15 = preds[2].get("predicted_count", "—") if len(preds) > 2 else "—"
            trend = self.predictor.es.trend_direction(zone.zone_id)
            icon = RISK_ICON.get(zone.risk_level, "⚪")
            p5s  = str(p5) if p5 is not None else "—"
            p10s = str(p10) if p10 is not None else "—"
            p15s = str(p15) if p15 is not None else "—"
            print(f"  {icon} {zone.name:<18} {zone.people_count:>7} {p5s:>7} {p10s:>8} {p15s:>8}  {trend}")

    # ════════════════════════════════════════
    # [5] RUN RISK ANALYSIS
    # ════════════════════════════════════════
    def _run_risk_analysis(self):
        section("RISK ANALYSIS")
        zones = self.manager.get_all_zones()
        if not zones:
            print("  ✗ No zones registered."); return

        plans = self.optimizer.compute_redistribution()
        decisions = self.engine.evaluate(self.tick, plans)
        self.engine.print_decisions(decisions, self.tick)
        self.engine.print_alert_log()

        if plans:
            self.optimizer.print_flow_summary(plans)

    # ════════════════════════════════════════
    # [6] LIVE SIMULATION
    # ════════════════════════════════════════
    def _live_simulation(self):
        section("LIVE SIMULATION MODE")
        zones = self.manager.get_all_zones()
        if not zones:
            print("  ✗ No zones. Add zones first."); return

        delay = get_float("Tick delay (seconds)", 1.0, 0.1, 10)
        print("  ▶ Simulation running. Press Ctrl+C to stop.\n")

        try:
            while True:
                self.tick += 1

                # Advance each zone
                for zone in self.manager.get_all_zones():
                    zone.tick()
                    self.predictor.feed(zone.zone_id, zone.people_count)
                    self.zone_histories.setdefault(zone.zone_id, []).append({
                        "tick": self.tick, "density": zone.density,
                        "people": zone.people_count, "entry": zone.entry_rate,
                        "exit": zone.exit_rate, "zone_name": zone.name,
                    })
                    self.risk_timelines.setdefault(zone.zone_id, []).append(
                        (self.tick, zone.risk_level))

                self.manager.tick_number = self.tick

                # Decision engine
                plans = self.optimizer.compute_redistribution()
                decisions = self.engine.evaluate(self.tick, plans)

                # Dashboard
                clear_screen()
                print(BANNER)
                self._print_zone_table()

                # Alerts
                crit = [d for d in decisions if d.urgency == "P1 CRITICAL"]
                high = [d for d in decisions if d.urgency == "P2 HIGH"]
                if crit or high:
                    print(f"\n  🚨 ALERTS: {len(crit)} CRITICAL, {len(high)} HIGH")
                    for d in (crit + high)[:5]:
                        d.display()

                print(f"\n  ⏱  Tick #{self.tick}  |  Press Ctrl+C to stop")
                time.sleep(delay)

        except KeyboardInterrupt:
            print("\n\n  ⏸  Simulation paused. Returning to menu.")

    # ════════════════════════════════════════
    # [7] EMERGENCY MODE
    # ════════════════════════════════════════
    def _emergency_mode(self):
        section("🚨 EMERGENCY MODE ACTIVATED 🚨")
        zones = self.manager.get_all_zones()
        if not zones:
            print("  ✗ No zones registered."); return

        self.emergency_active = True

        for zone in zones:
            zone.declare_emergency()

        print("  ⛔ ALL ZONES SET TO EMERGENCY:")
        print("     → Entry BLOCKED on all zones")
        print("     → Exit rates DOUBLED")
        print("     → Evacuation routing engaged\n")

        # Find evacuation routes
        safest = sorted(zones, key=lambda z: z.density)
        print("  🏥 SAFEST EVACUATION ZONES (lowest density):")
        for i, z in enumerate(safest[:3], 1):
            icon = RISK_ICON.get(z.risk_level, "⚪")
            print(f"     {i}. {icon} {z.name} — density {z.density:.2f}/m²"
                  f"  ({z.capacity - z.people_count} free slots)")

        # Rerouting suggestions
        plans = self.optimizer.compute_redistribution()
        if plans:
            print("\n  🔀 EVACUATION REROUTING:")
            self.optimizer.print_flow_summary(plans)
        else:
            print("\n  ℹ  No redistribution paths available.")

        print("\n  ⚠️  Emergency is now ACTIVE. Zones will remain locked until manual reset.")

    # ════════════════════════════════════════
    # [8] SYSTEM DASHBOARD
    # ════════════════════════════════════════
    def _dashboard(self):
        clear_screen()
        print(BANNER)
        zones = self.manager.get_all_zones()
        if not zones:
            print("\n  ✗ No zones registered. Add zones first."); return

        # ── Zone Table ──
        self._print_zone_table()

        # ── Graph Status ──
        edges = self.optimizer.get_all_edges_summary()
        section("GRAPH STATUS")
        if edges:
            print(f"  {'From':<18} {'To':<18} {'Capacity':>8}  {'Status':<8}  Label")
            print("  " + "─" * 70)
            for e in edges:
                st = "OPEN" if e["is_open"] else "CLOSED"
                print(f"  {e['from_name']:<18} {e['to_name']:<18} {e['capacity']:>8.0f}  {st:<8}  {e['label']}")
        else:
            print("  No edges defined.")


        # ── ML Predictions ──
        section("ML PREDICTIONS")
        has_data = False
        for zone in zones:
            preds = self.predictor.predict_range(zone.zone_id)
            if preds and preds[0].get("predicted_count") is not None:
                has_data = True
                break
        if has_data:
            self._run_forecast()
        else:
            print("  ℹ  No prediction data yet. Run simulation ticks or forecasts first.")

        # ── Decision Output ──
        section("DECISION ENGINE OUTPUT")
        plans = self.optimizer.compute_redistribution()
        decisions = self.engine.evaluate(self.tick, plans)
        if decisions:
            self.engine.print_decisions(decisions, self.tick)
        else:
            print("  ✅ All zones nominal.")

        if plans:
            self.optimizer.print_flow_summary(plans)

        if self.emergency_active:
            print("\n  🚨 EMERGENCY MODE IS ACTIVE")

    # ════════════════════════════════════════
    # REACTIVE AUTO-CHECK (Rule 4)
    # ════════════════════════════════════════
    def _reactive_check(self):
        """Auto-triggered after any zone/crowd/graph update."""
        zones = self.manager.get_all_zones()
        if not zones:
            return

        # Feed current state to ML
        for zone in zones:
            self.predictor.feed(zone.zone_id, zone.people_count)

        # Run decision engine
        plans = self.optimizer.compute_redistribution()
        decisions = self.engine.evaluate(self.tick, plans)

        # Check for HIGH / CRITICAL
        urgent = [d for d in decisions
                  if d.urgency in ("P1 CRITICAL", "P2 HIGH")]

        if urgent:
            print(f"\n  {'━' * 60}")
            print(f"  🚨 AUTO-ALERT: {len(urgent)} HIGH/CRITICAL risk(s) detected!")
            print(f"  {'━' * 60}")

            for d in urgent:
                d.display()

            if plans:
                print(f"\n  🔀 AUTO-REROUTING SUGGESTIONS:")
                self.optimizer.print_flow_summary(plans)

            # Find evacuation paths
            safe = self.manager.safe_zones()
            if safe:
                print(f"\n  🏥 EVACUATION TARGETS:")
                for z in safe[:3]:
                    slack = z.capacity - z.people_count
                    print(f"     🟢 {z.name} — {slack} free slots")

            # Print quick dashboard
            self._print_zone_table()

    # ════════════════════════════════════════
    # Helpers
    # ════════════════════════════════════════
    def _list_zone_ids(self):
        zones = self.manager.get_all_zones()
        ids = ", ".join(z.zone_id for z in zones)
        print(f"  Registered zones: [{ids}]")

    def _print_zone_table(self):
        zones = self.manager.get_all_zones()
        if not zones:
            return
        section("ZONE STATUS")
        print(f"  {'Zone':<20} {'People':>7} {'Density':>8} {'Risk':<10}"
              f" {'Entry':>6} {'Exit':>6} {'Occ%':>6}")
        print("  " + "─" * 72)
        for z in sorted(zones, key=lambda x: x.density, reverse=True):
            icon = RISK_ICON.get(z.risk_level, "⚪")
            print(f"  {icon} {z.name:<18} {z.people_count:>7}"
                  f" {z.density:>8.2f} {z.risk_level:<10}"
                  f" {z.entry_rate:>6.1f} {z.exit_rate:>6.1f}"
                  f" {z.occupancy_pct:>5.1f}%")
        total = self.manager.total_people()
        crit = len(self.manager.critical_zones())
        print("  " + "─" * 72)
        print(f"  Total: {total:,} people  |  Critical zones: {crit}"
              f"  |  Tick: #{self.tick}")


# ─────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    clear_screen()
    print(BANNER)
    print()
    terminal = CrowdControlTerminal()
    terminal.run()
