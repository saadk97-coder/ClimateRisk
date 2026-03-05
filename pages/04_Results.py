"""
Page 4 – Results: EAD summary, asset table, EP curves, scenario comparison, damage timeline.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

from engine.asset_model import Asset
from engine.damage_engine import run_portfolio, AssetResult
from engine.portfolio_aggregator import results_to_dataframe, aggregate_portfolio, scenario_comparison_table
from engine.scenario_model import SCENARIOS

st.set_page_config(page_title="Results", page_icon="📊", layout="wide")

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    total_val = sum(a.replacement_value for a in st.session_state.get("assets", []))
    st.metric("Assets", n)
    st.metric("Total Value", f"£{total_val:,.0f}")
    if "last_run" in st.session_state:
        st.caption(f"Last run: {st.session_state.last_run}")

st.title("Damage Results")

from engine.asset_model import Asset as _Asset
assets: list = [_Asset.from_dict(a) if isinstance(a, dict) else a for a in st.session_state.get("assets", [])]
if not assets:
    st.warning("No assets defined. Go to the Portfolio page first.")
    st.stop()

selected_scenarios = st.session_state.get("selected_scenarios", [])
selected_horizons = st.session_state.get("selected_horizons", [2050])

if not selected_scenarios:
    st.warning("No scenarios selected. Go to the Scenarios page.")
    st.stop()

# ---------------------------------------------------------------------------
# Run calculation
# ---------------------------------------------------------------------------
col_run, col_info = st.columns([2, 5])
with col_run:
    run_btn = st.button("▶ Run Damage Calculation", type="primary", use_container_width=True)
with col_info:
    st.caption(
        f"{len(assets)} assets × {len(selected_scenarios)} scenarios × "
        f"{len(selected_horizons)} time horizons"
    )

if run_btn:
    hazard_overrides = {}
    for asset in assets:
        asset_hdata = st.session_state.get("hazard_data", {}).get(asset.id)
        if asset_hdata:
            hazard_overrides[asset.id] = asset_hdata

    progress_bar = st.progress(0, text="Calculating...")

    def cb(pct):
        progress_bar.progress(pct, text=f"Calculating... {pct*100:.0f}%")

    with st.spinner("Running damage engine..."):
        results: list = run_portfolio(
            assets,
            selected_scenarios,
            selected_horizons,
            hazard_overrides=hazard_overrides if hazard_overrides else None,
            progress_callback=cb,
        )

    st.session_state.results = results
    st.session_state.last_run = datetime.now().strftime("%Y-%m-%d %H:%M")
    progress_bar.empty()
    st.success("Calculation complete.")

results: list = st.session_state.get("results", [])
if not results:
    st.info("Click 'Run Damage Calculation' to generate results.")
    st.stop()

df_results = results_to_dataframe(results)

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
st.divider()
col_sc, col_yr = st.columns(2)
with col_sc:
    view_scenario = st.selectbox(
        "View Scenario",
        selected_scenarios,
        format_func=lambda s: SCENARIOS[s]["label"],
    )
with col_yr:
    view_year = st.selectbox("View Year", selected_horizons)

agg = aggregate_portfolio(results, view_scenario, view_year)

# ---------------------------------------------------------------------------
# Summary metrics
# ---------------------------------------------------------------------------
st.subheader("Portfolio Summary")
m1, m2, m3, m4 = st.columns(4)
total_val = sum(a.replacement_value for a in assets)

m1.metric("Total Portfolio Value", f"£{agg.get('total_value', 0):,.0f}")
m2.metric("Portfolio EAD", f"£{agg.get('portfolio_ead', 0):,.0f}")
m3.metric("EAD as % of Value", f"{agg.get('ead_pct', 0):.2f}%")
m4.metric("Assets Analysed", agg.get("n_assets", 0))

# EAD by hazard breakdown
ead_by_haz = agg.get("ead_by_hazard", {})
if ead_by_haz:
    st.divider()
    haz_cols = st.columns(len(ead_by_haz))
    for i, (haz, ead_val) in enumerate(ead_by_haz.items()):
        haz_cols[i].metric(f"{haz.capitalize()} EAD", f"£{ead_val:,.0f}")

# ---------------------------------------------------------------------------
# Asset-level table
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Asset-Level Results")

asset_df = df_results[
    (df_results["scenario_id"] == view_scenario) & (df_results["year"] == view_year)
].copy()

if not asset_df.empty:
    display_cols = ["asset_name", "asset_value", "total_ead", "total_ead_pct"]
    hazard_ead_cols = [c for c in asset_df.columns if c.startswith("ead_")]
    display_cols += hazard_ead_cols

    display_df = asset_df[display_cols].copy()
    display_df.columns = (
        ["Asset", "Value (£)", "Total EAD (£)", "EAD %"]
        + [c.replace("ead_", "").capitalize() + " EAD (£)" for c in hazard_ead_cols]
    )
    display_df["Value (£)"] = display_df["Value (£)"].apply(lambda x: f"£{x:,.0f}")
    display_df["Total EAD (£)"] = display_df["Total EAD (£)"].apply(lambda x: f"£{x:,.0f}")
    display_df["EAD %"] = display_df["EAD %"].apply(lambda x: f"{x:.3f}%")
    for col in display_df.columns:
        if "EAD (£)" in col and col != "Total EAD (£)":
            display_df[col] = display_df[col].apply(lambda x: f"£{x:,.0f}" if pd.notna(x) else "N/A")

    st.dataframe(display_df, use_container_width=True)

    csv = asset_df.to_csv(index=False).encode()
    st.download_button("⬇️ Export Asset Results (CSV)", csv, "asset_results.csv", "text/csv")

# ---------------------------------------------------------------------------
# Scenario comparison bar chart
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Scenario Comparison")

sc_table = scenario_comparison_table(results, selected_scenarios, selected_horizons)
if not sc_table.empty:
    sc_table["Scenario"] = sc_table["scenario_id"].apply(
        lambda s: SCENARIOS.get(s, {}).get("label", s)
    )
    year_cols = [c for c in sc_table.columns if c.isdigit()]
    sc_melt = sc_table.melt(id_vars=["Scenario"], value_vars=year_cols, var_name="Year", value_name="EAD")

    fig = px.bar(
        sc_melt, x="Scenario", y="EAD", color="Year", barmode="group",
        labels={"EAD": "Portfolio EAD (£)", "Scenario": ""},
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=20, b=80),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# Exceedance Probability curves per asset
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Exceedance Probability Curves")

ep_asset_id = st.selectbox(
    "Select Asset",
    [a.id for a in assets],
    format_func=lambda i: next((a.name for a in assets if a.id == i), i),
    key="ep_asset",
)
ep_hazard = st.selectbox("Hazard", ["flood", "wind", "wildfire", "heat"], key="ep_haz")

asset_result_matches = [
    r for r in results
    if r.asset_id == ep_asset_id
    and r.scenario_id == view_scenario
    and r.year == view_year
]
if asset_result_matches:
    ar = asset_result_matches[0]
    if ep_hazard in ar.hazard_results:
        hr = ar.hazard_results[ep_hazard]
        rps = np.array(hr.return_periods)
        dfs = np.array(hr.damage_fractions)
        asset_val = ar.asset_value

        aep = 1.0 / rps
        losses = dfs * asset_val

        order = np.argsort(aep)
        fig_ep = go.Figure()
        fig_ep.add_trace(go.Scatter(
            x=losses[order], y=aep[order],
            mode="lines+markers",
            name=f"{ep_hazard.capitalize()} losses",
            line=dict(color="#2980b9", width=2),
            fill="tozeroy",
            fillcolor="rgba(41,128,185,0.1)",
        ))
        fig_ep.update_layout(
            xaxis_title="Loss (£)",
            yaxis_title="Annual Exceedance Probability",
            yaxis_type="log",
            height=350,
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig_ep, use_container_width=True)
    else:
        st.info(f"No {ep_hazard} data for this asset.")

# ---------------------------------------------------------------------------
# Damage timeline
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Damage Timeline (EAD by Year)")

timeline_asset_id = st.selectbox(
    "Asset",
    ["_portfolio"] + [a.id for a in assets],
    format_func=lambda i: "Entire Portfolio" if i == "_portfolio" else next(
        (a.name for a in assets if a.id == i), i
    ),
    key="tl_asset",
)

fig_tl = go.Figure()
for sc_id in selected_scenarios:
    ys_vals = []
    for yr in sorted(selected_horizons):
        if timeline_asset_id == "_portfolio":
            agg_yr = aggregate_portfolio(results, sc_id, yr)
            ead_val = agg_yr.get("portfolio_ead", 0.0)
        else:
            matches = [r for r in results if r.asset_id == timeline_asset_id and r.scenario_id == sc_id and r.year == yr]
            ead_val = matches[0].total_ead if matches else 0.0
        ys_vals.append(ead_val)

    fig_tl.add_trace(go.Scatter(
        x=sorted(selected_horizons),
        y=ys_vals,
        mode="lines+markers",
        name=SCENARIOS[sc_id]["label"],
        line=dict(color=SCENARIOS[sc_id].get("color", "#888"), width=2),
    ))

fig_tl.update_layout(
    xaxis_title="Year",
    yaxis_title="Expected Annual Damage (£)",
    height=350,
    margin=dict(l=20, r=20, t=20, b=20),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    hovermode="x unified",
)
st.plotly_chart(fig_tl, use_container_width=True)
