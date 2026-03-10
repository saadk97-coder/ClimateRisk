"""
Page 10 – Methodology: Interactive schematic of the platform's data flow,
calculation pipeline, and methodology with expandable deep-dives.
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import pandas as pd

st.set_page_config(page_title="Methodology", page_icon="📐", layout="wide")

with st.sidebar:
    st.header("About This Page")
    st.markdown(
        "An interactive walkthrough of the BSR Climate Risk platform — "
        "from asset data entry to financial damage output. "
        "Hover over nodes in the diagram for details."
    )
    st.divider()
    st.caption(
        "**Built on:**\n\n"
        "- HAZUS 6.0 · JRC DDFs · Syphard et al.\n"
        "- ISIMIP3b · NASA NEX-GDDP · WRI Aqueduct 4.0\n"
        "- NGFS Phase V · IPCC AR6 · BSR Climate Scenarios 2025\n"
        "- scipy · xarray · streamlit"
    )

st.markdown(
    "<h1 style='color:#333;'>"
    "<span style='color:#F4721A;font-weight:900;'>BSR</span> Platform Methodology"
    "</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "An end-to-end walkthrough of how the platform translates **asset data + climate scenarios** "
    "into **financial damage estimates**. Click any section below for a deep-dive."
)

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION A — INTERACTIVE FLOW DIAGRAM
# ═══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("Platform Data Flow")

# Node positions (x, y) and labels — arranged in a left-to-right flow
# Columns: Input (x=0), Hazard (x=1), Vulnerability (x=2), EAD (x=3), Output (x=4)

_NODE_DATA = [
    # --- Inputs ---
    dict(id=0, x=0.0,  y=3.0, label="Asset Portfolio",      category="Input",
         desc="Replacement values, lat/lon, asset type, construction material, year built, elevation above flood plain"),
    dict(id=1, x=0.0,  y=1.5, label="Climate Scenarios",    category="Input",
         desc="BSR 2025 / NGFS Phase V / IEA WEO 2023 / IPCC AR6 — 14 scenarios covering 1.5°C to 4.3°C warming"),
    dict(id=2, x=0.0,  y=0.0, label="Financial Parameters", category="Input",
         desc="Discount rate (default 3.5% HM Treasury Green Book), WACC for DCF, analysis horizon 2025–2050"),

    # --- Hazard data ---
    dict(id=3, x=1.0,  y=4.2, label="ISIMIP3b API",         category="Hazard",
         desc="ISIMIP3b GSWP3-W5E5 bias-adjusted climate data. GCMs: GFDL-ESM4, IPSL-CM6A-LR, MPI-ESM1-2-HR. Variables: tasmax (heat), sfcwind (wind), pr (flood proxy), FWI components (wildfire)"),
    dict(id=4, x=1.0,  y=2.8, label="WRI Aqueduct 4.0",     category="Hazard",
         desc="Water stress projections to 2080 under SSP1/2/3/5. Indicators: baseline water stress, depletion, variability"),
    dict(id=5, x=1.0,  y=1.4, label="Scenario Multipliers", category="Hazard",
         desc="IPCC AR6 hazard scaling factors: flood +5–8%/°C (Tabari 2020), wind +5%/2°C (Knutson 2020), wildfire FWI season length (Jolly 2015), heat productivity loss (Zhao 2021)"),
    dict(id=6, x=1.0,  y=0.0, label="Regional Fallback",    category="Hazard",
         desc="Built-in table of median hazard intensities by region, scenario, and return period. Used when ISIMIP API is unavailable or returns insufficient data"),

    # --- Vulnerability ---
    dict(id=7, x=2.0,  y=4.2, label="HAZUS 6.0 Flood DDFs", category="Vulnerability",
         desc="FEMA HAZUS 6.0 depth-damage functions: 25 occupancy types × 4 construction materials. Source: FEMA (2022)"),
    dict(id=8, x=2.0,  y=3.1, label="JRC Global DDFs",      category="Vulnerability",
         desc="Joint Research Centre depth-damage functions for European building stock. Huizinga et al. (2017)"),
    dict(id=9, x=2.0,  y=2.0, label="Wind Fragility",       category="Vulnerability",
         desc="HAZUS MH wind fragility curves: Weibull CDF parameterised by mean damage ratio (MDR) and coefficient of variation per construction class"),
    dict(id=10, x=2.0, y=0.9, label="Wildfire FWI Pipeline",category="Vulnerability",
         desc="Canadian Forest Fire Weather Index (Van Wagner 1987): FFMC → DMC → DC → ISI → BUI → FWI. Annual maxima → return period losses via GEV"),
    dict(id=11, x=2.0, y=-0.2,label="Heat & Water Stress",  category="Vulnerability",
         desc="Heat: IEA degree-day cooling cost escalation + ILO productivity loss curves (Zhao et al. 2021). Water stress: WRI Aqueduct 4.0 sector-specific sensitivity weights"),

    # --- EAD ---
    dict(id=12, x=3.0, y=2.5, label="Return Period Grid",   category="EAD",
         desc="Standard return periods: 2, 5, 10, 25, 50, 100, 250, 500, 1000 years. GEV fitting (scipy.stats.genextreme) to annual maxima for each hazard"),
    dict(id=13, x=3.0, y=1.2, label="EAD Integration",      category="EAD",
         desc="Trapezoidal integration under the Loss Exceedance Probability (EP) curve: EAD = ∫ L(p) dp over [0,1]. Annual hazard probability × loss at each return period"),
    dict(id=14, x=3.0, y=0.0, label="Monte Carlo CI",        category="EAD",
         desc="1,000 parameter draws from vulnerability curve uncertainty distributions → 5th / 95th percentile confidence interval on EAD"),

    # --- Outputs ---
    dict(id=15, x=4.0, y=4.0, label="Annual EAD 2025–50",   category="Output",
         desc="Per-asset, per-hazard, per-scenario annual EAD for each year 2025–2050. Discounted to present value at selected discount rate"),
    dict(id=16, x=4.0, y=2.8, label="Exposure Scores",      category="Output",
         desc="Climate Exposure Score (1–10) and Physical Climate VaR (%) per asset × hazard. Log-normalised transformation with HAZUS-calibrated thresholds"),
    dict(id=17, x=4.0, y=1.6, label="Adaptation ROI",       category="Output",
         desc="NPV cost-benefit analysis for 19+ adaptation measures. CBR = NPV(avoided EAD) / (capex + NPV opex). Payback = capex / avoided EAD annual"),
    dict(id=18, x=4.0, y=0.4, label="DCF & Stranded Asset", category="Output",
         desc="Climate-adjusted NPV impairment: scenario-weighted PV of damage reduces terminal value. Stranded asset flag: cumulative PV damages > threshold % of replacement value"),
]

# Edges: (from_id, to_id)
_EDGES = [
    (0, 12), (0, 7), (0, 9), (0, 10), (0, 11),
    (1, 5),  (1, 4),
    (2, 13), (2, 14), (2, 17), (2, 18),
    (3, 12),
    (4, 11),
    (5, 12),
    (6, 12),
    (7, 13), (8, 13), (9, 13), (10, 13), (11, 13),
    (12, 13),
    (13, 15), (13, 16),
    (14, 15),
    (15, 17), (15, 18), (15, 16),
]

_CATEGORY_COLORS = {
    "Input":          "#1A3A5C",
    "Hazard":         "#2A9D8F",
    "Vulnerability":  "#F4721A",
    "EAD":            "#E9C46A",
    "Output":         "#27ae60",
}

_id_to_node = {n["id"]: n for n in _NODE_DATA}

fig_flow = go.Figure()

# Draw edges first (behind nodes)
for src_id, dst_id in _EDGES:
    src = _id_to_node[src_id]
    dst = _id_to_node[dst_id]
    fig_flow.add_trace(go.Scatter(
        x=[src["x"], dst["x"]],
        y=[src["y"], dst["y"]],
        mode="lines",
        line=dict(color="rgba(180,180,180,0.5)", width=1.2),
        hoverinfo="skip",
        showlegend=False,
    ))

# Draw nodes per category
for cat, color in _CATEGORY_COLORS.items():
    cat_nodes = [n for n in _NODE_DATA if n["category"] == cat]
    if not cat_nodes:
        continue
    fig_flow.add_trace(go.Scatter(
        x=[n["x"] for n in cat_nodes],
        y=[n["y"] for n in cat_nodes],
        mode="markers+text",
        name=cat,
        text=[n["label"] for n in cat_nodes],
        textposition="middle right",
        textfont=dict(size=11, color="#222"),
        marker=dict(
            color=color,
            size=22,
            symbol="circle",
            line=dict(color="white", width=2),
        ),
        customdata=[n["desc"] for n in cat_nodes],
        hovertemplate="<b>%{text}</b><br><br>%{customdata}<extra></extra>",
        showlegend=True,
    ))

# Column header annotations
_COLUMN_HEADERS = [
    (0.0, 5.0, "INPUTS"),
    (1.0, 5.0, "HAZARD DATA"),
    (2.0, 5.0, "VULNERABILITY"),
    (3.0, 5.0, "EAD CALC"),
    (4.0, 5.0, "OUTPUTS"),
]
for cx, cy, label in _COLUMN_HEADERS:
    fig_flow.add_annotation(
        x=cx, y=cy, text=f"<b>{label}</b>",
        showarrow=False,
        font=dict(size=13, color="#555"),
        xanchor="center",
    )

fig_flow.update_layout(
    height=540,
    margin=dict(l=20, r=20, t=20, b=20),
    xaxis=dict(
        range=[-0.3, 4.8],
        showticklabels=False, showgrid=False, zeroline=False,
    ),
    yaxis=dict(
        range=[-0.8, 5.5],
        showticklabels=False, showgrid=False, zeroline=False,
    ),
    plot_bgcolor="white",
    paper_bgcolor="white",
    legend=dict(
        orientation="h", yanchor="top", y=-0.02, xanchor="center", x=0.5,
        title="Category:",
        font=dict(size=12),
    ),
    hovermode="closest",
)

st.plotly_chart(fig_flow, use_container_width=True)
st.caption(
    "Hover over any node for details. "
    "Arrows show the data flow from asset inputs through hazard data, "
    "vulnerability functions, and EAD integration to financial outputs."
)

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION B — STEP-BY-STEP METHODOLOGY DEEP DIVES
# ═══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("Step-by-Step Methodology")
st.markdown(
    "Expand any section below for a detailed explanation of each stage, "
    "including data sources, equations, and calibration notes."
)

# ── STEP 1: Asset Definition ────────────────────────────────────────────────
with st.expander("**Step 1 — Asset Portfolio Definition**", expanded=False):
    col_a, col_b = st.columns([3, 2])
    with col_a:
        st.markdown("""
