"""
Page 00 – Methodology: Interactive schematic of the platform's data flow,
calculation pipeline, and step-by-step methodology.
Appears first in the sidebar navigation.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import pandas as pd

st.set_page_config(page_title="How It Works", page_icon="📐", layout="wide")

# ── BSR colour palette ────────────────────────────────────────────────────────
BSR = {
    "orange":  "#F4721A",
    "navy":    "#1A3A5C",
    "teal":    "#2A9D8F",
    "amber":   "#E9C46A",
    "red":     "#C94040",
    "purple":  "#7B2D8B",
    "green":   "#27ae60",
    "light":   "#F8F4F0",
    "mid":     "#EDEDED",
}

with st.sidebar:
    st.markdown(
        f"<div style='padding:8px 0;'>"
        f"<span style='font-size:20px;font-weight:800;color:{BSR['orange']};'>BSR</span>"
        f"<span style='font-size:12px;color:#666;margin-left:6px;'>Climate Risk Intelligence</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown("**Jump to section**")
    st.markdown(
        "- [Overview](#overview)\n"
        "- [Data Flow Diagram](#data-flow)\n"
        "- [Step-by-Step](#step-by-step)\n"
        "- [Data Sources](#data-sources)",
        unsafe_allow_html=True,
    )

# ════════════════════════════════════════════════════════════════════════════
# HERO
# ════════════════════════════════════════════════════════════════════════════
st.markdown(
    f"""
    <div style="background:linear-gradient(135deg,{BSR['navy']} 0%,#0d2440 100%);
                border-radius:12px;padding:36px 40px 28px 40px;margin-bottom:24px;">
      <div style="font-size:13px;font-weight:700;color:{BSR['orange']};
                  letter-spacing:3px;text-transform:uppercase;margin-bottom:8px;">
        BSR Climate Risk Intelligence Platform
      </div>
      <h1 style="color:white;font-size:32px;font-weight:800;margin:0 0 12px 0;">
        How the Platform Works
      </h1>
      <p style="color:#b0c4d8;font-size:15px;max-width:720px;line-height:1.6;margin:0 0 20px 0;">
        From an asset address to an insurance-grade financial damage estimate in six steps.
        Every number is traceable to a published scientific source.
      </p>
      <div style="display:flex;gap:24px;flex-wrap:wrap;">
        <div style="background:rgba(255,255,255,0.08);border-radius:8px;
                    padding:12px 20px;text-align:center;min-width:100px;">
          <div style="font-size:24px;font-weight:800;color:{BSR['orange']};">5</div>
          <div style="font-size:11px;color:#8fb3d5;">Hazards</div>
        </div>
        <div style="background:rgba(255,255,255,0.08);border-radius:8px;
                    padding:12px 20px;text-align:center;min-width:100px;">
          <div style="font-size:24px;font-weight:800;color:{BSR['teal']};">21</div>
          <div style="font-size:11px;color:#8fb3d5;">Asset Types</div>
        </div>
        <div style="background:rgba(255,255,255,0.08);border-radius:8px;
                    padding:12px 20px;text-align:center;min-width:100px;">
          <div style="font-size:24px;font-weight:800;color:{BSR['amber']};">14</div>
          <div style="font-size:11px;color:#8fb3d5;">Scenarios</div>
        </div>
        <div style="background:rgba(255,255,255,0.08);border-radius:8px;
                    padding:12px 20px;text-align:center;min-width:100px;">
          <div style="font-size:24px;font-weight:800;color:{BSR['green']};">1,000</div>
          <div style="font-size:11px;color:#8fb3d5;">MC draws / asset</div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ════════════════════════════════════════════════════════════════════════════
# STEP CARDS — visual pipeline overview
# ════════════════════════════════════════════════════════════════════════════
st.markdown(f"<h2 id='overview' style='color:{BSR['navy']};margin-top:8px;'>Pipeline Overview</h2>", unsafe_allow_html=True)

