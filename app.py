"""
BSR Climate Risk Intelligence Platform
Physical climate risk quantification aligned with BSR Climate Scenarios 2025.

Run with: streamlit run app.py
"""

import streamlit as st
from engine.fmt import fmt as _fmt, CURRENCIES

st.set_page_config(
    page_title="BSR Climate Risk Platform",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
if "assets" not in st.session_state:
    st.session_state.assets = []
if "selected_scenarios" not in st.session_state:
    st.session_state.selected_scenarios = ["current_policies", "net_zero_2050"]
if "selected_horizons" not in st.session_state:
    st.session_state.selected_horizons = [2050]
if "discount_rate" not in st.session_state:
    st.session_state.discount_rate = 0.035
if "results" not in st.session_state:
    st.session_state.results = []
if "currency_code" not in st.session_state:
    st.session_state.currency_code = "USD"

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    # BSR wordmark header
    st.markdown(
        "<div style='padding:12px 0 4px 0;'>"
        "<span style='font-size:22px;font-weight:800;color:#F4721A;letter-spacing:1px;'>BSR</span>"
        "<span style='font-size:13px;color:#666;margin-left:8px;'>Climate Risk Intelligence</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()
    # Currency selector
    _cur_options = list(CURRENCIES.keys())
    _cur_idx = _cur_options.index(st.session_state.currency_code) if st.session_state.currency_code in _cur_options else 0
    _new_cur = st.selectbox(
        "Currency",
        _cur_options,
        index=_cur_idx,
        format_func=lambda c: CURRENCIES[c]["label"],
        help="Display currency for all monetary values. Values are not converted — enter asset values in your chosen currency.",
        key="currency_selector",
    )
    st.session_state.currency_code = _new_cur
    _cur = st.session_state.currency_code

    st.divider()
    st.header("📊 Portfolio Summary")
    n = len(st.session_state.assets)
    total_val = sum(a.replacement_value for a in st.session_state.assets)
    st.metric("Assets", n)
    st.metric("Total Value", _fmt(total_val, _cur))

    if st.session_state.results:
        from engine.portfolio_aggregator import aggregate_portfolio
        sc = st.session_state.selected_scenarios[0] if st.session_state.selected_scenarios else None
        yr = st.session_state.selected_horizons[0] if st.session_state.selected_horizons else None
        if sc and yr:
            agg = aggregate_portfolio(st.session_state.results, sc, yr)
            st.metric("Portfolio EAD", _fmt(agg.get("portfolio_ead", 0), _cur))
            st.metric("EAD % of Value", f"{agg.get('ead_pct', 0):.2f}%")

    if "last_run" in st.session_state:
        st.caption(f"Last run: {st.session_state.last_run}")

    st.divider()
    st.caption(
        "**Hazard data:** ISIMIP3b historical baseline · WRI Aqueduct · coastal baseline · regional fallback\n\n"
        "**Vulnerability:** HAZUS 6.0 · JRC DDFs · Syphard et al.\n\n"
        "**Scenarios:** BSR 2025 · NGFS Phase V · IEA WEO 2023 · IPCC AR6\n\n"
        "[BSR Climate Scenarios 2025 ↗](https://www.bsr.org/en/reports/bsr-climate-scenarios-2025)"
    )

# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------
st.markdown(
    "<h1 style='color:#333333;'>"
    "<span style='color:#F4721A;font-weight:900;'>BSR</span> Climate Risk Intelligence Platform"
    "</h1>",
    unsafe_allow_html=True,
)

st.markdown(
    "Physical climate risk screening aligned with **BSR Climate Scenarios 2025** (NGFS Phase V). "
    "Translates hazard exposure into asset-level financial damage estimates with source citations "
    "and audit trails. Suitable for portfolio screening and risk triage — not a substitute for "
    "site-specific engineering assessments or professional catastrophe modelling."
)

# ── Headline metrics strip ───────────────────────────────────────────────────
total_val = sum(
    (a.replacement_value if hasattr(a, 'replacement_value') else a.get('replacement_value', 0))
    for a in st.session_state.assets
)
n_assets  = len(st.session_state.assets)
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("Assets", n_assets)
col_m2.metric("Portfolio Value", _fmt(total_val, _cur) if total_val > 0 else "—")
col_m3.metric("Scenarios Available", "14", help="6 NGFS Phase V · 3 IEA WEO 2023 · 5 IPCC AR6")
col_m4.metric("Hazards Covered", "6", help="Flood · Wind · Wildfire · Heat · Coastal Flood · Water Stress")

st.divider()

# ── Workflow table ────────────────────────────────────────────────────────────
st.subheader("Platform Workflow")
st.markdown("""
| Step | Page | Description |
|------|------|-------------|
| 1 | **Portfolio** | Upload assets via CSV or add them manually |
| 2 | **Scenarios** | Select scenarios — BSR 2025, NGFS Phase V, IEA WEO or IPCC AR6, with regional narrative insights |
| 3 | **Hazards** | Fetch hazard data (ISIMIP3b historical baseline → built-in regional fallback; WRI Aqueduct for water stress) |
| 4 | **Results** | Climate Exposure Scores, EALR (Expected Annual Loss Ratio), annual EAD 2025–2050, stranded asset flags |
| 5 | **Map** | Interactive risk map with water stress overlay, satellite imagery & building footprints |
| 6 | **Adaptation** | Adaptation Return on Investment (ROI) and cost-benefit for 20+ measures |
| 7 | **DCF** | Climate-adjusted NPV valuation with stranded asset analysis |
| 8 | **Audit** | Step-by-step calculation trace for any asset/scenario/year |
| 9 | **Vulnerability** | Damage functions with structural failure pathways and component-level analysis |
| 10 | **Governance** | Model scope, validation status, lineage controls, and known limitations |
""")

st.divider()

# ── Feature highlights ────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("### 📊 Risk Analytics")
    st.markdown("""
- **Climate Exposure Score** (1–10) per hazard per asset — normalised, comparable across portfolio
- **Expected Annual Loss Ratio (EALR %)** — expected damage as % of asset value
- **Stranded asset flags** — where cumulative climate costs exceed value thresholds
- **30-year forward risk projection** per scenario
    """)
with col2:
    st.markdown("### 🌍 Data & Scenarios")
    st.markdown("""
- **BSR Climate Scenarios 2025** with regional qualitative narratives (incl. *Fragmented World*)
- **6 hazards**: Flood, Wind, Wildfire, Heat, Coastal Flood, Water Stress
- **ISIMIP3b** historical baseline plus coastal and water-stress specialist pathways
- **WRI Aqueduct 4.0** — water stress projections to 2050
    """)
with col3:
    st.markdown("### 📐 Financial Outputs")
    st.markdown("""
- EAD via trapezoidal EP curve integration (screening-level)
- Annual 2025–2050 timeline, discounted to PV
- Adaptation Return on Investment (ROI %) with NPV benefits
- Climate-adjusted DCF — scenario-weighted NPV impairment
- Multi-sheet XLSX export for all outputs
    """)

st.divider()

col_info, col_warn = st.columns(2)
with col_info:
    st.info(
        "**Quick Start**: Portfolio → Scenarios → Hazards → Results → Map → DCF\n\n"
        "All ℹ️ icons throughout the platform provide source citations and methodology notes."
    )
with col_warn:
    st.warning(
        "**Disclaimer**: This is a screening-level tool producing quantitative estimates based on "
        "published climate science and open-source vulnerability functions. Results are indicative, "
        "not insurance-grade. Flood uses precipitation-derived proxies, not hydraulic models. "
        "Consult licensed climate risk specialists for regulatory disclosures (TCFD, CSRD, ISSB S2)."
    )

st.caption(
    "**Scenario source:** [BSR Climate Scenarios 2025](https://www.bsr.org/en/reports/bsr-climate-scenarios-2025) · "
    "[NGFS Phase V (Nov 2023)](https://www.ngfs.net/ngfs-scenarios-portal/) · "
    "[IPCC AR6 (2021)](https://www.ipcc.ch/report/ar6/wg1/) · "
    "[IEA WEO 2023](https://www.iea.org/reports/world-energy-outlook-2023)"
)