**What you provide:**
- Asset ID, name, location (lat/lon)
- Asset type (e.g. `commercial_steel`, `residential_masonry`)
- Replacement value in your chosen currency
- Construction material, year built, number of stories
- Roof type, basement, elevation above flood plain (m)
- Country code (ISO3) for regional curve selection

**Why each parameter matters:**

| Parameter | Used in |
|---|---|
| **Asset type** | Selects the vulnerability curve family (HAZUS occupancy class) |
| **Construction material** | Adjusts damage fraction within the curve (e.g. masonry vs steel) |
| **Year built** | Post-1994 buildings use HAZUS modern construction standards |
| **Elevation above flood plain** | Directly reduces flood damage fraction — 1m elevation can halve EAD |
| **Region (ISO3)** | Selects regional depth-damage function (JRC for Europe, HAZUS for US) |
| **Replacement value** | Converts damage fraction to absolute loss (£) |

**Tip:** The most impactful parameters for damage results are **elevation_m** (flood), **construction_material** (wind/flood), and **replacement_value** (absolute loss scale).
        """)
    with col_b:
        st.markdown("**Asset type catalog (examples):**")
        example_types = pd.DataFrame([
            {"Type": "residential_masonry",  "HAZUS Class": "RES1", "Primary Hazards": "Flood, Wind"},
            {"Type": "residential_wood",     "HAZUS Class": "RES1", "Primary Hazards": "Wind, Wildfire"},
            {"Type": "commercial_steel",     "HAZUS Class": "COM1", "Primary Hazards": "Flood, Wind"},
            {"Type": "commercial_office",    "HAZUS Class": "COM4", "Primary Hazards": "Heat, Flood"},
            {"Type": "industrial_warehouse", "HAZUS Class": "IND1", "Primary Hazards": "Wind, Flood"},
            {"Type": "critical_infrastructure", "HAZUS Class": "GOV2", "Primary Hazards": "All"},
        ])
        st.dataframe(example_types, use_container_width=True, hide_index=True)
        st.caption(
            "Full catalog: 20+ asset types mapped to HAZUS occupancy classes. "
            "Source: FEMA HAZUS 6.0 Technical Manual (2022)."
        )

# ── STEP 2: Climate Scenarios ────────────────────────────────────────────────
with st.expander("**Step 2 — Climate Scenario Selection**", expanded=False):
    col_a, col_b = st.columns([3, 2])
    with col_a:
        st.markdown("""