STEPS = [
    {
        "num": "1",
        "icon": "🏗️",
        "title": "Portfolio",
        "subtitle": "Asset definition",
        "desc": "Enter asset type, location, value, and structural attributes. Country and elevation auto-detected from coordinates.",
        "color": BSR["navy"],
    },
    {
        "num": "2",
        "icon": "🌡️",
        "title": "Scenarios",
        "subtitle": "Climate pathways",
        "desc": "Choose from BSR 2025, NGFS Phase V, IEA WEO, or IPCC AR6 — 14 scenarios, 1.5°C to 4.3°C by 2080.",
        "color": BSR["teal"],
    },
    {
        "num": "3",
        "icon": "🌊",
        "title": "Hazard Data",
        "subtitle": "ISIMIP3b + Aqueduct",
        "desc": "Granular point-level GCM data per asset. GEV-fitted return periods for flood, wind, heat, and wildfire.",
        "color": BSR["orange"],
    },
    {
        "num": "4",
        "icon": "📉",
        "title": "Vulnerability",
        "subtitle": "HAZUS / JRC curves",
        "desc": "Intensity → damage fraction via peer-reviewed depth-damage and fragility functions, one per asset type × hazard.",
        "color": "#8e44ad",
    },
    {
        "num": "5",
        "icon": "📊",
        "title": "EAD + Scores",
        "subtitle": "Financial quantification",
        "desc": "Trapezoidal integration of Loss EP curve gives EAD. Climate Exposure Scores, EALR, stranded-asset flags.",
        "color": BSR["red"],
    },
    {
        "num": "6",
        "icon": "🛡️",
        "title": "Adaptation & DCF",
        "subtitle": "Decision outputs",
        "desc": "NPV cost-benefit for 19+ adaptation measures. Climate-adjusted DCF valuation with scenario-weighted NPV impairment.",
        "color": BSR["green"],
    },
]

