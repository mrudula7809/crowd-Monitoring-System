"""
step5_visualization.py — Visualization Module
Generates all 5 control-room graphs using matplotlib.
"""

from typing import Dict, List, Optional
import os

try:
    import matplotlib
    matplotlib.use("Agg")          # non-interactive backend (safe for servers)
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.colors as mcolors
    import numpy as np
    MATPLOTLIB_OK = True
except ImportError:
    MATPLOTLIB_OK = False
    print("  ⚠️  matplotlib / numpy not installed. Visualization disabled.")
    print("      Run: pip install matplotlib numpy")


RISK_COLORS = {
    "SAFE":     "#2ecc71",
    "MODERATE": "#f1c40f",
    "HIGH":     "#e67e22",
    "CRITICAL": "#e74c3c",
}

OUTPUT_DIR = "crowd_charts"


def _ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def _savefig(fig, filename: str):
    _ensure_output_dir()
    path = os.path.join(OUTPUT_DIR, filename)
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"  📊 Saved → {path}")
    return path


# ─────────────────────────────────────────────
# 1. Crowd Density vs Time
# ─────────────────────────────────────────────
def plot_density_over_time(zone_histories: Dict[str, List[Dict]], title: str = "Crowd Density Over Time"):
    """zone_histories: {zone_id: [{tick, density, zone_name}, ...]}"""
    if not MATPLOTLIB_OK:
        return
    fig, ax = plt.subplots(figsize=(12, 5))
    cmap = plt.get_cmap("tab10")

    for i, (zid, history) in enumerate(zone_histories.items()):
        if not history:
            continue
        ticks   = [h["tick"]    for h in history]
        density = [h["density"] for h in history]
        label   = history[0].get("zone_name", zid) if history else zid
        ax.plot(ticks, density, label=label, color=cmap(i), linewidth=2, marker=".", markersize=3)

    # Risk threshold lines
    ax.axhline(2.0, color=RISK_COLORS["MODERATE"], linestyle="--", linewidth=1, alpha=0.7, label="Moderate threshold")
    ax.axhline(4.0, color=RISK_COLORS["HIGH"],     linestyle="--", linewidth=1, alpha=0.7, label="High threshold")
    ax.axhline(6.0, color=RISK_COLORS["CRITICAL"], linestyle="--", linewidth=1, alpha=0.7, label="Critical threshold")

    ax.set_xlabel("Simulation Tick (1 tick = 1 min)", fontsize=11)
    ax.set_ylabel("Density (people/m²)", fontsize=11)
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.legend(fontsize=8, ncol=2)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return _savefig(fig, "1_density_over_time.png")


# ─────────────────────────────────────────────
# 3. Zone Risk Level Timeline
# ─────────────────────────────────────────────
def plot_risk_timeline(risk_data: Dict[str, List], zone_names: Dict[str, str] = None):
    """
    risk_data: {zone_id: [(tick, risk_level), ...]}
    """
    if not MATPLOTLIB_OK:
        return
    risk_order = {"SAFE": 0, "MODERATE": 1, "HIGH": 2, "CRITICAL": 3}
    zone_ids   = list(risk_data.keys())
    n_zones    = len(zone_ids)

    fig, ax = plt.subplots(figsize=(14, max(4, n_zones * 0.8 + 2)))

    for yi, zid in enumerate(zone_ids):
        timeline = risk_data.get(zid, [])
        if not timeline:
            continue
        for tick, risk in timeline:
            color = RISK_COLORS.get(risk, "#bdc3c7")
            ax.barh(yi, 1, left=tick - 1, height=0.6, color=color, alpha=0.85)

    label = zone_names or {}
    ytick_labels = [label.get(zid, zid) for zid in zone_ids]
    ax.set_yticks(range(n_zones))
    ax.set_yticklabels(ytick_labels, fontsize=9)
    ax.set_xlabel("Simulation Tick")
    ax.set_title("Zone Risk Level Timeline", fontsize=13, fontweight="bold")

    patches = [mpatches.Patch(color=c, label=r) for r, c in RISK_COLORS.items()]
    ax.legend(handles=patches, loc="upper right", fontsize=9)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    return _savefig(fig, "3_risk_timeline.png")


# ─────────────────────────────────────────────
# 4. Heatmap of Zone Risk (grid layout)
# ─────────────────────────────────────────────
def plot_zone_heatmap(zone_densities: Dict[str, float], zone_names: Dict[str, str] = None,
                      grid_cols: int = 3):
    """zone_densities: {zone_id: current_density}"""
    if not MATPLOTLIB_OK:
        return

    ids = list(zone_densities.keys())
    n   = len(ids)
    cols = min(grid_cols, n)
    rows = (n + cols - 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 3.5 * rows))
    axes_flat = np.array(axes).flatten() if n > 1 else [axes]

    cmap  = mcolors.LinearSegmentedColormap.from_list(
        "crowd", ["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c"], N=256
    )
    norm  = mcolors.Normalize(vmin=0, vmax=8)

    for i, zid in enumerate(ids):
        ax      = axes_flat[i]
        density = zone_densities[zid]
        color   = cmap(norm(density))
        ax.set_facecolor(color)
        label   = (zone_names or {}).get(zid, zid)
        ax.text(0.5, 0.6, label,  ha="center", va="center", fontsize=11, fontweight="bold",
                transform=ax.transAxes, color="white" if density > 3 else "#2c3e50")
        ax.text(0.5, 0.35, f"{density:.2f}/m²", ha="center", va="center", fontsize=14,
                transform=ax.transAxes, color="white" if density > 3 else "#2c3e50", fontweight="bold")

        # Risk label
        if density >= 6:   risk = "CRITICAL"
        elif density >= 4: risk = "HIGH"
        elif density >= 2: risk = "MODERATE"
        else:              risk = "SAFE"
        ax.text(0.5, 0.12, risk, ha="center", va="center", fontsize=9,
                transform=ax.transAxes, color="white" if density > 3 else "#7f8c8d")
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_edgecolor("white"); spine.set_linewidth(2)

    # Hide unused axes
    for j in range(n, len(axes_flat)):
        axes_flat[j].set_visible(False)

    # Colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    fig.colorbar(sm, ax=axes_flat, orientation="vertical", fraction=0.02, pad=0.04, label="Density (people/m²)")
    fig.suptitle("Zone Density Heatmap", fontsize=14, fontweight="bold", y=1.01)
    fig.tight_layout()
    return _savefig(fig, "4_zone_heatmap.png")