**Four scenario frameworks are available:**

1. **BSR Climate Scenarios 2025** — narrative + quantitative; cross-functional corporate use
2. **NGFS Phase V** — standard for TCFD/TNFD financial disclosure
3. **IEA WEO 2023** — energy system focus; covers Net Zero, APS, STEPS
4. **IPCC AR6 SSPs** — canonical physical science scenarios

**BSR scenarios are quantitatively grounded in NGFS/SSP** — see the mapping table on the Scenarios page. BSR provides unique value through its qualitative regional narratives and cross-functional framing, which overlay the quantitative SSP outputs.

**Hazard multipliers** are derived from IPCC AR6 WG1 findings:

| Hazard | Scaling relationship | Source |
|---|---|---|
| Flood | ~5–8% increase in extreme precipitation per °C above baseline | Tabari (2020) *Sci. Total Env.* |
| Wind | Max tropical cyclone intensity +5% per 2°C | Knutson et al. (2020) *BAMS* |
| Wildfire | Fire weather season lengthening; burned area ∝ FWI² | Jolly et al. (2015) *Nat. Comms.* |
| Heat | Productivity loss super-linear above 2°C; cooling costs ∝ CDD | Zhao et al. (2021) *Nature* |
| Water Stress | ~4% per °C reduction in freshwater availability | WRI Aqueduct 4.0 (2023) |

