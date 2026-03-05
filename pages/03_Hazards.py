"""
Page 3 – Hazards: Status of hazard data fetch per asset + manual overrides.
"""

import streamlit as st
import pandas as pd
import numpy as np
from engine.asset_model import load_asset_types
from engine.hazard_fetcher import fetch_all_hazards
from engine.impact_functions import get_damage_curve, HAZARD_UNITS
from engine.scenario_model import SCENARIOS
import plotly.graph_objects as go

st.set_page_config(page_title="Hazard Data", page_icon="🌊", layout="wide")

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    total_val = sum(a.replacement_value for a in st.session_state.get("assets", []))
    st.metric("Assets", n)
    st.metric("Total Value", f"£{total_val:,.0f}")

st.title("Hazard Data")

assets = st.session_state.get("assets", [])
if not assets:
    st.warning("No assets defined. Go to the Portfolio page first.")
    st.stop()

selected_scenarios = st.session_state.get("selected_scenarios", ["current_policies"])
asset_types_catalog = load_asset_types()

# ---------------------------------------------------------------------------
# Fetch or load cached hazard data
# ---------------------------------------------------------------------------
if "hazard_data" not in st.session_state:
    st.session_state.hazard_data = {}

if st.button("🔄 Fetch / Refresh Hazard Data", type="primary"):
    progress = st.progress(0, text="Fetching hazard data...")
    total = len(assets)

    scenario_id = selected_scenarios[0] if selected_scenarios else "current_policies"
    ssp = SCENARIOS[scenario_id]["ssp"]

    for i, asset in enumerate(assets):
        hazards = asset_types_catalog.get(asset.asset_type, {}).get(
            "hazards", ["flood", "wind", "wildfire", "heat"]
        )
        data = fetch_all_hazards(
            asset.lat, asset.lon, asset.region, hazards, ssp, "2041_2060"
        )
        st.session_state.hazard_data[asset.id] = data
        progress.progress((i + 1) / total, text=f"Fetched {asset.name}")

    st.success("Hazard data loaded.")

# ---------------------------------------------------------------------------
# Status table
# ---------------------------------------------------------------------------
st.subheader("Data Status")
if st.session_state.hazard_data:
    rows = []
    for asset in assets:
        hdata = st.session_state.hazard_data.get(asset.id, {})
        row = {"Asset": asset.name, "Region": asset.region}
        for hazard in ["flood", "wind", "wildfire", "heat"]:
            if hazard in hdata:
                src = hdata[hazard]["source"]
                row[hazard.capitalize()] = "✅ API" if src == "isimip_api" else "⚠️ Fallback"
            else:
                row[hazard.capitalize()] = "➖ N/A"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.caption("✅ ISIMIP API  |  ⚠️ Built-in regional fallback  |  ➖ Not applicable for asset type")
else:
    st.info("Click 'Fetch Hazard Data' to load data.")

# ---------------------------------------------------------------------------
# Per-asset override panel
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Manual Intensity Overrides")
st.markdown("Override specific hazard intensities for any asset at any return period.")

if "hazard_overrides" not in st.session_state:
    st.session_state.hazard_overrides = {}

asset_names = {a.id: a.name for a in assets}
selected_asset_id = st.selectbox(
    "Select asset to override",
    options=[a.id for a in assets],
    format_func=lambda i: asset_names.get(i, i),
)
selected_asset = next((a for a in assets if a.id == selected_asset_id), None)

if selected_asset:
    hazards_for_asset = asset_types_catalog.get(selected_asset.asset_type, {}).get(
        "hazards", ["flood", "wind", "wildfire", "heat"]
    )
    selected_hazard = st.selectbox("Hazard", hazards_for_asset)
    base_data = st.session_state.hazard_data.get(selected_asset_id, {}).get(selected_hazard)

    if base_data:
        rps = base_data["return_periods"]
        current_intens = base_data["intensities"]
        unit = HAZARD_UNITS.get(selected_hazard, "")

        st.markdown(f"**Intensities for {selected_hazard} ({unit})**")
        override_df = pd.DataFrame({
            "Return Period (yr)": [int(r) for r in rps],
            f"Intensity ({unit})": current_intens,
        })
        edited = st.data_editor(override_df, num_rows="fixed", use_container_width=True)

        if st.button("💾 Save Override"):
            override_key = selected_asset_id
            if override_key not in st.session_state.hazard_overrides:
                st.session_state.hazard_overrides[override_key] = {}
            st.session_state.hazard_overrides[override_key][selected_hazard] = {
                "return_periods": edited["Return Period (yr)"].tolist(),
                "intensities": edited[f"Intensity ({unit})"].tolist(),
                "source": "manual_override",
            }
            # Update main hazard data
            if selected_asset_id not in st.session_state.hazard_data:
                st.session_state.hazard_data[selected_asset_id] = {}
            st.session_state.hazard_data[selected_asset_id][selected_hazard] = (
                st.session_state.hazard_overrides[override_key][selected_hazard]
            )
            st.success("Override saved.")

# ---------------------------------------------------------------------------
# Vulnerability curve viewer
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Vulnerability Curves")
st.markdown("Inspect the damage functions used for each asset type and hazard.")

col1, col2 = st.columns(2)
with col1:
    curve_hazard = st.selectbox("Hazard", ["flood", "wind", "wildfire", "heat"], key="curve_haz")
with col2:
    from engine.asset_model import load_asset_types
    at_catalog = load_asset_types()
    curve_atype = st.selectbox(
        "Asset Type",
        list(at_catalog.keys()),
        format_func=lambda k: at_catalog[k]["label"],
        key="curve_atype",
    )

xs, ys = get_damage_curve(curve_hazard, curve_atype)
if len(xs) > 0:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys * 100,
        mode="lines",
        name="Damage fraction",
        line=dict(color="#e74c3c", width=2),
        fill="tozeroy",
        fillcolor="rgba(231,76,60,0.1)",
    ))
    fig.update_layout(
        xaxis_title=HAZARD_UNITS.get(curve_hazard, "Intensity"),
        yaxis_title="Damage Fraction (%)",
        yaxis=dict(range=[0, 105]),
        height=300,
        margin=dict(l=20, r=20, t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"Sources: HAZUS 6.0, JRC Global DDFs, Syphard et al. 2012, IEA/IPCC cooling curves")
