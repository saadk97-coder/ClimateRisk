"""
Climate Risk Financial Quantification Platform
Insurance-quality, non-coder-friendly climate risk tool.

Run with: streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Climate Risk Platform",
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

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.image(
        "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e9/Notna_Mapa_Sveta.svg/320px-Notna_Mapa_Sveta.svg.png",
        use_container_width=True,
    )
    st.header("📊 Portfolio Summary")
    n = len(st.session_state.assets)
    total_val = sum(a.replacement_value for a in st.session_state.assets)
    st.metric("Assets", n)
    st.metric("Total Value", f"£{total_val:,.0f}")

    if st.session_state.results:
        from engine.portfolio_aggregator import aggregate_portfolio
        sc = st.session_state.selected_scenarios[0] if st.session_state.selected_scenarios else None
        yr = st.session_state.selected_horizons[0] if st.session_state.selected_horizons else None
        if sc and yr:
            agg = aggregate_portfolio(st.session_state.results, sc, yr)
            st.metric("Portfolio EAD", f"£{agg.get('portfolio_ead', 0):,.0f}")
            st.metric("EAD % of Value", f"{agg.get('ead_pct', 0):.2f}%")

    if "last_run" in st.session_state:
        st.caption(f"Last run: {st.session_state.last_run}")

    st.divider()
    st.caption(
        "Climate Risk Financial Quantification Platform\n\n"
        "Hazard sources: ISIMIP3b / NASA NEX / CHELSA / LOCA2\n"
        "Vulnerability: HAZUS 6.0, JRC DDFs, Syphard et al.\n"
        "Scenarios: NGFS Phase V / IEA WEO 2023 / IPCC AR6"
    )

# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------
st.title("🌍 Climate Risk Financial Quantification Platform")

st.markdown("""
Welcome to the **Climate Risk Financial Quantification Platform** — a professional-grade tool
that translates physical climate hazard exposure into asset-level financial damages with full
source transparency, audit trails, and TCFD-aligned financial outputs.

### Workflow

| Step | Page | Description |
|------|------|-------------|
| 1 | **Portfolio** | Upload assets via CSV or add them manually |
| 2 | **Scenarios** | Select scenarios — NGFS Phase V, IEA WEO 2023, or IPCC AR6 |
| 3 | **Hazards** | Fetch hazard data (ISIMIP3b, NASA NEX, CHELSA, LOCA2, fallback) |
| 4 | **Results** | Annual 2025–2050 EAD, EP curves, tail risk, scenario comparison |
| 5 | **Map** | Interactive risk map with satellite imagery & building footprints |
| 6 | **Adaptation** | Cost-benefit analysis for 20+ adaptation measures with citations |
| 7 | **DCF** | Climate-adjusted NPV valuation (BSR framework) |
| 8 | **Audit** | Step-by-step calculation trace for any asset/scenario/year |
| 9 | **Vulnerability** | View, edit, and audit all damage functions with source citations |

### Key Features
- 🌊 **Multi-hazard**: Flood, Wind, Wildfire, Heat stress
- 🌡️ **Multi-provider scenarios**: NGFS Phase V (6) · IEA WEO 2023 (3) · IPCC AR6 (5)
- 📅 **Annual 2025–2050 timeline**: per-year EAD discounted to present value
- 📐 **Insurance-grade EAD**: Trapezoidal integration over exceedance probability curves
- 💹 **Climate-adjusted DCF**: BSR framework — scenario-weighted NPV impairment
- 🔍 **Full audit trail**: hazard source → warming → multiplier → curve → EAD → PV
- 📐 **Vulnerability editor**: HAZUS/JRC/ILO curves — view, edit, compare, export
- 🛡️ **Adaptation CBR**: 20+ measures with FEMA/EA/IBHS source citations
- 🛰️ **Satellite imagery**: ESRI WorldImagery + OSM building footprints
- 📤 **XLSX export**: Formatted multi-sheet workbooks for all outputs

### Vulnerability Curve Sources
- **Flood**: HAZUS 6.0 (FEMA 2022) · JRC Global DDFs (Huizinga et al. 2017)
- **Wind**: HAZUS MH Hurricane Technical Manual (FEMA 2012) · IBHS FORTIFIED
- **Wildfire**: Syphard et al. (2012) Ecosphere · HAZUS Wildfire
- **Heat**: IEA Future of Cooling (2018) · ILO (2019) · Zhao et al. (2021) Nature

---
Navigate using the **sidebar pages** to get started.
""")

col1, col2, col3 = st.columns(3)
with col1:
    st.info("**Quick Start**: Portfolio → Scenarios → Hazards → Results → DCF")
with col2:
    st.success("**Data**: ISIMIP3b · NASA NEX · CHELSA · LOCA2 · Built-in regional baselines")
with col3:
    st.warning("**Note**: Results are indicative estimates. Consult licensed climate risk specialists for regulatory filings.")