All multipliers are applied against a **1995–2014 historical baseline** (consistent with ISIMIP3b and IPCC AR6 reference period).
        """)
    with col_b:
        _sc_df = pd.DataFrame([
            {"Scenario": "BSR Net Zero 2050",        "SSP": "SSP1-1.9", "2050 °C": 1.5, "2080 °C": 1.5},
            {"Scenario": "BSR Delayed Transition",   "SSP": "SSP2-4.5", "2050 °C": 2.0, "2080 °C": 2.4},
            {"Scenario": "BSR Current Policies",     "SSP": "SSP5-8.5", "2050 °C": 3.0, "2080 °C": 4.3},
            {"Scenario": "BSR Fragmented World",     "SSP": "SSP3-7.0", "2050 °C": 2.5, "2080 °C": 3.5},
            {"Scenario": "NGFS Current Policies",    "SSP": "SSP5-8.5", "2050 °C": 3.0, "2080 °C": 4.3},
            {"Scenario": "IEA NZE",                  "SSP": "SSP1-1.9", "2050 °C": 1.5, "2080 °C": 1.5},
            {"Scenario": "IPCC AR6 SSP2-4.5",        "SSP": "SSP2-4.5", "2050 °C": 2.0, "2080 °C": 2.7},
            {"Scenario": "IPCC AR6 SSP5-8.5",        "SSP": "SSP5-8.5", "2050 °C": 3.3, "2080 °C": 4.4},
        ])
        st.markdown("**Warming at key horizons:**")
        fig_sc_warm = px.bar(
            _sc_df.melt(id_vars=["Scenario"], value_vars=["2050 °C", "2080 °C"], var_name="Horizon", value_name="Warming (°C)"),
            x="Scenario", y="Warming (°C)", color="Horizon",
            barmode="group",
            color_discrete_map={"2050 °C": "#F4721A", "2080 °C": "#C94040"},
        )
        fig_sc_warm.update_layout(
            height=280, margin=dict(l=0, r=0, t=10, b=100),
            xaxis_tickangle=-35, showlegend=True,
            legend=dict(orientation="h", y=1.1),
            plot_bgcolor="white", paper_bgcolor="white",
        )
        fig_sc_warm.add_hline(y=1.5, line_dash="dot", line_color="#27ae60", annotation_text="Paris 1.5°C")
        fig_sc_warm.add_hline(y=2.0, line_dash="dot", line_color="#e67e22", annotation_text="Paris 2.0°C")
        st.plotly_chart(fig_sc_warm, use_container_width=True)

# ── STEP 3: Hazard Data ──────────────────────────────────────────────────────
with st.expander("**Step 3 — Hazard Data Retrieval**", expanded=False):
    st.markdown("""
