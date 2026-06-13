"""
dashboard.py — Streamlit Real-Time Crowd Intelligence Control Dashboard
Run:  streamlit run dashboard.py
"""
import streamlit as st
import time, math
from datetime import datetime

from step1_core import Zone, CrowdManager
from step2_ml import CrowdPredictor
from step3_flow import FlowOptimizer
from step4_db import DatabaseManager
from step6_decision_engine import DecisionEngine

st.set_page_config(page_title="Crowd Intelligence Control", page_icon="C", layout="wide", initial_sidebar_state="expanded")

RISK_CLR = {"SAFE":"#22c55e","MODERATE":"#eab308","HIGH":"#f97316","CRITICAL":"#ef4444"}
RISK_DOT = {"SAFE":"#22c55e","MODERATE":"#eab308","HIGH":"#f97316","CRITICAL":"#ef4444"}

# ── CSS ──
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
*{font-family:'Inter',sans-serif;}
.hdr{background:linear-gradient(135deg,#0f172a,#1e293b);padding:1.4rem 2rem;border-radius:10px;margin-bottom:1rem;color:#e2e8f0;text-align:center;}
.hdr h1{margin:0;font-size:1.5rem;letter-spacing:2px;font-weight:700;color:#f8fafc;}
.hdr p{margin:.3rem 0 0;font-size:.82rem;color:#94a3b8;}
.kpi{background:#1e293b;border-radius:8px;padding:1rem;text-align:center;border:1px solid #334155;}
.kpi .val{font-size:1.6rem;font-weight:700;color:#f8fafc;}
.kpi .lbl{font-size:.75rem;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;}
.zcard{border-radius:8px;padding:.9rem 1rem;margin-bottom:.5rem;border-left:4px solid;background:#1e293b;color:#e2e8f0;}
.zcard h4{margin:0 0 .3rem;font-size:.95rem;font-weight:600;}
.zcard .m{font-size:.8rem;color:#94a3b8;margin:.15rem 0;}
.zcard .m b{color:#e2e8f0;}
.alert-bar{background:linear-gradient(90deg,#dc2626,#b91c1c);color:#fff;padding:.8rem 1.2rem;border-radius:8px;margin-bottom:1rem;font-weight:600;text-align:center;animation:pulse 1.5s infinite;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:.65;}}
.htbl{width:100%;border-collapse:collapse;font-size:.82rem;color:#e2e8f0;}
.htbl th{background:#334155;padding:.55rem .7rem;text-align:left;font-weight:600;color:#94a3b8;text-transform:uppercase;font-size:.72rem;letter-spacing:.5px;border-bottom:2px solid #475569;}
.htbl td{padding:.5rem .7rem;border-bottom:1px solid #334155;}
.htbl tr:hover{background:#334155;}
.dcard{padding:.7rem .9rem;border-radius:6px;margin-bottom:.5rem;border-left:3px solid;font-size:.82rem;color:#e2e8f0;}
.dc-crit{border-color:#ef4444;background:#1c1117;}
.dc-high{border-color:#f97316;background:#1c1810;}
.dc-mod{border-color:#eab308;background:#1c1b10;}
.dc-safe{border-color:#22c55e;background:#101c14;}
.sec-title{font-size:1rem;font-weight:600;color:#f8fafc;margin:1.2rem 0 .6rem;padding-bottom:.4rem;border-bottom:1px solid #334155;}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:middle;}
div[data-testid="stMetric"]{background:#1e293b;border-radius:8px;padding:.8rem;border:1px solid #334155;}
div[data-testid="stMetric"] label{color:#94a3b8 !important;}
div[data-testid="stMetric"] [data-testid="stMetricValue"]{color:#f8fafc !important;}
.stApp{background-color:#0f172a;}
section[data-testid="stSidebar"]>div{background:#1e293b;padding-top:1rem;}
section[data-testid="stSidebar"] *{color:#e2e8f0 !important;}
section[data-testid="stSidebar"] input, section[data-testid="stSidebar"] select{background:#334155 !important;border-color:#475569 !important;color:#f8fafc !important;}
</style>""", unsafe_allow_html=True)


def init_state():
    if "manager" not in st.session_state:
        st.session_state.manager = CrowdManager("Control Room")
        st.session_state.predictor = CrowdPredictor(tick_seconds=60)
        st.session_state.optimizer = FlowOptimizer(st.session_state.manager)
        st.session_state.engine = DecisionEngine(
            st.session_state.manager, predictor=st.session_state.predictor, auto_apply=True)
        st.session_state.db = DatabaseManager(use_mysql=True, verbose=False)
        st.session_state.live_mode = False
        st.session_state.emergency = False
        st.session_state.tick = 0
        st.session_state.history = {}

init_state()
mgr = st.session_state.manager
pred = st.session_state.predictor
opt = st.session_state.optimizer
eng = st.session_state.engine


def do_tick():
    st.session_state.tick += 1
    mgr.tick_number = st.session_state.tick
    for z in mgr.get_all_zones():
        z.tick()
        pred.feed(z.zone_id, z.people_count)
        st.session_state.history.setdefault(z.zone_id, []).append(
            {"tick": st.session_state.tick, "people": z.people_count, "density": z.density})


def reactive_check():
    for z in mgr.get_all_zones():
        pred.feed(z.zone_id, z.people_count)
    plans = opt.compute_redistribution()
    return eng.evaluate(st.session_state.tick, plans), plans


def html_table(headers, rows_data):
    h = "".join(f"<th>{c}</th>" for c in headers)
    body = ""
    for r in rows_data:
        body += "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
    return f'<table class="htbl"><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table>'


def risk_dot(level):
    c = RISK_CLR.get(level, "#64748b")
    return f'<span class="dot" style="background:{c};"></span>{level}'


# ── HEADER ──
zones = mgr.get_all_zones()
n_crit = len(mgr.critical_zones())
n_high = len(mgr.high_risk_zones())
emg = " | EMERGENCY ACTIVE" if st.session_state.emergency else ""

st.markdown(f"""<div class="hdr">
<h1>{mgr.venue_name.upper()} CONTROL ROOM</h1>
<p>{datetime.now().strftime('%A %d %b %Y  %H:%M:%S')} &nbsp;|&nbsp; Tick #{st.session_state.tick}
&nbsp;|&nbsp; Zones: {len(zones)} &nbsp;|&nbsp; Critical: {n_crit} &nbsp;|&nbsp; High Risk: {n_high}{emg}</p>
</div>""", unsafe_allow_html=True)

if n_crit > 0 or st.session_state.emergency:
    names = ", ".join(z.name for z in mgr.critical_zones()) or "ALL ZONES"
    st.markdown(f'<div class="alert-bar">CRITICAL ALERT  --  {names}  --  IMMEDIATE ACTION REQUIRED</div>',
                unsafe_allow_html=True)

# ── SIDEBAR ──
with st.sidebar:
    st.markdown('<p class="sec-title">CONTROL PANEL</p>', unsafe_allow_html=True)

    with st.expander("Venue Settings", expanded=True):
        new_venue = st.text_input("Venue Name", value=mgr.venue_name, key="v_name_input")
        if new_venue and new_venue != mgr.venue_name:
            mgr.venue_name = new_venue
            st.rerun()

    with st.expander("Add / Update Zone"):
        zid = st.text_input("Zone ID", "Z1", key="az_id").strip().upper()
        exists = mgr.zone_exists(zid)
        old = mgr.get_zone(zid) if exists else None
        zname = st.text_input("Name", old.name if old else zid, key="az_n")
        zarea = st.number_input("Area m2", 10.0, 1e6, float(old.area_sqm) if old else 500.0, key="az_a")
        zcap = st.number_input("Capacity", 1, 500000, old.capacity if old else 1000, key="az_c")
        zppl = st.number_input("People", 0, 999999, old.people_count if old else 0, key="az_p")
        zer = st.number_input("Entry rate", 0.0, 5000.0, float(old.entry_rate) if old else 30.0, key="az_er")
        zxr = st.number_input("Exit rate", 0.0, 5000.0, float(old.exit_rate) if old else 25.0, key="az_xr")
        if st.button("Save Zone", key="az_btn", use_container_width=True):
            if exists:
                zone_obj = mgr.update_zone(zid, name=zname, area_sqm=zarea, capacity=int(zcap),
                                people_count=int(zppl), entry_rate=zer, exit_rate=zxr)
            else:
                zone_obj = Zone(zone_id=zid, name=zname, area_sqm=zarea, capacity=int(zcap),
                                  initial_count=int(zppl), entry_rate=zer, exit_rate=zxr)
                mgr.add_zone(zone_obj)
                st.session_state.history[zid] = []
            
            # Log to backend database
            if zone_obj:
                st.session_state.db.insert_crowd_log(
                    zone_id=zone_obj.zone_id,
                    zone_name=zone_obj.name,
                    entry_rate=zone_obj.entry_rate,
                    exit_rate=zone_obj.exit_rate,
                    people=zone_obj.people_count,
                    density=zone_obj.density,
                    capacity=zone_obj.capacity
                )
            
            st.rerun()

    with st.expander("Update Crowd"):
        zids = [z.zone_id for z in mgr.get_all_zones()]
        if zids:
            sel = st.selectbox("Zone", zids, key="uc_s")
            zo = mgr.get_zone(sel)
            np_ = st.number_input("People", 0, 999999, zo.people_count, key="uc_p")
            ne_ = st.number_input("Entry rate", 0.0, 5000.0, float(zo.entry_rate), key="uc_e")
            nx_ = st.number_input("Exit rate", 0.0, 5000.0, float(zo.exit_rate), key="uc_x")
            if st.button("Update", key="uc_btn", use_container_width=True):
                zo.people_count = int(np_); zo.entry_rate = ne_; zo.exit_rate = nx_
                st.rerun()
        else:
            st.info("Add zones first")

    with st.expander("Add / Update Edge"):
        if len(zids) >= 2:
            ef = st.selectbox("From", zids, key="ef")
            et = st.selectbox("To", [z for z in zids if z != ef], key="et")
            ec = st.number_input("Capacity", 1.0, 10000.0, 100.0, key="ec")
            el = st.text_input("Label", f"{ef}-{et}", key="el")
            if st.button("Save Edge", key="eb", use_container_width=True):
                if opt.edge_exists(ef, et):
                    opt.update_edge_capacity(ef, et, ec)
                else:
                    try:
                        opt.add_bidirectional(ef, et, ec, el)
                    except ValueError as e:
                        st.error(str(e))
                st.rerun()
        else:
            st.info("Need 2+ zones")

    st.divider()
    st.markdown('<p class="sec-title">SIMULATION</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("1 Tick", use_container_width=True, key="t1"):
            do_tick(); st.rerun()
    with c2:
        if st.button("5 Ticks", use_container_width=True, key="t5"):
            for _ in range(5): do_tick()
            st.rerun()

    live = st.toggle("Live Mode", value=st.session_state.live_mode, key="lv")
    st.session_state.live_mode = live
    st.divider()
    if st.button("EMERGENCY MODE", use_container_width=True, type="primary", key="em"):
        st.session_state.emergency = True
        for z in mgr.get_all_zones(): z.declare_emergency()
        st.rerun()
    if st.session_state.emergency:
        if st.button("Reset Emergency", use_container_width=True, key="emr"):
            st.session_state.emergency = False
            for z in mgr.get_all_zones():
                z.is_emergency = False; z.is_entry_restricted = False
            st.rerun()


# ── MAIN ──
zones = mgr.get_all_zones()
if not zones:
    st.info("Use the sidebar to add zones and get started.")
    st.stop()

# KPIs
k1, k2, k3, k4 = st.columns(4)
k1.metric("Total People", f"{mgr.total_people():,}")
k2.metric("Active Zones", len(zones))
k3.metric("Critical Zones", n_crit)
k4.metric("Tick", f"#{st.session_state.tick}")

# ── ZONE STATUS ──
st.markdown('<p class="sec-title">ZONE STATUS</p>', unsafe_allow_html=True)
cols_per = min(4, len(zones))
sorted_z = sorted(zones, key=lambda x: x.density, reverse=True)
for i in range(0, len(sorted_z), cols_per):
    cols = st.columns(cols_per)
    for j, col in enumerate(cols):
        idx = i + j
        if idx >= len(sorted_z): break
        z = sorted_z[idx]
        clr = RISK_CLR.get(z.risk_level, "#64748b")
        with col:
            st.markdown(f"""<div class="zcard" style="border-left-color:{clr};">
<h4><span class="dot" style="background:{clr};"></span>{z.name} <span style="color:#64748b;font-size:.7rem">({z.zone_id})</span></h4>
<div class="m">People: <b>{z.people_count:,}</b></div>
<div class="m">Density: <b>{z.density:.2f}</b> /m2</div>
<div class="m">Risk: <b style="color:{clr}">{z.risk_level}</b></div>
<div class="m">Entry: {z.entry_rate:.1f} | Exit: {z.exit_rate:.1f}</div>
<div class="m">Occupancy: {z.occupancy_pct:.1f}%</div>
</div>""", unsafe_allow_html=True)

# ── FORECAST + DECISIONS ──
lc, rc = st.columns([3, 2])

with lc:
    st.markdown('<p class="sec-title">ML FORECASTS</p>', unsafe_allow_html=True)
    hdr = ["Zone", "Now", "+5 min", "+10 min", "+15 min", "Trend"]
    trows = []
    for z in zones:
        preds = pred.predict_range(z.zone_id)
        def fmt(p): return str(p.get("predicted_count", "--")) if p.get("predicted_count") is not None else "--"
        p5 = fmt(preds[0]) if preds else "--"
        p10 = fmt(preds[1]) if len(preds) > 1 else "--"
        p15 = fmt(preds[2]) if len(preds) > 2 else "--"
        trend = pred.es.trend_direction(z.zone_id)
        trows.append([f'{risk_dot(z.risk_level)} {z.name}', str(z.people_count), p5, p10, p15, trend])
    st.markdown(html_table(hdr, trows), unsafe_allow_html=True)

with rc:
    st.markdown('<p class="sec-title">DECISION ENGINE</p>', unsafe_allow_html=True)
    decisions, plans = reactive_check()
    urgent = [d for d in decisions if d.urgency in ("P1 CRITICAL", "P2 HIGH")]
    if urgent:
        for d in urgent[:5]:
            css = "dcard dc-crit" if "CRITICAL" in d.urgency else "dcard dc-high"
            tgts = ", ".join(d.target_zones) if d.target_zones else "--"
            st.markdown(f"""<div class="{css}">
<b>[{d.urgency}]</b> {d.zone_name}<br/>
<span style="font-size:.78rem">{d.action}</span><br/>
<span style="font-size:.75rem;color:#94a3b8">Redirect: {tgts}</span>
</div>""", unsafe_allow_html=True)
    elif decisions:
        for d in decisions[:4]:
            css = "dcard dc-mod" if "MODERATE" in d.urgency else "dcard dc-safe"
            st.markdown(f"""<div class="{css}">
<b>[{d.urgency}]</b> {d.zone_name}<br/>
<span style="font-size:.78rem">{d.action}</span>
</div>""", unsafe_allow_html=True)
    else:
        st.markdown('<div class="dcard dc-safe">All zones nominal. No action required.</div>',
                    unsafe_allow_html=True)

    if plans:
        st.markdown('<p style="font-size:.85rem;font-weight:600;color:#e2e8f0;margin-top:.8rem;">REROUTING:</p>',
                    unsafe_allow_html=True)
        for p in plans[:4]:
            src = mgr.get_zone(p.from_zone)
            tgt = mgr.get_zone(p.to_zone)
            st.caption(f"Move {p.move_count} : {src.name if src else p.from_zone} -> "
                       f"{tgt.name if tgt else p.to_zone} via {p.via_edge}")

# ── GRAPH ──
st.markdown('<p class="sec-title">NETWORK GRAPH & CONGESTION</p>', unsafe_allow_html=True)
gl, gr = st.columns([3, 2])

with gl:
    edges = opt.get_all_edges_summary()
    if edges and len(zones) >= 2:
        try:
            import plotly.graph_objects as go
            n = len(zones)
            pos = {}
            for i, z in enumerate(zones):
                a = 2 * math.pi * i / max(n, 1)
                pos[z.zone_id] = (3 + 2.5 * math.cos(a), 3 + 2.5 * math.sin(a))
            ex, ey = [], []
            for e in edges:
                x0, y0 = pos.get(e["from_id"], (0, 0))
                x1, y1 = pos.get(e["to_id"], (0, 0))
                ex += [x0, x1, None]; ey += [y0, y1, None]
            et = go.Scatter(x=ex, y=ey, mode="lines", line=dict(width=1.5, color="#475569"), hoverinfo="none")
            nx_ = [pos[z.zone_id][0] for z in zones]
            ny_ = [pos[z.zone_id][1] for z in zones]
            nc = [RISK_CLR.get(z.risk_level, "#64748b") for z in zones]
            ns = [max(22, min(50, z.people_count / max(z.capacity, 1) * 40)) for z in zones]
            nt = [f"{z.name}<br>People: {z.people_count}<br>Density: {z.density:.2f}<br>Risk: {z.risk_level}" for z in zones]
            nl = [z.name for z in zones]
            nd = go.Scatter(x=nx_, y=ny_, mode="markers+text", text=nl, textposition="top center",
                            textfont=dict(size=10, color="#e2e8f0"),
                            marker=dict(size=ns, color=nc, line=dict(width=2, color="#1e293b")),
                            hovertext=nt, hoverinfo="text")
            fig = go.Figure(data=[et, nd])
            fig.update_layout(showlegend=False, hovermode="closest",
                              plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
                              margin=dict(l=10, r=10, t=10, b=10), height=320,
                              xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                              yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.markdown(html_table(["From","To","Capacity","Status"],
                [[e["from_name"],e["to_name"],f'{e["capacity"]:.0f}',"OPEN" if e["is_open"] else "CLOSED"] for e in edges]),
                unsafe_allow_html=True)
    elif edges:
        st.markdown(html_table(["From","To","Capacity","Status"],
            [[e["from_name"],e["to_name"],f'{e["capacity"]:.0f}',"OPEN" if e["is_open"] else "CLOSED"] for e in edges]),
            unsafe_allow_html=True)
    else:
        st.info("No edges defined yet.")

with gr:
    bn = opt.get_bottlenecks()
    if bn:
        st.markdown('<p style="font-size:.85rem;font-weight:600;color:#ef4444;">BOTTLENECKS:</p>',
                    unsafe_allow_html=True)
        for b in bn:
            st.markdown(f'<div class="dcard dc-crit">{b["from_name"]} -> {b["to_name"]} | overflow +{b["overflow"]:.0f}</div>',
                        unsafe_allow_html=True)
    else:
        st.markdown('<div class="dcard dc-safe">No bottlenecks detected</div>', unsafe_allow_html=True)

    if edges:
        st.markdown('<p style="font-size:.85rem;font-weight:600;color:#e2e8f0;margin-top:.6rem;">EDGES:</p>',
                    unsafe_allow_html=True)
        for e in edges:
            s = "OPEN" if e["is_open"] else "CLOSED"
            st.caption(f'{e["from_name"]} <-> {e["to_name"]} | cap: {e["capacity"]:.0f} | {s}')

    safe = mgr.safe_zones()
    if safe and n_high > 0:
        st.markdown('<p style="font-size:.85rem;font-weight:600;color:#22c55e;margin-top:.6rem;">EVACUATION TARGETS:</p>',
                    unsafe_allow_html=True)
        for z in safe[:3]:
            st.caption(f'[SAFE] {z.name} -- {z.capacity - z.people_count:,} free slots')

CHART_LAYOUT = dict(
    plot_bgcolor="#0f172a", paper_bgcolor="#0f172a",
    font=dict(color="#e2e8f0", size=11),
    margin=dict(l=50, r=20, t=30, b=50),
    xaxis=dict(gridcolor="#1e293b", linecolor="#334155"),
    yaxis=dict(gridcolor="#1e293b", linecolor="#334155"),
    legend=dict(orientation="h", y=-0.28, font=dict(size=10)),
)

def interp(text):
    st.markdown(
        f'<div style="background:#1e293b;border-left:3px solid #3b82f6;padding:.6rem 1rem;'
        f'border-radius:0 6px 6px 0;font-size:.8rem;color:#94a3b8;margin-top:.3rem;">'
        f'<b style="color:#60a5fa">Interpretation: </b>{text}</div>',
        unsafe_allow_html=True
    )

import plotly.graph_objects as go

has_history = any(st.session_state.history.values())

# ══════════════════════════════════════════════════════════
# CHART ROW 1 — Density Over Time  |  People Count Snapshot
# ══════════════════════════════════════════════════════════
st.markdown('<p class="sec-title">ANALYTICAL CHARTS</p>', unsafe_allow_html=True)
c1, c2 = st.columns(2)

with c1:
    st.markdown('<p style="font-size:.88rem;font-weight:600;color:#e2e8f0;">Chart 1 — Crowd Density Over Time</p>', unsafe_allow_html=True)
    if has_history:
        fig = go.Figure()
        for z in zones:
            h = st.session_state.history.get(z.zone_id, [])
            if h:
                fig.add_trace(go.Scatter(
                    x=[d["tick"] for d in h], y=[d["density"] for d in h],
                    mode="lines+markers", name=z.name,
                    line=dict(width=2), marker=dict(size=3)
                ))
        for y, lbl, col in [(2.0,"Moderate",RISK_CLR["MODERATE"]),(4.0,"High",RISK_CLR["HIGH"]),(6.0,"Critical",RISK_CLR["CRITICAL"])]:
            fig.add_hline(y=y, line_dash="dash", line_color=col, opacity=.5, annotation_text=lbl, annotation_font_size=10)
        fig.update_layout(**CHART_LAYOUT, height=270, xaxis_title="Tick", yaxis_title="Density (ppl/m2)")
        st.plotly_chart(fig, use_container_width=True)
        interp("Each line represents one zone's crowd density trajectory. Lines crossing the orange (HIGH) or red (CRITICAL) thresholds indicate stampede risk windows. Converging lines suggest crowd redistribution is working; diverging lines indicate a zone absorbing pressure from others.")
    else:
        st.info("Run simulation ticks to populate this chart.")

with c2:
    st.markdown('<p style="font-size:.88rem;font-weight:600;color:#e2e8f0;">Chart 2 — Current People Count per Zone</p>', unsafe_allow_html=True)
    znames = [z.name for z in zones]
    zppl   = [z.people_count for z in zones]
    zcap   = [z.capacity for z in zones]
    zclrs  = [RISK_CLR.get(z.risk_level, "#64748b") for z in zones]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Current People", x=znames, y=zppl, marker_color=zclrs, text=zppl, textposition="outside"))
    fig.add_trace(go.Scatter(name="Capacity Limit", x=znames, y=zcap, mode="markers+lines",
        marker=dict(symbol="line-ew", size=12, color="#f8fafc", line=dict(color="#f8fafc", width=2)),
        line=dict(dash="dot", color="#f8fafc", width=1)))
    fig.update_layout(**CHART_LAYOUT, height=270, barmode="group",
        xaxis_title="Zone", yaxis_title="People")
    st.plotly_chart(fig, use_container_width=True)
    interp("Bars show the live headcount per zone, coloured by risk level. The dotted white line marks each zone's declared safe capacity. Bars touching or exceeding the line signal an overloaded zone requiring immediate intervention.")

# ══════════════════════════════════════════════════════════
# CHART ROW 2 — Occupancy %  |  Entry vs Exit Flow
# ══════════════════════════════════════════════════════════
c3, c4 = st.columns(2)

with c3:
    st.markdown('<p style="font-size:.88rem;font-weight:600;color:#e2e8f0;">Chart 3 — Zone Occupancy %</p>', unsafe_allow_html=True)
    occ    = [z.occupancy_pct for z in zones]
    fig = go.Figure(go.Bar(
        x=znames, y=occ,
        marker_color=[RISK_CLR.get(z.risk_level,"#64748b") for z in zones],
        text=[f"{v:.1f}%" for v in occ], textposition="outside"
    ))
    fig.add_hline(y=75, line_dash="dash", line_color=RISK_CLR["MODERATE"], opacity=.6, annotation_text="75% warn")
    fig.add_hline(y=100, line_dash="dash", line_color=RISK_CLR["CRITICAL"], opacity=.6, annotation_text="100% cap")
    fig.update_layout(**CHART_LAYOUT, height=270, xaxis_title="Zone", yaxis_title="Occupancy (%)")
    fig.update_yaxes(range=[0, max(max(occ, default=0)*1.2, 120)])
    st.plotly_chart(fig, use_container_width=True)
    interp("Occupancy % is the ratio of current people to declared safe capacity. Values above 75% (yellow line) warrant pre-emptive action. Values above 100% (red line) mean the zone is operating beyond its rated capacity — the system's physical hard cap is 200% to prevent state corruption.")

with c4:
    st.markdown('<p style="font-size:.88rem;font-weight:600;color:#e2e8f0;">Chart 4 — Entry vs Exit Rate per Zone</p>', unsafe_allow_html=True)
    entry_rates = [z.entry_rate for z in zones]
    exit_rates  = [z.exit_rate  for z in zones]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Entry Rate", x=znames, y=entry_rates, marker_color="#3b82f6"))
    fig.add_trace(go.Bar(name="Exit Rate",  x=znames, y=exit_rates,  marker_color="#22c55e"))
    fig.update_layout(**CHART_LAYOUT, height=270, barmode="group",
        xaxis_title="Zone", yaxis_title="People per Tick")
    st.plotly_chart(fig, use_container_width=True)
    interp("Compares the entry rate (people arriving per tick) against the exit rate for each zone. When the blue bar (entry) is significantly taller than the green bar (exit), the zone is accumulating crowd faster than it can drain — a precursor to density escalation. Equal bars indicate a stable zone.")