# ─────────────────────────────────────────────
# 5. Flow Network Graph
# ─────────────────────────────────────────────
def plot_flow_network(
    zone_data:   Dict[str, Dict],    # {zone_id: {name, density, risk, x, y}}
    edges:       List[Dict],         # [{from, to, capacity, is_open}]
    plans:       List = None,        # redistribution plans
):
    """Draws venue topology as a network with color-coded nodes."""
    if not MATPLOTLIB_OK:
        return

    fig, ax = plt.subplots(figsize=(14, 9))
    ax.set_aspect("equal")
    ax.set_facecolor("#1a1a2e")
    fig.patch.set_facecolor("#1a1a2e")

    # Draw edges
    for edge in edges:
        fz = zone_data.get(edge["from"])
        tz = zone_data.get(edge["to"])
        if not fz or not tz:
            continue
        x0, y0 = fz["x"], fz["y"]
        x1, y1 = tz["x"], tz["y"]
        color = "#4CAF50" if edge.get("is_open", True) else "#e74c3c"
        lw    = max(1.0, edge.get("capacity", 50) / 80)
        ax.plot([x0, x1], [y0, y1], "-", color=color, linewidth=lw, alpha=0.6, zorder=1)
        # arrow midpoint
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        ax.annotate("", xy=(x1, y1), xytext=(mx, my),
                    arrowprops=dict(arrowstyle="->", color=color, lw=1.0), zorder=2)

    # Highlight redistribution edges
    if plans:
        for plan in plans:
            fz = zone_data.get(plan.from_zone)
            tz = zone_data.get(plan.to_zone)
            if not fz or not tz:
                continue
            ax.annotate("",
                xy=(tz["x"], tz["y"]), xytext=(fz["x"], fz["y"]),
                arrowprops=dict(arrowstyle="-|>", color="#FFD700", lw=2.5, mutation_scale=20),
                zorder=5)
            mx, my = (fz["x"] + tz["x"]) / 2, (fz["y"] + tz["y"]) / 2
            ax.text(mx, my, f"+{plan.move_count}", color="#FFD700", fontsize=8, ha="center",
                    fontweight="bold", zorder=6)

    # Draw nodes
    for zid, zd in zone_data.items():
        color  = RISK_COLORS.get(zd.get("risk", "SAFE"), "#95a5a6")
        radius = max(0.5, zd.get("density", 1) * 0.18)
        circle = plt.Circle((zd["x"], zd["y"]), radius, color=color, zorder=3, alpha=0.9)
        ax.add_patch(circle)
        ax.text(zd["x"], zd["y"] + radius + 0.15, zd.get("name", zid),
                ha="center", va="bottom", fontsize=8, color="white", fontweight="bold", zorder=4)
        ax.text(zd["x"], zd["y"], f"{zd.get('density', 0):.1f}",
                ha="center", va="center", fontsize=7, color="white", zorder=4)

    # Legend
    patches  = [mpatches.Patch(color=c, label=r) for r, c in RISK_COLORS.items()]
    gold_line = mpatches.Patch(color="#FFD700", label="Redirect flow")
    ax.legend(handles=patches + [gold_line], loc="lower right", fontsize=8,
              facecolor="#2c2c2c", edgecolor="white", labelcolor="white")
    ax.set_title("Flow Network — Crowd Movement Graph", fontsize=13, fontweight="bold", color="white")
    ax.set_xlim(-0.5, 12); ax.set_ylim(-0.5, 10)
    ax.set_xticks([]); ax.set_yticks([])
    fig.tight_layout()
    return _savefig(fig, "5_flow_network.png")


# ─────────────────────────────────────────────
# Convenience: render all charts at once
# ─────────────────────────────────────────────
def render_all(manager, zone_histories, risk_timelines, plans, edges_raw):
    """Call after simulation completes to generate all 5 charts."""
    print("\n  🖼  Generating visualizations ...")

    # 1. Density over time
    plot_density_over_time(zone_histories)

    # 3. Risk timeline
    plot_risk_timeline(risk_timelines, {z.zone_id: z.name for z in manager.zones.values()})

    # 4. Heatmap
    densities = {z.zone_id: z.density for z in manager.zones.values()}
    names     = {z.zone_id: z.name    for z in manager.zones.values()}
    plot_zone_heatmap(densities, names)

    # 5. Flow network (requires layout coords stored in zone_data)
    zone_data = {}
    for zone in manager.zones.values():
        zone_data[zone.zone_id] = {
            "name":    zone.name,
            "density": zone.density,
            "risk":    zone.risk_level,
            "x":       getattr(zone, "_layout_x", 1.0),
            "y":       getattr(zone, "_layout_y", 1.0),
        }
    plot_flow_network(zone_data, edges_raw, plans)

    print(f"  ✅ All charts saved to ./{OUTPUT_DIR}/")