**The platform follows a priority hierarchy for hazard data:**

```
1. ISIMIP3b API (granular point-level GCM output)
   └── isimip-client v2 → select_point() → ZIP of NetCDF4 files
   └── GEV fitting to annual maxima → return period intensities

2. WRI Aqueduct 4.0 (water stress only)
   └── Pre-aggregated basin-level projections to 2080

3. Regional fallback table (built-in)
   └── Median hazard intensities by region × scenario × return period
   └── Used when ISIMIP API is unavailable or returns < 10 years of data
```

**Per hazard, what ISIMIP3b provides:**

| Hazard | ISIMIP Variable | Derivation |
|---|---|---|
| Heat | `tasmax` | Annual maximum daily temperature → GEV → return period °C |
| Wind | `sfcwind` | Annual maximum wind speed → GEV → return period m/s |
| Flood | `pr` (precipitation) | Annual maximum daily precipitation → JRC empirical scaling → depth (m). *Rx1day threshold: 25mm; depth factor: 0.012 m/mm* |
| Wildfire | `tasmax`, `pr`, `hurs`, `sfcwind` | Full Canadian FWI pipeline (Van Wagner 1987) → annual maximum FWI → GEV |

**GCMs used:** GFDL-ESM4, IPSL-CM6A-LR, MPI-ESM1-2-HR, MRI-ESM2-0, UKESM1-0-LL (5-model ensemble, bias-adjusted to W5E5 observational baseline)

**GEV fitting:**
```python
from scipy.stats import genextreme
c, loc, scale = genextreme.fit(annual_maxima)          # MLE
intensity_rp  = genextreme.ppf(1 - 1/return_period, c, loc, scale)
```

**Flood depth derivation (JRC-calibrated):**
```python
DRAINAGE_THRESHOLD_MM = 25.0   # urban drainage capacity
DEPTH_FACTOR = 0.012           # m per excess mm (JRC calibration)
depth_m = max(0, (rx1day_mm - DRAINAGE_THRESHOLD_MM) * DEPTH_FACTOR)
# London RP100: Rx1day ≈ 53mm → depth ≈ 0.34m
```

Source: Alfieri et al. (2017) *NHESS*, JRC Technical Report EUR 28612 EN.
    """)

# ── STEP 4: Vulnerability Functions ─────────────────────────────────────────
with st.expander("**Step 4 — Vulnerability Functions**", expanded=False):
    col_a, col_b = st.columns([3, 2])
    with col_a:
        st.markdown("""
**Vulnerability functions map hazard intensity → damage fraction (0–1)**

The platform uses a library of published depth-damage and fragility functions:

**Flood (depth-damage functions):**
- **HAZUS 6.0** (FEMA 2022): 25 occupancy types × 4 construction materials
- **JRC Global DDFs** (Huizinga et al. 2017): European building stock, validated across 7 EU countries
- Curve selection: JRC for European regions (GBR, FRA, DEU, NLD, etc.), HAZUS elsewhere
- Interpolation: **monotonic Pchip spline** (`scipy.interpolate.PchipInterpolator`) — avoids oscillation artefacts from cubic splines

**Wind (fragility curves):**
- **HAZUS MH** wind fragility: parameterised as Weibull CDF
- Mean Damage Ratio (MDR) as function of 3-second gust wind speed
- Per construction class: wood_frame, masonry, steel, concrete

**Wildfire:**
- Syphard et al. (2012): structure loss vs. Fire Radiative Power
- HAZUS wildfire: direct damage fraction from FWI bands
- Ember ignition probability model for wood-frame structures

**Heat (chronic):**
- IEA/IPCC degree-day cooling cost escalation: `ΔOPEX ∝ ΔCDD × floor_area × cooling_intensity`
- ILO productivity loss: `damage_pct = max(0, (temp - 25°C) × 0.3%/°C) × exposure_factor`

