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
        "Hazard sources: ISIMIP3b / Built-in regional baselines\n"
        "Vulnerability: HAZUS 6.0, JRC DDFs, Syphard et al.\n"
        "Scenarios: NGFS Phase 4 / IPCC AR6"
    )

# ---------------------------------------------------------------------------
# Home page
# ---------------------------------------------------------------------------
st.title("🌍 Climate Risk Financial Quantification Platform")

st.markdown("""
Welcome to the **Climate Risk Financial Quantification Platform** — an insurance-quality tool
that translates physical climate hazard exposure into asset-level financial damages.

### How it works

| Step | Page | Description |
|------|------|-------------|
| 1 | **Portfolio** | Upload your assets via CSV or add them manually |
| 2 | **Scenarios** | Select NGFS climate scenarios and time horizons |
| 3 | **Hazards** | Fetch hazard data from ISIMIP API or use built-in baselines |
| 4 | **Results** | View EAD, EP curves, scenario comparison, and damage timelines |
| 5 | **Map** | Explore assets on an interactive risk map |
| 6 | **Adaptation** | Evaluate cost-benefit of adaptation measures |

### Key Features
- 🌊 **Multi-hazard**: Flood, Wind, Wildfire, Heat stress
- 🌡️ **5 NGFS scenarios**: Net Zero 2050 → Current Policies
- 📅 **4 time horizons**: 2030, 2040, 2050, 2080
- 📐 **Insurance-grade EAD**: Trapezoidal integration over exceedance probability curves
- 🛡️ **Adaptation NPV**: Cost-benefit analysis for 19 adaptation measures
- 🗺️ **Interactive map**: Assets coloured by risk level
- 📤 **Export**: CSV/Excel download of all results

### Vulnerability Curve Sources
- **Flood**: HAZUS 6.0 depth-damage functions (25 occupancy types) + JRC Global DDFs
- **Wind**: HAZUS MH wind fragility functions
- **Wildfire**: Syphard et al. 2012 + HAZUS wildfire functions
- **Heat**: IEA/IPCC cooling cost escalation + ILO productivity loss curves

---
Navigate using the **sidebar pages** to get started.
""")

col1, col2, col3 = st.columns(3)
with col1:
    st.info("**Quick Start**: Go to Portfolio → upload the sample CSV template → Scenarios → Hazards → Results")
with col2:
    st.success("**Data Source**: ISIMIP3b API with automatic fallback to built-in regional baselines")
with col3:
    st.warning("**Note**: Results are indicative. Consult licensed climate risk specialists for regulatory use.")