cols = st.columns(len(STEPS))
for col, step in zip(cols, STEPS):
    with col:
        st.markdown(
            f"""
            <div style="background:{step['color']}14;border:1.5px solid {step['color']}44;
                        border-radius:10px;padding:16px;min-height:200px;position:relative;overflow:hidden;">
              <div style="position:absolute;top:-14px;left:14px;
                          background:{step['color']};color:white;
                          font-size:13px;font-weight:800;border-radius:20px;
                          padding:2px 10px;line-height:1.6;">
                Step {step['num']}
              </div>
              <div style="font-size:28px;margin:8px 0 4px 0;">{step['icon']}</div>
              <div style="font-size:15px;font-weight:700;color:{step['color']};margin-bottom:2px;">
                {step['title']}
              </div>
              <div style="font-size:11px;color:#888;font-weight:600;
                          text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">
                {step['subtitle']}
              </div>
              <div style="font-size:12px;color:#444;line-height:1.5;">
                {step['desc']}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ════════════════════════════════════════════════════════════════════════════
# INTERACTIVE FLOW DIAGRAM
# ════════════════════════════════════════════════════════════════════════════
st.markdown(f"<h2 id='data-flow' style='color:{BSR['navy']};margin-top:32px;'>Data Flow Diagram</h2>", unsafe_allow_html=True)
st.caption("Hover over any node for details on data sources and processing logic.")

_NODE_DATA = [
    # Inputs
    dict(id=0,  x=0.0, y=3.2, label="Asset Portfolio",       cat="Input",
         desc="Replacement value · lat/lon · asset type · construction material · year built · elevation · floor area"),
    dict(id=1,  x=0.0, y=1.6, label="Climate Scenarios",     cat="Input",
         desc="BSR 2025 / NGFS Phase V / IEA WEO 2023 / IPCC AR6 · 14 scenarios · 1.5–4.3°C by 2080"),
    dict(id=2,  x=0.0, y=0.0, label="Financial Parameters",  cat="Input",
         desc="Discount rate · WACC · analysis horizon 2025–2050"),

    # Hazard
    dict(id=3,  x=1.1, y=4.2, label="ISIMIP3b API",          cat="Hazard",
         desc="GSWP3-W5E5 bias-adjusted climate data. Variables: tasmax, sfcwind, pr, hurs. 5-GCM ensemble · GEV fitting."),
    dict(id=4,  x=1.1, y=2.8, label="WRI Aqueduct 4.0",      cat="Hazard",
         desc="Water stress projections 2030–2080 under SSP1/2/3/5. Basin-level baseline water stress and variability."),
    dict(id=5,  x=1.1, y=1.4, label="Hazard Multipliers",    cat="Hazard",
         desc="IPCC AR6 scaling: flood +5–8%/°C (Tabari 2020) · wind +5%/2°C (Knutson 2020) · wildfire FWI season (Jolly 2015)"),
    dict(id=6,  x=1.1, y=0.0, label="Regional Fallback",     cat="Hazard",
         desc="Built-in regional median intensities by scenario and return period. Used when ISIMIP API unavailable."),

    # Vulnerability
    dict(id=7,  x=2.2, y=4.2, label="HAZUS 6.0 Flood DDFs",  cat="Vulnerability",
         desc="FEMA HAZUS 6.0 depth-damage functions · 25 occupancy types · 4 materials. PchipInterpolator (monotonic cubic spline)."),
    dict(id=8,  x=2.2, y=3.1, label="JRC Global DDFs",       cat="Vulnerability",
         desc="JRC European depth-damage functions (Huizinga et al. 2017). Applied for European regions (GBR, FRA, DEU …)."),
    dict(id=9,  x=2.2, y=2.0, label="Wind Fragility",        cat="Vulnerability",
         desc="HAZUS MH wind fragility curves. Weibull CDF parameterised by mean damage ratio per construction class."),
    dict(id=10, x=2.2, y=0.9, label="Wildfire FWI Pipeline", cat="Vulnerability",
         desc="Canadian FWI (Van Wagner 1987): FFMC→DMC→DC→ISI→BUI→FWI. Annual maxima → GEV → return period losses."),
    dict(id=11, x=2.2, y=-0.2,label="Heat & Water Stress",   cat="Vulnerability",
         desc="Heat: IEA degree-day cooling cost + ILO productivity loss. Water stress: WRI Aqueduct sector sensitivity weights."),

    # EAD
    dict(id=12, x=3.3, y=2.5, label="Return Period Grid",    cat="EAD",
         desc="Standard RPs: 2, 5, 10, 25, 50, 100, 250, 500, 1000 yrs. GEV MLE fitting to ISIMIP annual maxima."),
    dict(id=13, x=3.3, y=1.2, label="EAD Integration",       cat="EAD",
         desc="Trapezoidal integration under the Loss EP curve. Discounted to PV at chosen rate. Annual 2025–2050 timeline."),
    dict(id=14, x=3.3, y=0.0, label="Monte Carlo (1,000×)",  cat="EAD",
         desc="1,000 draws from vulnerability curve uncertainty distributions → 5th/95th CI on EAD per asset."),

    # Outputs
    dict(id=15, x=4.4, y=4.0, label="Annual EAD 2025–50",    cat="Output",
         desc="Per-asset · per-hazard · per-scenario. Discounted to present value. Scenario comparison charts."),
    dict(id=16, x=4.4, y=2.8, label="Exposure Scores",       cat="Output",
         desc="Climate Exposure Score 1–10 per asset × hazard. EALR (%). Stranded-asset flags."),
    dict(id=17, x=4.4, y=1.6, label="Adaptation ROI",        cat="Output",
         desc="NPV of avoided EAD for 19+ measures. Cost-benefit ratio, payback period, investment frontier."),
    dict(id=18, x=4.4, y=0.4, label="DCF Impairment",        cat="Output",
         desc="Climate-adjusted NPV = base DCF − PV damages. Scenario-weighted impairment %. TCFD-ready."),
]

_EDGES = [
    (0,12),(0,7),(0,9),(0,10),(0,11),
    (1,5),(1,4),(2,13),(2,17),(2,18),
    (3,12),(4,11),(5,12),(6,12),
    (7,13),(8,13),(9,13),(10,13),(11,13),
    (12,13),(13,15),(13,16),(14,15),(15,17),(15,18),(15,16),
]

_CAT_COLORS = {
    "Input":         BSR["navy"],
    "Hazard":        BSR["teal"],
    "Vulnerability": BSR["orange"],
    "EAD":           "#d4a017",
    "Output":        BSR["green"],
}

_id_map = {n["id"]: n for n in _NODE_DATA}

fig_flow = go.Figure()

for src_id, dst_id in _EDGES:
    s, d = _id_map[src_id], _id_map[dst_id]
    fig_flow.add_trace(go.Scatter(
        x=[s["x"], d["x"]], y=[s["y"], d["y"]],
        mode="lines",
        line=dict(color="rgba(170,170,170,0.4)", width=1.3),
        hoverinfo="skip", showlegend=False,
    ))

for cat, color in _CAT_COLORS.items():
    nodes = [n for n in _NODE_DATA if n["cat"] == cat]
    if not nodes:
        continue
    fig_flow.add_trace(go.Scatter(
        x=[n["x"] for n in nodes],
        y=[n["y"] for n in nodes],
        mode="markers+text",
        name=cat,
        text=[n["label"] for n in nodes],
        textposition="middle right",
        textfont=dict(size=13, color="#1a1a1a", family="Arial, sans-serif"),
        marker=dict(color=color, size=32, symbol="circle",
                    line=dict(color="white", width=2.5)),
        customdata=[n["desc"] for n in nodes],
        hovertemplate="<b>%{text}</b><br><br>%{customdata}<extra></extra>",
    ))

for cx, label in [(0.0,"INPUTS"),(1.1,"HAZARD DATA"),(2.2,"VULNERABILITY"),(3.3,"EAD CALC"),(4.4,"OUTPUTS")]:
    fig_flow.add_annotation(
        x=cx, y=5.0, text=f"<b>{label}</b>", showarrow=False,
        font=dict(size=13, color="#444", family="Arial, sans-serif"), xanchor="center",
    )

fig_flow.update_layout(
    height=580, margin=dict(l=20, r=20, t=20, b=20),
    xaxis=dict(range=[-0.35, 5.4], showticklabels=False, showgrid=False, zeroline=False),
    yaxis=dict(range=[-1.0, 5.6],  showticklabels=False, showgrid=False, zeroline=False),
    plot_bgcolor="#fafafa", paper_bgcolor="white",
    legend=dict(orientation="h", yanchor="top", y=-0.02, xanchor="center", x=0.5,
                title_text="Category:", font=dict(size=12)),
    hovermode="closest",
)

st.plotly_chart(fig_flow, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# STEP-BY-STEP METHODOLOGY
# ════════════════════════════════════════════════════════════════════════════
st.markdown(f"<h2 id='step-by-step' style='color:{BSR['navy']};margin-top:4px;'>Step-by-Step Methodology</h2>", unsafe_allow_html=True)
st.caption("Click any step for equations, calibration details, and source citations.")


def _step_header(num: str, icon: str, title: str, color: str) -> str:
    return f"{icon}  Step {num} — {title}"


# Step 1
with st.expander(_step_header("1", "🏗️", "Asset Definition", BSR["navy"]), expanded=False):
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(f"""
**Why each parameter matters:**

| Parameter | How it drives damage |
|---|---|
| **Asset type** | Selects vulnerability curve family (HAZUS occupancy class) |
| **Construction material** | Adjusts damage fraction within the curve |
| **Year built** | Post-1994 = modern construction standards (HAZUS) |
| **Elevation (m ASL)** | Directly subtracted from flood depth; 1 m can halve EAD |
| **Roof type** | Flat = higher wind uplift; gable/hip sheds wind |
| **Floor area (m²)** | Scales heat cooling cost and productivity loss |
| **Region (ISO3)** | Selects regional DDF: JRC for Europe, HAZUS elsewhere |

**Auto-detection:** Clicking **📍 Auto-detect** on the Portfolio page:
- **Country** — reverse geocodes via BigDataCloud (OpenStreetMap data, no API key)
- **Elevation** — queries OpenTopoData ASTER 30m DEM (±10 m accuracy, free, no key)

**Material auto-fill:** Selecting an asset type immediately sets the default construction material
from the peer-reviewed HAZUS occupancy class definition — editable if your specific asset differs.
        """)
    with c2:
        st.markdown("**21 asset types, with HAZUS class mapping:**")
        try:
            import json, os
            with open(os.path.join(os.path.dirname(__file__), "..", "data", "asset_types.json")) as f:
                _at = json.load(f)
            _at_df = pd.DataFrame([
                {"Type": v["label"], "Material": v["default_material"], "HAZUS": v.get("hazus_class","—")}
                for v in _at.values()
            ])
            st.dataframe(_at_df, use_container_width=True, hide_index=True, height=400)
        except Exception:
            st.caption("Asset types defined in data/asset_types.json")

# Step 2
with st.expander(_step_header("2", "🌡️", "Climate Scenario Selection", BSR["teal"]), expanded=False):
    col_a, col_b = st.columns([3, 2])
    with col_a:
        st.markdown("""
**Four scenario frameworks, 14 scenarios total:**

| Framework | Scenarios | Quantitative basis |
|---|---|---|
| BSR 2025 | 4 (incl. Fragmented World) | NGFS Phase V / IPCC AR6 |
| NGFS Phase V | 6 | GCAM 6.0 + REMIND-MAgPIE 3.2 |
| IEA WEO 2023 | 3 | IEA Energy System Model |
| IPCC AR6 | 5 SSPs | CMIP6 multi-model ensemble |

**Hazard scaling from IPCC AR6 WG1:**

| Hazard | Source | Scaling |
|---|---|---|
| Flood | Tabari (2020) | +5–8% extreme precip per °C |
| Wind | Knutson et al. (2020) | +5% max intensity per 2°C |
| Wildfire | Jolly et al. (2015) | FWI season lengthening |
| Heat | Zhao et al. (2021) | Super-linear above 2°C |
| Water Stress | WRI Aqueduct (2023) | ~4%/°C freshwater reduction |

Hazard data extracted from ISIMIP3b 2021–2050 projections (bias-adjusted against 1995–2014 W5E5 reanalysis). IPCC AR6 scaling applied to all sources for temporal evolution.
        """)
    with col_b:
        _sc_df = pd.DataFrame([
            {"Scenario": "BSR Net Zero 2050",      "SSP": "SSP1-1.9", "2050": 1.5, "2080": 1.5},
            {"Scenario": "BSR Delayed Transition",  "SSP": "SSP2-4.5", "2050": 2.0, "2080": 2.4},
            {"Scenario": "BSR Fragmented World",    "SSP": "SSP3-7.0", "2050": 2.5, "2080": 3.5},
            {"Scenario": "BSR Current Policies",    "SSP": "SSP5-8.5", "2050": 3.0, "2080": 4.3},
            {"Scenario": "IPCC SSP2-4.5",           "SSP": "SSP2-4.5", "2050": 2.0, "2080": 2.7},
            {"Scenario": "IPCC SSP5-8.5",           "SSP": "SSP5-8.5", "2050": 3.3, "2080": 4.4},
        ])
        fig_w = px.bar(
            _sc_df.melt(id_vars=["Scenario","SSP"], value_vars=["2050","2080"],
                        var_name="Horizon", value_name="Warming (°C)"),
            x="Scenario", y="Warming (°C)", color="Horizon", barmode="group",
            color_discrete_map={"2050": BSR["orange"], "2080": BSR["red"]},
        )
        fig_w.add_hline(y=1.5, line_dash="dot", line_color=BSR["green"], annotation_text="Paris 1.5°C")
        fig_w.add_hline(y=2.0, line_dash="dot", line_color=BSR["amber"], annotation_text="Paris 2.0°C")
        fig_w.update_layout(
            height=300, margin=dict(l=0, r=0, t=10, b=120),
            xaxis_tickangle=-40, showlegend=True,
            legend=dict(orientation="h", y=1.1),
            plot_bgcolor="white", paper_bgcolor="white",
        )
        st.plotly_chart(fig_w, use_container_width=True)

# Step 3
with st.expander(_step_header("3", "🌊", "Hazard Data Retrieval", BSR["orange"]), expanded=False):
    st.markdown("""
**Priority hierarchy for hazard intensity data:**
```
1. ISIMIP3b API (granular point-level, preferred)
   └── isimip-client v2 → select_point() → ZIP of NetCDF4
   └── h5netcdf engine for in-memory reading
   └── GEV fitting to annual maxima → return period intensities

2. WRI Aqueduct 4.0 (water stress only)
   └── Pre-aggregated basin-level projections to 2080

3. Regional fallback (built-in table)
   └── Median intensities by region × scenario × RP
   └── Used when ISIMIP API unavailable or data < 10 years
```

**ISIMIP3b variables and derivations:**

| Hazard | Variable | Derivation |
|---|---|---|
| Heat | `tasmax` | Annual max daily temperature → GEV → return period °C |
| Wind | `sfcwind` | Annual max wind speed → GEV → return period m/s |
| Flood | `pr` (precipitation) | Rx1day annual maxima → JRC scaling: `depth = max(0, (Rx1day − 25mm) × 0.012 m/mm)` |
| Wildfire | `tasmax`, `pr`, `hurs`, `sfcwind` | Full Canadian FWI pipeline (Van Wagner 1987) |

**GCMs used:** GFDL-ESM4, IPSL-CM6A-LR, MPI-ESM1-2-HR, MRI-ESM2-0, UKESM1-0-LL
(5-model ensemble, bias-adjusted to W5E5 observational baseline)

**GEV fitting:**
```python
c, loc, scale = scipy.stats.genextreme.fit(annual_maxima)  # MLE
intensity_rp  = genextreme.ppf(1 - 1/return_period, c, loc, scale)
```
    """)

# Step 4
with st.expander(_step_header("4", "📉", "Vulnerability Functions", "#8e44ad"), expanded=False):
    col_a, col_b = st.columns([3, 2])
    with col_a:
        st.markdown("""
**Maps hazard intensity → damage fraction [0–1]**

| Hazard | Source | Asset types |
|---|---|---|
| Flood | FEMA HAZUS 6.0 | 21 types (via alias map) |
| Flood (EU) | JRC Global DDFs (Huizinga 2017) | Applied for European ISO3 codes |
| Wind | HAZUS MH Wind Fragility | Weibull MDR curves per material |
| Wildfire | Syphard et al. (2012) + HAZUS | Flame length / FWI band |
| Heat | IEA/ILO degree-day + productivity | Temp → HVAC cost + labor loss |

**Interpolation:** Monotonic Pchip cubic spline — avoids oscillation artefacts.

**First-floor height adjustment for flood:**
```python
effective_depth = max(0.0, flood_depth_m - first_floor_height_m)
damage_fraction = curve.evaluate(effective_depth)
```

**Curve alias system:** New asset types (e.g. `data_center`, `hotel_resort`) are mapped to the
closest existing HAZUS occupancy class curve. No duplicate JSON data needed.
        """)
    with col_b:
        depths = np.linspace(0, 3.0, 100)
        fig_ddf = go.Figure()
        for label, k, color in [
            ("Residential masonry", -2.0, BSR["navy"]),
            ("Commercial steel",    -1.8, BSR["orange"]),
            ("Industrial steel",    -2.5, BSR["teal"]),
        ]:
            y = 1 / (1 + np.exp(k * (depths - 1.1)))
            fig_ddf.add_trace(go.Scatter(x=depths, y=y, name=label,
                                         line=dict(color=color, width=2)))
        fig_ddf.update_layout(
            title="Illustrative Flood Depth-Damage Curves",
            xaxis_title="Flood depth (m)",
            yaxis_title="Damage fraction",
            height=250, margin=dict(l=0,r=0,t=40,b=30),
            legend=dict(orientation="h", y=1.4, font=dict(size=10)),
            plot_bgcolor="white", paper_bgcolor="white",
        )
        st.plotly_chart(fig_ddf, use_container_width=True)
        st.caption("Illustrative only. Actual curves from HAZUS 6.0 / JRC.")

# Step 5
with st.expander(_step_header("5", "📊", "EAD Calculation & Scores", BSR["red"]), expanded=False):
    col_a, col_b = st.columns([3, 2])
    with col_a:
        st.markdown("""
**Expected Annual Damage (EAD) — the probability-weighted average annual loss.**

```python
# Return periods → annual exceedance probabilities
aep = 1.0 / np.array([2, 5, 10, 25, 50, 100, 250, 500, 1000])
losses = damage_fractions * asset_value

# Trapezoidal integration of the Loss EP curve
ead = np.trapezoid(losses[np.argsort(aep)], aep[np.argsort(aep)])
```

**Climate change timeline (2025–2050):**
```python
for year in range(2025, 2051):
    multiplier = interpolate(scenario_multipliers, year)
    ead_year   = ead_baseline * multiplier
    pv_year    = ead_year / (1 + discount_rate) ** (year - 2025)
```

**Climate Exposure Score (1–10):**
```
score = 1 + 9 × log(1 + raw_pct / midpoint) / log(1 + max_pct / midpoint)
```
Log-normalised so all scores use the full 1–10 range even when one asset dominates.

**Expected Annual Loss Ratio (EALR):**  `EALR% = EAD_2050 / replacement_value × 100`
(Note: This is an expected-loss ratio, not a tail Value-at-Risk measure.)

**Monte Carlo uncertainty:** 1,000 draws at ±20% vulnerability curve CoV → 5th/95th CI.
        """)
    with col_b:
        rps = np.array([2, 5, 10, 25, 50, 100, 250, 500, 1000])
        aep_ex = 1.0 / rps
        losses_ex = 0.01 * (1 - np.exp(-0.003 * rps)) * 10_000_000
        _trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz")
        ead_ex = _trapz(losses_ex[::-1], aep_ex[::-1])
        fig_ep = go.Figure()
        fig_ep.add_trace(go.Scatter(
            x=losses_ex[::-1], y=aep_ex[::-1],
            mode="lines+markers",
            line=dict(color=BSR["navy"], width=2.5),
            fill="tozeroy", fillcolor=f"{BSR['navy']}18",
            name="EP curve",
        ))
        fig_ep.add_vline(x=ead_ex, line_dash="dot", line_color=BSR["red"],
                         annotation_text=f"EAD")
        fig_ep.update_layout(
            title="Loss Exceedance Probability Curve",
            xaxis_title="Loss ($)", yaxis_title="Annual Exceedance Prob.",
            yaxis_type="log", height=260,
            margin=dict(l=0,r=0,t=40,b=20),
            plot_bgcolor="white", paper_bgcolor="white",
            showlegend=False,
        )
        st.plotly_chart(fig_ep, use_container_width=True)
        st.caption("Area under curve = EAD. Red dashed line marks the expected annual loss.")

# Step 6
with st.expander(_step_header("6", "🛡️", "Adaptation ROI & DCF Impairment", BSR["green"]), expanded=False):
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("""
**Adaptation Cost-Benefit Analysis:**
```python
npv_benefits = sum(
    avoided_ead / (1 + discount_rate)**t
    for t in range(1, design_life_years + 1)
)
cbr           = npv_benefits / (capex + npv_opex)
roi_pct       = (npv_benefits - total_cost) / total_cost * 100
payback_years = capex / avoided_ead
```

A measure is justified when **CBR > 1.0**; strongly beneficial at **CBR > 2.0**.

**19+ measure catalog:**
- 🌊 Flood: barriers, elevated foundations, sump pumps, permeable paving
- 🌬️ Wind: roof reinforcement, storm shutters, anchor bolts, wind-rated glazing
- 🔥 Wildfire: ember vents, non-combustible cladding, vegetation clearance zones
- ☀️ Heat: improved insulation, cool roofs, HVAC upgrades, green roofs

*Sources: FEMA BCA Toolkit (2021) · EA Appraisal Guide (2019) · HM Treasury Green Book (2022)*
        """)
    with col_b:
        st.markdown("""
**Climate-Adjusted DCF:**
```python
# Annual free cash flow discounted at WACC
dcf_base = sum(FCF_t / (1+wacc)**t for t in years)

# Subtract present value of climate damage stream
dcf_adjusted = dcf_base - total_pv_damages

# Impairment
impairment_pct = (dcf_base - dcf_adjusted) / dcf_base * 100
```

**Scenario-weighted:**
```python
weighted_npv = mean(dcf_adjusted_per_scenario)
```

**Stranded asset flag:**
```
cumulative_pv_damages / replacement_value > threshold (default 15%)
```
Signals financial impairment before end of economic life.

*Sources: TCFD (2017) · IPCC AR6 WG2 Ch.16 · Commercial underwriting practice*
        """)

# ════════════════════════════════════════════════════════════════════════════
# DATA SOURCES TABLE
# ════════════════════════════════════════════════════════════════════════════
st.markdown(f"<h2 id='data-sources' style='color:{BSR['navy']};margin-top:16px;'>Data Sources & Citations</h2>", unsafe_allow_html=True)

_SOURCES = pd.DataFrame([
    {"Module": "Heat / Wind / Flood / Wildfire",  "Source": "ISIMIP3b (GSWP3-W5E5)",       "Reference": "Lange et al. (2021) Earth Syst. Sci. Data"},
    {"Module": "Water Stress",                    "Source": "WRI Aqueduct 4.0",             "Reference": "Kuzma et al. (2023) WRI Technical Note"},
    {"Module": "Hazard multipliers",              "Source": "IPCC AR6 WG1",                 "Reference": "Tabari (2020); Knutson et al. (2020); Jolly et al. (2015); Zhao et al. (2021)"},
    {"Module": "Flood — North America",           "Source": "FEMA HAZUS 6.0",               "Reference": "FEMA (2022) Technical Manual"},
    {"Module": "Flood — Europe",                  "Source": "JRC Global DDFs",              "Reference": "Huizinga et al. (2017) JRC EUR 28612 EN"},
    {"Module": "Wind fragility",                  "Source": "HAZUS MH Wind",                "Reference": "FEMA HAZUS MH Technical Manual (2012)"},
    {"Module": "Wildfire vulnerability",          "Source": "Syphard et al. + HAZUS",       "Reference": "Syphard et al. (2012) PLOS ONE; FEMA (2022)"},
    {"Module": "Wildfire FWI",                    "Source": "Canadian FWI System",          "Reference": "Van Wagner (1987) Canadian Forestry Service"},
    {"Module": "Heat productivity",               "Source": "ILO / Zhao et al.",            "Reference": "Zhao et al. (2021) Nature; ILO (2019)"},
    {"Module": "Elevation (auto-detect)",         "Source": "OpenTopoData ASTER 30m DEM",   "Reference": "NASA ASTER GDEM v3 (2019); opentopodata.org"},
    {"Module": "Country (auto-detect)",           "Source": "BigDataCloud Reverse Geocode", "Reference": "OpenStreetMap contributors; bigdatacloud.net"},
    {"Module": "Scenarios — BSR",                 "Source": "BSR Climate Scenarios 2025",   "Reference": "BSR (2024) bsr.org/reports/bsr-climate-scenarios-2025"},
    {"Module": "Scenarios — NGFS",                "Source": "NGFS Phase V (Nov 2023)",      "Reference": "NGFS (2023) ngfs.net/ngfs-scenarios-portal/"},
    {"Module": "Scenarios — IEA",                 "Source": "IEA WEO 2023",                 "Reference": "IEA (2023) iea.org/reports/world-energy-outlook-2023"},
    {"Module": "EAD methodology",                 "Source": "FEMA BCA Toolkit",             "Reference": "FEMA (2021); Swiss Re sigma 1/2023"},
    {"Module": "Adaptation costs",                "Source": "HM Treasury Green Book",       "Reference": "HM Treasury (2022 update); EA Appraisal Guide (2019)"},
])

st.dataframe(_SOURCES, use_container_width=True, hide_index=True)

st.markdown(
    f"""
    <div style="background:{BSR['light']};border-left:4px solid {BSR['orange']};
                border-radius:6px;padding:14px 18px;margin-top:16px;font-size:13px;color:#555;">
      <strong>Disclaimer:</strong> Results are quantitative estimates based on published climate
      science and peer-reviewed vulnerability functions. Uncertainty bounds reflect vulnerability
      function uncertainty only; scenario uncertainty is captured by running multiple scenarios.
      Consult licensed climate risk specialists for regulatory disclosures (TCFD, CSRD, ISSB S2).
    </div>
    """,
    unsafe_allow_html=True,
)