**Elevation adjustment for flood:**
```python
effective_depth = max(0.0, flood_depth_m - elevation_m)
damage_frac = curve.evaluate(effective_depth)  # 0 if below flood plain
```
        """)
    with col_b:
        # Illustrative depth-damage curve
        depths = np.linspace(0, 3.0, 100)
        # Simple logistic approximation of HAZUS residential masonry curve
        dd_residential = 1 / (1 + np.exp(-2.5 * (depths - 1.0)))
        dd_commercial  = 1 / (1 + np.exp(-2.0 * (depths - 0.8)))
        dd_industrial  = 1 / (1 + np.exp(-3.0 * (depths - 1.5)))

        fig_ddf = go.Figure()
        fig_ddf.add_trace(go.Scatter(x=depths, y=dd_residential, name="Residential masonry", line=dict(color="#2A9D8F", width=2)))
        fig_ddf.add_trace(go.Scatter(x=depths, y=dd_commercial,  name="Commercial steel",   line=dict(color="#F4721A", width=2)))
        fig_ddf.add_trace(go.Scatter(x=depths, y=dd_industrial,  name="Industrial",         line=dict(color="#1A3A5C", width=2)))
        fig_ddf.update_layout(
            title="Illustrative Flood Depth-Damage Functions",
            xaxis_title="Flood depth (m)", yaxis_title="Damage fraction (0–1)",
            height=260, margin=dict(l=0, r=0, t=40, b=30),
            legend=dict(orientation="h", y=1.3, font=dict(size=10)),
            plot_bgcolor="white", paper_bgcolor="white",
        )
        st.plotly_chart(fig_ddf, use_container_width=True)
        st.caption(
            "Illustrative shape only. Actual curves from HAZUS 6.0 (FEMA 2022) "
            "and Huizinga et al. (2017) JRC Global DDFs."
        )

# ── STEP 5: EAD Calculation ──────────────────────────────────────────────────
with st.expander("**Step 5 — Expected Annual Damage (EAD) Calculation**", expanded=False):
    col_a, col_b = st.columns([3, 2])
    with col_a:
        st.markdown("""
**EAD is the probability-weighted average annual loss — the 'fair value' of climate damage.**

**Standard return period grid:**
`[2, 5, 10, 25, 50, 100, 250, 500, 1000 years]`
→ Annual Exceedance Probabilities (AEP): `[0.5, 0.2, 0.1, 0.04, 0.02, 0.01, 0.004, 0.002, 0.001]`

**Algorithm:**
```python
def calc_ead(return_periods, damage_fractions, asset_value):
    # Convert return periods → annual exceedance probabilities
    aep = 1.0 / np.array(return_periods)

    # Scale to absolute losses
    losses = np.array(damage_fractions) * asset_value

    # Sort by increasing probability (i.e. decreasing return period)
    order  = np.argsort(aep)

    # Trapezoidal integration under Loss Exceedance Probability curve
    ead = np.trapz(losses[order], aep[order])
    return ead
```

**Discounting to present value:**
```python
pv_t = ead_t / (1 + discount_rate) ** (year - base_year)
total_pv = sum(pv_t for year in range(2025, 2051))
```

**Climate change adjustment (annual):**
```python
# Linear interpolation of hazard multiplier between scenario years
multiplier_t = interpolate(scenario_multipliers, year)
ead_t = ead_baseline * multiplier_t
```

**Why trapezoidal integration?**
The EP curve (loss vs. probability) represents the full distribution of annual losses.
The area under this curve equals the expected annual loss — EAD.
Trapezoidal integration is numerically stable and unbiased for unevenly spaced return period grids.

Source: FEMA BCA Toolkit (2021) · Swiss Re Institute *sigma 1/2023* ·
Wagenaar et al. (2017) *NHESS*
        """)
    with col_b:
        # Illustrative EP curve
        rps = np.array([2, 5, 10, 25, 50, 100, 250, 500, 1000])
        aep = 1.0 / rps
        losses_example = 0.01 * (1 - np.exp(-0.003 * rps)) * 5_000_000  # illustrative

        fig_ep = go.Figure()
        fig_ep.add_trace(go.Scatter(
            x=losses_example[::-1], y=aep[::-1],
            mode="lines+markers",
            line=dict(color="#2980b9", width=2.5),
            fill="tozeroy", fillcolor="rgba(41,128,185,0.08)",
            name="EP curve",
            hovertemplate="Loss: £%{x:,.0f}<br>AEP: %{y:.3f}<extra></extra>",
        ))
        # EAD line (approximate centroid)
        ead_example = np.trapz(losses_example[::-1], aep[::-1])
        fig_ep.add_vline(x=ead_example, line_dash="dot", line_color="#e74c3c",
                         annotation_text=f"EAD ≈ £{ead_example:,.0f}")
        fig_ep.update_layout(
            title="Illustrative Exceedance Probability Curve",
            xaxis_title="Loss (£)", yaxis_title="AEP",
            yaxis_type="log",
            height=280, margin=dict(l=0, r=0, t=40, b=30),
            legend=dict(font=dict(size=10)),
            plot_bgcolor="white", paper_bgcolor="white",
        )
        st.plotly_chart(fig_ep, use_container_width=True)
        st.caption(
            "Illustrative values. Area under the EP curve = EAD. "
            "EAD marked with dashed red line."
        )

# ── STEP 6: Portfolio Aggregation ────────────────────────────────────────────
with st.expander("**Step 6 — Portfolio Aggregation & Uncertainty**", expanded=False):
    st.markdown("""
**Portfolio EAD is not the simple sum of asset EADs** — flood events and windstorms
affect nearby assets simultaneously (positive correlation), while wildfire and heat
damage may be largely independent across geographically dispersed portfolios.

**Correlation adjustment:**
```python
# Pearson correlation matrix between asset EADs
# grouped by hazard type and geographic proximity
portfolio_ead_adjusted = sqrt(EAD_vector @ correlation_matrix @ EAD_vector)
```

**Current implementation:**
- **Same-hazard, same-region**: correlation coefficient = 0.7 (moderate–high)
- **Same-hazard, different-region**: 0.3 (some spatial correlation)
- **Different hazard**: 0.1 (largely independent)

This produces a **portfolio EAD** that is lower than the naive sum (due to diversification)
but higher than zero — reflecting the non-independent nature of physical climate events.

**Monte Carlo uncertainty (1,000 draws):**
```python
# Sample vulnerability curve parameters from empirical uncertainty distributions
# HAZUS reports ±20–30% coefficient of variation on depth-damage fractions
for draw in range(1000):
    noisy_damage_fractions = damage_fractions * (1 + np.random.normal(0, 0.20, size))
    ead_draws.append(calc_ead(return_periods, noisy_damage_fractions, asset_value))

ead_p05 = np.percentile(ead_draws, 5)
ead_p95 = np.percentile(ead_draws, 95)
```

The 5th/95th percentile confidence interval reflects vulnerability curve uncertainty — not
scenario uncertainty. Scenario uncertainty is captured by running multiple scenarios.

**Physical Climate VaR:**
```
VaR_pct = EAD_2050 / replacement_value × 100%
```

Portfolio VaR = asset-weighted average VaR, with correlation adjustment applied.

Source: McNeil, Frey & Embrechts (2005) *Quantitative Risk Management* ·
TCFD Physical Risk framing (2017) · FEMA HAZUS 6.0 User Manual
    """)

# ── STEP 7: Financial Outputs ────────────────────────────────────────────────
with st.expander("**Step 7 — Financial Outputs: Adaptation ROI & DCF**", expanded=False):
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("""
**Adaptation Return on Investment (ROI):**
```python
npv_benefits = sum(
    avoided_ead_annual / (1 + r)**t
    for t in range(1, design_life_years + 1)
)
cbr           = npv_benefits / (capex + npv_opex)
roi_pct       = (npv_benefits - total_cost) / total_cost * 100
payback_years = capex / avoided_ead_annual
```

A measure is **economically justified** when CBR > 1.0 and **strongly beneficial** when CBR > 2.0.

**Measure catalog (19+ measures):**
- **Flood**: flood barriers, elevated foundations, sump pumps, permeable paving
- **Wind**: roof reinforcement, storm shutters, anchor bolts, wind-rated glazing
- **Wildfire**: ember vents, non-combustible cladding, vegetation clearance
- **Heat**: improved insulation, cool roofs, HVAC upgrades, green roofs

Source: FEMA BCA Toolkit (2021) · EA Appraisal of Flood Risk Management (2019) ·
HM Treasury Green Book (2022)
        """)
    with col_b:
        st.markdown("""
**Climate-Adjusted DCF Valuation:**
```python
# Annual free cash flow, discounted at WACC
dcf_base = sum(FCF_t / (1 + wacc)**t for t in years)

# Subtract discounted climate damage stream
dcf_adjusted = dcf_base - total_pv_damages

# Impairment = base DCF - climate-adjusted DCF
impairment = dcf_base - dcf_adjusted
impairment_pct = impairment / dcf_base * 100
```

**Scenario-weighted impairment:**
```python
# Average across selected scenarios (equal weighting by default)
weighted_impairment = mean(impairment_per_scenario)
```

**Stranded asset flag:**
An asset is flagged as stranded when:
```
cumulative_pv_damages / replacement_value > threshold
```
Default threshold: 15% of replacement value over 2025–2050.
This signals the asset may be financially impaired by climate damage
before the end of its economic life.

Source: TCFD Physical Risk (2017) ·
IPCC AR6 WG2 Ch. 16 (Loss & Damage) ·
Commercial property underwriting practice (10–20% total-loss threshold)
        """)

# ── DATA SOURCES SUMMARY ─────────────────────────────────────────────────────
st.divider()
st.subheader("Data Sources & Citations")

_sources_df = pd.DataFrame([
    {
        "Module": "Hazard — Heat/Wind/Flood/Wildfire",
        "Source": "ISIMIP3b (GSWP3-W5E5 bias-adjusted)",
        "Variables": "tasmax, sfcwind, pr, hurs",
        "Reference": "Lange et al. (2021) Earth Syst. Sci. Data",
    },
    {
        "Module": "Hazard — Water Stress",
        "Source": "WRI Aqueduct 4.0",
        "Variables": "baseline_water_stress, interannual_variability",
        "Reference": "Kuzma et al. (2023) WRI Technical Note",
    },
    {
        "Module": "Hazard multipliers",
        "Source": "IPCC AR6 WG1",
        "Variables": "Flood, wind, wildfire, heat scaling",
        "Reference": "Tabari (2020), Knutson et al. (2020), Jolly et al. (2015), Zhao et al. (2021)",
    },
    {
        "Module": "Vulnerability — Flood",
        "Source": "FEMA HAZUS 6.0 + JRC Global DDFs",
        "Variables": "25 occupancy types × 4 materials",
        "Reference": "FEMA (2022); Huizinga et al. (2017) JRC EUR 28612 EN",
    },
    {
        "Module": "Vulnerability — Wind",
        "Source": "HAZUS MH Wind Fragility",
        "Variables": "3-second gust; Weibull MDR curves",
        "Reference": "FEMA HAZUS MH Technical Manual (2012)",
    },
    {
        "Module": "Vulnerability — Wildfire",
        "Source": "Syphard et al. (2012) + HAZUS",
        "Variables": "FWI, structure loss, ember ignition",
        "Reference": "Syphard et al. (2012) PLOS ONE; FEMA (2022)",
    },
    {
        "Module": "Wildfire FWI",
        "Source": "Canadian Forest Fire Weather Index",
        "Variables": "FFMC, DMC, DC, ISI, BUI, FWI",
        "Reference": "Van Wagner (1987) Canadian Forestry Service",
    },
    {
        "Module": "Scenarios — BSR",
        "Source": "BSR Climate Scenarios 2025",
        "Variables": "4 scenarios; NGFS-aligned narratives",
        "Reference": "BSR (2024) bsr.org/reports/bsr-climate-scenarios-2025",
    },
    {
        "Module": "Scenarios — NGFS",
        "Source": "NGFS Phase V (Nov 2023)",
        "Variables": "6 scenarios; GCAM 6.0, REMIND-MAgPIE 3.2",
        "Reference": "NGFS (2023) ngfs.net/ngfs-scenarios-portal/",
    },
    {
        "Module": "EAD / Adaptation",
        "Source": "FEMA BCA Toolkit + HM Treasury Green Book",
        "Variables": "Discount rate, NPV, CBR",
        "Reference": "FEMA (2021); HM Treasury (2022 update)",
    },
])

st.dataframe(_sources_df, use_container_width=True, hide_index=True)

st.caption(
    "**Disclaimer:** Results are quantitative estimates based on published climate science and "
    "open-source vulnerability functions. Uncertainty bounds (5th–95th percentile) reflect "
    "vulnerability function uncertainty only; scenario uncertainty is captured by running "
    "multiple scenarios. Consult licensed climate risk specialists for regulatory disclosures "
    "(TCFD, CSRD, ISSB S2)."
)
