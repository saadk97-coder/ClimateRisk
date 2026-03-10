"""
Page 4 – Results: Annual 2025–2050 EAD, PV discounting, scenario comparison,
EP curves, tail-risk explainer, and xlsx/CSV export.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import io
from datetime import datetime

from engine.asset_model import Asset as _Asset, load_asset_types
from engine.fmt import currency_symbol as _currency_symbol, fmt as _fmt_cur
from engine.damage_engine import run_portfolio
from engine.annual_risk import compute_portfolio_annual_damages, summarise_annual, DEFAULT_YEARS
from engine.portfolio_aggregator import results_to_dataframe, aggregate_portfolio, scenario_comparison_table
from engine.scenario_model import SCENARIOS
from engine.hazard_fetcher import fetch_all_hazards
from engine.export_engine import export_results_xlsx, df_to_xlsx
from engine.risk_scorer import (
    score_portfolio,
    portfolio_climate_var,
    stranded_asset_analysis,
    score_color,
    score_label,
    climate_exposure_score,
)
from engine.insights import results_hotspots, render_insights_html

st.set_page_config(page_title="Results", page_icon="📊", layout="wide")

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    total_val = sum(a.replacement_value for a in st.session_state.get("assets", []))
    st.metric("Assets", n)
    _cur = st.session_state.get("currency_code", "GBP")
    st.metric("Total Value", _fmt_cur(total_val, _cur))
    if "last_run" in st.session_state:
        st.caption(f"Last run: {st.session_state.last_run}")

st.title("Damage Results")

assets: list = [_Asset.from_dict(a) if isinstance(a, dict) else a
                for a in st.session_state.get("assets", [])]
if not assets:
    st.warning("No assets defined. Go to the Portfolio page first.")
    st.stop()

_cur = st.session_state.get("currency_code", "GBP")
_sym = _currency_symbol(_cur)

selected_scenarios = st.session_state.get("selected_scenarios", [])
discount_rate = st.session_state.get("discount_rate", 0.035)
years = list(range(2025, 2051))
asset_types_catalog = load_asset_types()

if not selected_scenarios:
    st.warning("No scenarios selected. Go to the Scenarios page.")
    st.stop()

# ── Run ────────────────────────────────────────────────────────────────────
col_run, col_info = st.columns([2, 5])
with col_run:
    run_btn = st.button("▶ Run Damage Calculation", type="primary", use_container_width=True)
with col_info:
    st.caption(
        f"{len(assets)} assets × {len(selected_scenarios)} scenarios × {len(years)} years (2025–2050) "
        f"| Discount rate: {discount_rate*100:.1f}%"
    )

if run_btn:
    hazard_data_all = st.session_state.get("hazard_data", {})

    # Auto-fetch hazard data if missing for any asset
    assets_needing_data = [a for a in assets if a.id not in hazard_data_all]
    if assets_needing_data:
        with st.status(f"Fetching hazard data for {len(assets_needing_data)} asset(s)…", expanded=False) as fetch_status:
            scenario_id = selected_scenarios[0]
            ssp = SCENARIOS.get(scenario_id, {}).get("ssp", "SSP2-4.5")
            for asset in assets_needing_data:
                hazards = asset_types_catalog.get(asset.asset_type, {}).get(
                    "hazards", ["flood", "wind", "wildfire", "heat"]
                )
                data = fetch_all_hazards(asset.lat, asset.lon, asset.region, hazards, ssp, "2041_2060")
                hazard_data_all[asset.id] = data
                fetch_status.write(f"✅ {asset.name}")
            st.session_state.hazard_data = hazard_data_all
            fetch_status.update(label="Hazard data ready.", state="complete")

    prog = st.progress(0, text="Computing EAD for each asset / scenario / year…")

    def cb(p):
        prog.progress(p, text=f"Calculating… {p*100:.0f}%")

    with st.spinner("Running…"):
        # Annual computation (primary — 2025–2050)
        ann_df = compute_portfolio_annual_damages(
            assets, selected_scenarios,
            hazard_data_all,
            discount_rate, years,
            progress_callback=cb,
        )

        # Coarse horizon results for EP curves / adaptation page
        coarse_years = [2030, 2040, 2050]
        overrides = {aid: hd for aid, hd in hazard_data_all.items()} if hazard_data_all else None
        coarse_results = run_portfolio(
            assets, selected_scenarios, coarse_years,
            hazard_overrides=overrides,
        )

    st.session_state.annual_damages = ann_df
    st.session_state.results = coarse_results
    st.session_state.last_run = datetime.now().strftime("%Y-%m-%d %H:%M")
    prog.empty()
    st.success(f"✅ Calculation complete — {len(ann_df):,} data points across {len(assets)} assets, "
               f"{len(selected_scenarios)} scenarios, {len(years)} years.")

annual_df: pd.DataFrame = st.session_state.get("annual_damages", pd.DataFrame())
coarse_results: list = st.session_state.get("results", [])

if annual_df.empty:
    st.info("Click 'Run Damage Calculation' to generate results.")
    st.stop()

# ── View controls ──────────────────────────────────────────────────────────
st.divider()
view_scenario = st.selectbox(
    "View Scenario",
    selected_scenarios,
    format_func=lambda s: SCENARIOS.get(s, {}).get("label", s),
)

# ── Portfolio summary metrics ──────────────────────────────────────────────
sc_annual = annual_df[annual_df["scenario_id"] == view_scenario]
total_ead_2025 = sc_annual[sc_annual["year"] == 2025]["ead"].sum()
total_ead_2050 = sc_annual[sc_annual["year"] == 2050]["ead"].sum()
total_pv       = sc_annual["pv"].sum()
total_value    = sum(a.replacement_value for a in assets)
mean_annual_ead = sc_annual.groupby("year")["ead"].sum().mean()

st.subheader("Portfolio Summary")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Portfolio Value",    _fmt_cur(total_value, _cur))
m2.metric("EAD (2025 baseline)",      _fmt_cur(total_ead_2025, _cur))
m3.metric("EAD (2050 projected)",     _fmt_cur(total_ead_2050, _cur),
          delta=f"+{(total_ead_2050-total_ead_2025)/max(total_ead_2025,1)*100:.1f}%" if total_ead_2025 > 0 else None)
m4.metric("Total PV Damages 2025–50", _fmt_cur(total_pv, _cur))
m5.metric("EAD as % of Value (2050)", f"{total_ead_2050/total_value*100:.3f}%")

# ── Risk Hotspot Insights ─────────────────────────────────────────────────
_hotspots = results_hotspots(annual_df, assets, view_scenario, year=2050)
if _hotspots:
    st.divider()
    st.subheader("Risk Hotspot Analysis")
    st.caption(
        "Key risk findings for the selected scenario based on modelled 2050 EAD. "
        "Use these insights to prioritise assets for adaptation and due diligence."
    )
    st.markdown(render_insights_html(_hotspots), unsafe_allow_html=True)

# ── Annual EAD Visualizations ──────────────────────────────────────────────
st.divider()
st.subheader("Annual Damages 2025–2050")

tab1, tab2, tab3, tab4 = st.tabs([
    "📈 Scenario Comparison",
    "🏗️ Hazard Breakdown",
    "🏢 Per-Asset Timeline",
    "🗓️ Year Snapshot",
])

# ── TAB 1: Scenario comparison line chart ─────────────────────────────────
with tab1:
    ann_by_year_sc = summarise_annual(annual_df)
    fig_ann = go.Figure()
    for sc_id in selected_scenarios:
        sc_sub = ann_by_year_sc[ann_by_year_sc["scenario_id"] == sc_id]
        sc_label = SCENARIOS.get(sc_id, {}).get("label", sc_id)
        sc_color = SCENARIOS.get(sc_id, {}).get("color", "#888")
        fig_ann.add_trace(go.Scatter(
            x=sc_sub["year"], y=sc_sub["total_ead"],
            mode="lines", name=sc_label,
            line=dict(color=sc_color, width=2.5),
            hovertemplate=f"<b>{sc_label}</b><br>Year: %{{x}}<br>EAD: {_sym}%{{y:,.0f}}<extra></extra>",
        ))
    # Shaded uncertainty band between min/max scenarios
    if len(selected_scenarios) > 1:
        sc_pivot = ann_by_year_sc.pivot(index="year", columns="scenario_id", values="total_ead").fillna(0)
        fig_ann.add_trace(go.Scatter(
            x=sc_pivot.index.tolist() + sc_pivot.index.tolist()[::-1],
            y=sc_pivot.max(axis=1).tolist() + sc_pivot.min(axis=1).tolist()[::-1],
            fill="toself", fillcolor="rgba(136,136,136,0.08)",
            line=dict(color="rgba(0,0,0,0)"), showlegend=False,
            hoverinfo="skip", name="Scenario range",
        ))
    fig_ann.update_layout(
        xaxis_title="Year", yaxis_title=f"Portfolio EAD ({_sym})",
        hovermode="x unified", height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=20, r=20, t=10, b=20),
    )
    st.plotly_chart(fig_ann, use_container_width=True)
    st.caption("EAD = Expected Annual Damage — probability-weighted average loss in each year, discounted to present value on the PV metrics above.")

# ── TAB 2: Stacked area by hazard ─────────────────────────────────────────
with tab2:
    HAZARD_COLORS = {"flood": "#2980b9", "wind": "#8e44ad", "wildfire": "#e67e22", "heat": "#e74c3c"}
    sc_haz_year = (
        annual_df[annual_df["scenario_id"] == view_scenario]
        .groupby(["year", "hazard"])["ead"]
        .sum()
        .reset_index()
    )
    hazards_present = sc_haz_year["hazard"].unique().tolist()

    fig_stack = go.Figure()
    for haz in ["flood", "wind", "wildfire", "heat"]:
        if haz not in hazards_present:
            continue
        haz_data = sc_haz_year[sc_haz_year["hazard"] == haz].sort_values("year")
        fig_stack.add_trace(go.Scatter(
            x=haz_data["year"], y=haz_data["ead"],
            name=haz.capitalize(),
            mode="lines",
            stackgroup="one",
            fillcolor=HAZARD_COLORS.get(haz, "#888") + "cc",
            line=dict(color=HAZARD_COLORS.get(haz, "#888"), width=0.5),
            hovertemplate=f"<b>{haz.capitalize()}</b><br>Year: %{{x}}<br>EAD: {_sym}%{{y:,.0f}}<extra></extra>",
        ))
    fig_stack.update_layout(
        title=f"EAD by Hazard — {SCENARIOS.get(view_scenario, {}).get('label', view_scenario)}",
        xaxis_title="Year", yaxis_title=f"Portfolio EAD ({_sym})",
        hovermode="x unified", height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig_stack, use_container_width=True)

    # PV breakdown pie + bar side by side
    sc_haz_pv = (
        annual_df[annual_df["scenario_id"] == view_scenario]
        .groupby("hazard")["pv"].sum().reset_index()
    )
    sc_haz_pv.columns = ["Hazard", f"PV ({_sym})"]
    sc_haz_pv["Hazard"] = sc_haz_pv["Hazard"].str.capitalize()
    sc_haz_pv = sc_haz_pv.sort_values("PV (£)", ascending=False)
    sc_haz_pv["color"] = sc_haz_pv["Hazard"].str.lower().map(HAZARD_COLORS)

    col_pie, col_bar = st.columns(2)
    with col_pie:
        st.caption("Total PV of Damages 2025–2050 by Hazard")
        fig_pie = px.pie(
            sc_haz_pv, names="Hazard", values=f"PV ({_sym})", hole=0.42,
            color="Hazard",
            color_discrete_map={h.capitalize(): c for h, c in HAZARD_COLORS.items()},
        )
        fig_pie.update_traces(textposition="outside", textinfo="percent+label")
        fig_pie.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)
    with col_bar:
        st.caption(f"Total PV by Hazard ({_sym})")
        fig_hbar = px.bar(
            sc_haz_pv, y="Hazard", x=f"PV ({_sym})", orientation="h",
            color="Hazard",
            color_discrete_map={h.capitalize(): c for h, c in HAZARD_COLORS.items()},
            text="PV (£)",
        )
        fig_hbar.update_traces(texttemplate=f"{_sym}%{{x:,.0f}}", textposition="outside")
        fig_hbar.update_layout(height=300, showlegend=False,
                               margin=dict(l=0, r=60, t=10, b=20),
                               xaxis_title="", yaxis_title="")
        st.plotly_chart(fig_hbar, use_container_width=True)

# ── TAB 3: Per-asset timeline ──────────────────────────────────────────────
with tab3:
    asset_year_ead = (
        annual_df[annual_df["scenario_id"] == view_scenario]
        .groupby(["year", "asset_id", "asset_name"])["ead"]
        .sum()
        .reset_index()
    )
    ASSET_COLORS = px.colors.qualitative.Set2 + px.colors.qualitative.Pastel
    fig_assets = go.Figure()
    asset_ids = asset_year_ead["asset_id"].unique()
    for i, aid in enumerate(asset_ids):
        aname = asset_year_ead[asset_year_ead["asset_id"] == aid]["asset_name"].iloc[0]
        a_data = asset_year_ead[asset_year_ead["asset_id"] == aid].sort_values("year")
        fig_assets.add_trace(go.Scatter(
            x=a_data["year"], y=a_data["ead"],
            name=aname,
            mode="lines+markers" if len(assets) <= 8 else "lines",
            line=dict(color=ASSET_COLORS[i % len(ASSET_COLORS)], width=2),
            marker=dict(size=5),
            hovertemplate=f"<b>{aname}</b><br>Year: %{{x}}<br>EAD: {_sym}%{{y:,.0f}}<extra></extra>",
        ))
    fig_assets.update_layout(
        title=f"EAD per Asset — {SCENARIOS.get(view_scenario, {}).get('label', view_scenario)}",
        xaxis_title="Year", yaxis_title=f"Asset EAD ({_sym})",
        hovermode="x unified", height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=11)),
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig_assets, use_container_width=True)

    # Heatmap: assets × years, EAD%
    if len(assets) >= 2:
        heat_data = (
            annual_df[annual_df["scenario_id"] == view_scenario]
            .groupby(["year", "asset_name"])["ead_pct_value"]
            .sum()
            .unstack(fill_value=0.0)
        )
        fig_hm = go.Figure(go.Heatmap(
            z=heat_data.values,
            x=heat_data.columns.tolist(),
            y=heat_data.index.tolist(),
            colorscale=[[0, "#ffffcc"], [0.33, "#fd8d3c"], [0.67, "#e31a1c"], [1, "#67000d"]],
            hovertemplate="Asset: %{x}<br>Year: %{y}<br>EAD%: %{z:.4f}%<extra></extra>",
            colorbar=dict(title="EAD %", thickness=15),
        ))
        fig_hm.update_layout(
            title="EAD as % of Asset Value — Heatmap",
            xaxis_title="Asset", yaxis_title="Year",
            height=max(300, 18 * len(years)),
            margin=dict(l=20, r=20, t=40, b=80),
            xaxis=dict(tickangle=-35),
        )
        st.plotly_chart(fig_hm, use_container_width=True)

# ── TAB 4: Year snapshot ───────────────────────────────────────────────────
with tab4:
    snap_year = st.slider("Select year", min_value=2025, max_value=2050, value=2040, step=1)
    snap_data = (
        annual_df[(annual_df["scenario_id"] == view_scenario) & (annual_df["year"] == snap_year)]
        .groupby(["asset_id", "asset_name"])
        .agg(total_ead=("ead", "sum"), ead_pct=("ead_pct_value", "sum"))
        .reset_index()
        .sort_values("total_ead", ascending=True)
    )

    if not snap_data.empty:
        fig_snap = px.bar(
            snap_data, y="asset_name", x="total_ead", orientation="h",
            color="ead_pct",
            color_continuous_scale="OrRd",
            labels={"asset_name": "Asset", "total_ead": f"EAD ({_sym})", "ead_pct": "EAD %"},
            text="total_ead",
        )
        fig_snap.update_traces(texttemplate=f"{_sym}%{{x:,.0f}}", textposition="outside")
        fig_snap.update_layout(
            title=f"Asset EAD in {snap_year} — {SCENARIOS.get(view_scenario, {}).get('label', view_scenario)}",
            height=max(300, 40 * len(assets) + 100),
            margin=dict(l=20, r=80, t=40, b=20),
            xaxis_title=f"EAD ({_sym})", yaxis_title="",
            coloraxis_colorbar=dict(title="EAD %"),
        )
        st.plotly_chart(fig_snap, use_container_width=True)

        # Hazard breakdown for selected year
        haz_snap = (
            annual_df[(annual_df["scenario_id"] == view_scenario) & (annual_df["year"] == snap_year)]
            .groupby(["asset_name", "hazard"])["ead"]
            .sum()
            .reset_index()
        )
        fig_haz_snap = px.bar(
            haz_snap, x="asset_name", y="ead", color="hazard",
            color_discrete_map={h: c for h, c in HAZARD_COLORS.items()},
            labels={"asset_name": "Asset", "ead": f"EAD ({_sym})", "hazard": "Hazard"},
            barmode="stack",
        )
        fig_haz_snap.update_layout(
            title=f"EAD by Hazard in {snap_year}",
            height=320, margin=dict(l=20, r=20, t=40, b=80),
            xaxis_tickangle=-35,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_haz_snap, use_container_width=True)

# ── Asset-level table ──────────────────────────────────────────────────────
st.divider()
st.subheader("Asset-Level Results (2050 snapshot)")

if coarse_results:
    df_coarse = results_to_dataframe(coarse_results)
    asset_2050 = df_coarse[
        (df_coarse["scenario_id"] == view_scenario) & (df_coarse["year"] == 2050)
    ].copy()

    # Add PV from annual computation
    pv_by_asset = annual_df[annual_df["scenario_id"] == view_scenario].groupby("asset_id")["pv"].sum().reset_index()
    pv_by_asset.columns = ["asset_id", "total_pv_damages"]
    asset_2050 = asset_2050.merge(pv_by_asset, on="asset_id", how="left")

    disp_cols = ["asset_name", "asset_value", "total_ead", "total_ead_pct", "total_pv_damages"]
    haz_cols = [c for c in asset_2050.columns if c.startswith("ead_")]
    disp_df = asset_2050[disp_cols + haz_cols].copy()

    rename = {
        "asset_name": "Asset", "asset_value": f"Value ({_sym})",
        "total_ead": f"EAD 2050 ({_sym})", "total_ead_pct": "EAD %",
        "total_pv_damages": f"PV Damages 2025–50 ({_sym})",
    }
    for hc in haz_cols:
        rename[hc] = hc.replace("ead_", "").capitalize() + f" EAD ({_sym})"
    disp_df = disp_df.rename(columns=rename)

    fmt_currency = [f"Value ({_sym})", f"EAD 2050 ({_sym})", f"PV Damages 2025–50 ({_sym})"] + \
                   [v for k, v in rename.items() if f"EAD ({_sym})" in v and "EAD 2050" not in v]
    for col in fmt_currency:
        if col in disp_df.columns:
            disp_df[col] = disp_df[col].apply(lambda x: f"{_sym}{x:,.0f}" if pd.notna(x) else "N/A")
    if "EAD %" in disp_df.columns:
        disp_df["EAD %"] = disp_df["EAD %"].apply(lambda x: f"{x:.3f}%" if pd.notna(x) else "N/A")

    st.dataframe(disp_df, use_container_width=True)

# ── Scenario comparison ────────────────────────────────────────────────────
st.divider()
st.subheader("Scenario Comparison — Total PV of Damages 2025–2050")

sc_pv_rows = []
for sc_id in selected_scenarios:
    sc_sub = annual_df[annual_df["scenario_id"] == sc_id]
    sc_pv_rows.append({
        "Scenario": SCENARIOS.get(sc_id, {}).get("label", sc_id),
        f"Total PV ({_sym})": sc_sub["pv"].sum(),
        f"Mean Annual EAD ({_sym})": sc_sub.groupby("year")["ead"].sum().mean() if not sc_sub.empty else 0,
        f"EAD 2050 ({_sym})": sc_sub[sc_sub["year"] == 2050]["ead"].sum(),
        "color": SCENARIOS.get(sc_id, {}).get("color", "#888"),
    })
sc_pv_df = pd.DataFrame(sc_pv_rows)

fig_sc = px.bar(sc_pv_df, x="Scenario", y=f"Total PV ({_sym})",
                color="Scenario",
                color_discrete_map={r["Scenario"]: r["color"] for r in sc_pv_rows},
                text=f"Total PV ({_sym})")
fig_sc.update_traces(texttemplate=f"{_sym}%{{y:,.0f}}", textposition="outside")
fig_sc.update_layout(height=340, showlegend=False,
                     margin=dict(l=20, r=20, t=20, b=100),
                     xaxis_tickangle=-20, yaxis_title=f"Total PV of Damages ({_sym})")
st.plotly_chart(fig_sc, use_container_width=True)

# ── EP curve ──────────────────────────────────────────────────────────────
if coarse_results:
    st.divider()
    st.subheader("Exceedance Probability Curve")
    col_a, col_b = st.columns(2)
    with col_a:
        ep_asset_id = st.selectbox("Asset", [a.id for a in assets],
                                   format_func=lambda i: next((a.name for a in assets if a.id == i), i))
    with col_b:
        ep_hazard = st.selectbox("Hazard", ["flood", "wind", "wildfire", "heat"])

    ep_matches = [r for r in coarse_results
                  if r.asset_id == ep_asset_id and r.scenario_id == view_scenario and r.year == 2050]
    if ep_matches and ep_hazard in ep_matches[0].hazard_results:
        hr = ep_matches[0].hazard_results[ep_hazard]
        rps = np.array(hr.return_periods)
        dfs = np.array(hr.damage_fractions)
        aep = 1.0 / rps
        losses = dfs * ep_matches[0].asset_value
        order = np.argsort(aep)

        fig_ep = go.Figure()
        fig_ep.add_trace(go.Scatter(
            x=losses[order], y=aep[order],
            mode="lines+markers",
            line=dict(color="#2980b9", width=2),
            fill="tozeroy", fillcolor="rgba(41,128,185,0.1)",
            hovertemplate=f"Loss: {_sym}%{{x:,.0f}}<br>AEP: %{{y:.4f}}<extra></extra>",
        ))
        fig_ep.update_layout(
            xaxis_title=f"Loss ({_sym})", yaxis_title="Annual Exceedance Probability",
            yaxis_type="log", height=320, margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig_ep, use_container_width=True)

        with st.expander("📖 Understanding this chart — Corporate Guide to Tail Risk & Return Periods"):
            st.markdown("""
**What is EAD (Expected Annual Damage)?**
EAD is the probability-weighted average annual loss — the "fair value" of climate damage in any given year.
If your EAD is £50,000, you won't lose exactly £50,000 every year; in most years you lose nothing, but occasionally a severe event causes much larger losses. The EAD is the long-run annual average.

**What is a Return Period?**
A "1-in-100-year event" has a **1% annual probability** — not that it happens once a century.
With climate change, these probabilities are shifting: a former 1-in-100-year flood may become a 1-in-50-year event by 2050.

**What is Tail Risk (TVaR / CVaR)?**
The EP curve shows the full range of possible losses:
- **95th percentile (1-in-20)**: a bad year, plausibly within a business planning horizon
- **99th percentile (1-in-100)**: severe but possible; relevant for credit/insurance stress tests
- **Tail Value at Risk (TVaR)**: average of all losses *above* the 95th or 99th percentile

For corporate strategic planning:
- Use **EAD** for annual budgeting and insurance procurement
- Use **99th percentile loss** for balance sheet stress tests and M&A due diligence
- Use **TVaR** for TCFD physical risk disclosure and board risk appetite frameworks

**TCFD Integration**
These metrics map directly to TCFD physical risk disclosure:
- *Chronic risk*: EAD + total PV damages (this page)
- *Acute risk*: return-period losses (EP curve above)
- *Scenario analysis*: current / transition / disorderly scenarios
- *Financial quantification*: climate-adjusted NPV (see DCF page)

*Reference: [TCFD Final Report (2017)](https://www.fsb-tcfd.org/recommendations/) | [BSR Climate Strategy](https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf)*
            """)

# ── XLSX / CSV Export ──────────────────────────────────────────────────────
st.divider()
st.subheader("Download Results")

col_e1, col_e2, col_e3 = st.columns(3)

with col_e1:
    if not annual_df.empty:
        try:
            xlsx_bytes = export_results_xlsx(
                asset_results_df=df_coarse if coarse_results else pd.DataFrame(),
                annual_damages_df=annual_df,
                portfolio_summary={
                    f"Total Portfolio Value ({_sym})": _fmt_cur(total_value, _cur),
                    "Scenarios analysed": ", ".join(selected_scenarios),
                    "Analysis period": "2025–2050 (annual)",
                    "Discount rate": f"{discount_rate*100:.1f}%",
                    "Run date": st.session_state.get("last_run", ""),
                },
                scenarios=selected_scenarios,
                metadata={"Run": st.session_state.get("last_run", ""),
                          "Provider": st.session_state.get("scenario_provider", "NGFS Phase V")},
            )
            st.download_button("⬇️ Full Results (.xlsx)", data=xlsx_bytes,
                               file_name="climate_risk_results.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        except Exception as e:
            st.warning(f"XLSX export unavailable: {e}")

with col_e2:
    if not annual_df.empty:
        csv_bytes = annual_df.to_csv(index=False).encode()
        st.download_button("⬇️ Annual Damages (.csv)", data=csv_bytes,
                           file_name="annual_damages.csv", mime="text/csv")

with col_e3:
    if coarse_results:
        df_c = results_to_dataframe(coarse_results)
        csv2 = df_c.to_csv(index=False).encode()
        st.download_button("⬇️ Asset Results (.csv)", data=csv2,
                           file_name="asset_results.csv", mime="text/csv")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — Climate Exposure Scores
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("Climate Exposure Scores")

# BSR colour palette
_BSR = dict(
    primary="#F4721A",
    navy="#1A3A5C",
    teal="#2A9D8F",
    amber="#E9C46A",
    danger="#C94040",
    purple="#7B2D8B",
)
_HAZARD_COLORS_BSR = dict(
    flood="#1A3A5C",
    wind="#2A9D8F",
    wildfire="#F4721A",
    heat="#C94040",
    water_stress="#E9C46A",
)

# ── Portfolio-level Physical Climate VaR metric ────────────────────────────
_pf_var = portfolio_climate_var(annual_df, assets, year=2050, scenario_id=view_scenario)
_port_var_pct  = _pf_var["portfolio_var_pct"]
_port_ead_total = _pf_var["portfolio_ead"]

_var_col, _info_col = st.columns([2, 5])
with _var_col:
    st.metric(
        label="Portfolio Physical Climate VaR (2050)",
        value=f"{_port_var_pct:.3f}%",
        help=(
            "Expected Annual Damage as a percentage of total portfolio replacement value "
            "under the selected scenario at 2050. Follows TCFD / MSCI Climate VaR framing."
        ),
    )
    st.caption(
        f"Portfolio EAD 2050: {_fmt_cur(_port_ead_total, _cur)} "
        f"| Scenario: {SCENARIOS.get(view_scenario, {}).get('label', view_scenario)}"
    )
with _info_col:
    with st.popover("ℹ️ How scores are calculated"):
        st.markdown("""
**Climate Exposure Score — Methodology**

Each asset × hazard cell is scored on a **1–10 scale** derived from the asset's
Physical Climate VaR (EAD ÷ replacement value × 100%).

A log-normalised transformation is applied so that the full score range is used
even when a few assets dominate portfolio EAD:

```
raw_pct = EAD / replacement_value × 100
score   = 1 + 9 × log(1 + raw_pct / midpoint) / log(1 + max_pct / midpoint)
```

**Hazard-specific calibration thresholds** (score 5.5 midpoint / score 10 ceiling):

| Hazard | Midpoint EAD% | Max EAD% |
|---|---|---|
| Flood | 0.5% | 5.0% |
| Wind | 0.3% | 3.0% |
| Wildfire | 0.4% | 4.0% |
| Heat | 0.2% | 2.0% |
| Water Stress | 0.15% | 1.5% |

Thresholds are calibrated to the platform's HAZUS/JRC/Syphard vulnerability curve library.

**Score bands:** Very Low (<2.5) · Low (<4.0) · Moderate (<5.5) · Elevated (<7.0) · High (<8.5) · Very High (≤10)
        """)

# ── Heatmap-style table: assets × hazards ─────────────────────────────────
_score_df = score_portfolio(annual_df, assets, year=2050, scenario_id=view_scenario)

if not _score_df.empty:
    _HAZARDS_ORDER = ["flood", "wind", "wildfire", "heat", "water_stress"]

    # Pivot: rows = asset names, columns = hazards, values = score
    _pivot_scores = (
        _score_df
        .pivot_table(index="name", columns="hazard", values="score", aggfunc="mean")
        .reindex(columns=[h for h in _HAZARDS_ORDER if h in _score_df["hazard"].unique()])
    )

    # Rename columns for display
    _col_labels = {
        "flood": "Flood",
        "wind": "Wind",
        "wildfire": "Wildfire",
        "heat": "Heat",
        "water_stress": "Water Stress",
    }
    _pivot_display = _pivot_scores.copy()
    _pivot_display.columns = [_col_labels.get(c, c) for c in _pivot_display.columns]
    _pivot_display.index.name = "Asset"

    def _colour_score_cell(val):
        """Return CSS background-color style string for a score value."""
        if pd.isna(val):
            return ""
        color = score_color(float(val))
        # Choose white or dark text based on background luminance
        dark_bgs = {"#1A3A5C", "#C94040", "#7B2D8B"}
        text_color = "#FFFFFF" if color in dark_bgs else "#1A1A1A"
        return f"background-color: {color}; color: {text_color}; font-weight: 600; text-align: center;"

    def _fmt_score(val):
        return f"{val:.1f}" if pd.notna(val) else "—"

    _styled = (
        _pivot_display
        .style
        .applymap(_colour_score_cell)
        .format(_fmt_score)
    )

    st.caption(
        f"Scores 1–10 per asset × hazard at 2050 under "
        f"{SCENARIOS.get(view_scenario, {}).get('label', view_scenario)}. "
        "Colour: teal=Very Low · green=Low · amber=Moderate · orange=Elevated · red=High · purple=Very High"
    )
    st.dataframe(_styled, use_container_width=True)
else:
    st.info("Run the damage calculation to generate exposure scores.")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Physical Climate VaR Waterfall
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("Physical Climate VaR — Asset Contribution")

_var_by_asset = _pf_var.get("var_by_asset", {})

if _var_by_asset:
    # Build sorted dataframe for waterfall (horizontal bar)
    _asset_name_map = {a.id: a.name for a in assets}
    _var_rows = []
    for _aid, _vdata in _var_by_asset.items():
        _a_ead  = _vdata["ead"]
        _a_var  = _vdata["var_pct"]
        # Use composite score (total EAD across hazards) for colour
        _asset_obj = next((a for a in assets if a.id == _aid), None)
        _a_val = _asset_obj.replacement_value if _asset_obj else 1.0
        _a_score = climate_exposure_score(_a_ead, _a_val, "default")
        _var_rows.append({
            "asset_id":   _aid,
            "asset_name": _asset_name_map.get(_aid, _aid),
            "ead":        _a_ead,
            "var_pct":    _a_var,
            "score":      _a_score,
            "bar_color":  score_color(_a_score),
        })

    _var_asset_df = (
        pd.DataFrame(_var_rows)
        .sort_values("var_pct", ascending=True)   # ascending so largest bar is at top
    )

    _fig_waterfall = go.Figure(go.Bar(
        x=_var_asset_df["var_pct"],
        y=_var_asset_df["asset_name"],
        orientation="h",
        marker_color=_var_asset_df["bar_color"].tolist(),
        text=[f"{v:.3f}%" for v in _var_asset_df["var_pct"]],
        textposition="outside",
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Climate VaR: %{x:.3f}%<br>"
            f"EAD 2050: {_sym}%{{customdata:,.0f}}"
            "<extra></extra>"
        ),
        customdata=_var_asset_df["ead"],
    ))
    _fig_waterfall.update_layout(
        title=f"Physical Climate VaR by Asset (2050) — "
              f"{SCENARIOS.get(view_scenario, {}).get('label', view_scenario)}",
        xaxis_title="Physical Climate VaR (%)",
        yaxis_title="",
        height=max(320, 40 * len(_var_rows) + 100),
        margin=dict(l=20, r=90, t=50, b=30),
        xaxis=dict(ticksuffix="%"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    # Reference line at portfolio mean
    _mean_var = float(np.mean([r["var_pct"] for r in _var_rows]))
    _fig_waterfall.add_vline(
        x=_mean_var,
        line_dash="dot",
        line_color=_BSR["navy"],
        annotation_text=f"Portfolio avg {_mean_var:.3f}%",
        annotation_position="top right",
        annotation_font_color=_BSR["navy"],
    )
    st.plotly_chart(_fig_waterfall, use_container_width=True)
    st.caption(
        "Physical Climate VaR = asset EAD as % of its own replacement value. "
        "Colour follows the same exposure score bands as the heatmap above. "
        "Dashed line = portfolio mean."
    )
else:
    st.info("Run the damage calculation to see the VaR waterfall.")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — Stranded Asset Analysis
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("Stranded Asset Analysis")

_sa_col1, _sa_col2 = st.columns([3, 1])
with _sa_col1:
    _stranded_threshold = st.slider(
        "Cumulative PV damage threshold (% of asset value)",
        min_value=10,
        max_value=30,
        value=15,
        step=1,
        help=(
            "An asset is flagged as 'stranded' when its total discounted physical climate "
            "costs over 2025–2050 exceed this percentage of its replacement value."
        ),
    )
with _sa_col2:
    with st.popover("ℹ️ What is a stranded asset?"):
        st.markdown("""
**Stranded Asset — Definition & Methodology**

An asset is flagged as **stranded** when cumulative discounted physical climate
costs over the analysis period (2025–2050) exceed the selected threshold percentage
of its replacement value.

**Example:** A warehouse worth £10M with a threshold of 15% is flagged if the
present value of all projected climate damage over 26 years exceeds £1.5M.

This signals that the asset may be **financially impaired by climate damage before
the end of its economic life** — analogous to an early write-down driven by
physical climate risk rather than technological or policy obsolescence.

**Methodology draws on:**
- TCFD Physical Risk framing (2017 Final Report, pp. 10–12)
- IPCC AR6 Working Group II — Chapter 16 (Loss & Damage)
- Insurance industry total-loss thresholds (typically 10–20% of insured value
  triggers partial or total write-off in commercial property underwriting)

The **acute breach year** column shows the earliest year in which a single year's
EAD exceeds 5% of asset value — a signal of acute (event-driven) impairment risk.
        """)

_stranded_df = stranded_asset_analysis(
    annual_df, assets,
    scenario_id=view_scenario,
    threshold_pct=float(_stranded_threshold),
)

if not _stranded_df.empty:
    _n_flagged = int(_stranded_df["stranded_flag"].sum())

    _flag_col, _total_col = st.columns(2)
    _flag_col.metric("Assets Flagged as Stranded", f"{_n_flagged} / {len(_stranded_df)}")
    _total_col.metric(
        "Combined PV Exposure (flagged)",
        _fmt_cur(_stranded_df[_stranded_df["stranded_flag"]]["cumulative_pv"].sum(), _cur)
        if _n_flagged > 0 else _fmt_cur(0, _cur),
    )

    # Display columns
    _sa_display = _stranded_df[[
        "name", "asset_type", "region", "value",
        "cumulative_pv", "pv_as_pct_of_value",
        "stranded_flag", "acute_breach_year",
    ]].copy()

    _sa_display = _sa_display.rename(columns={
        "name":               "Asset",
        "asset_type":         "Type",
        "region":             "Region",
        "value":              f"Replacement Value ({_sym})",
        "cumulative_pv":      f"Cumulative PV Damages ({_sym})",
        "pv_as_pct_of_value": "PV as % of Value",
        "stranded_flag":      "Stranded?",
        "acute_breach_year":  "Acute Breach Year",
    })

    def _style_stranded_rows(row):
        """Apply red background to stranded rows."""
        if row["Stranded?"]:
            return [f"background-color: {_BSR['danger']}22; color: #7a0000; font-weight: 600;"] * len(row)
        return [""] * len(row)

    _sa_styled = (
        _sa_display
        .style
        .apply(_style_stranded_rows, axis=1)
        .format({
            f"Replacement Value ({_sym})":   f"{_sym}{{:,.0f}}",
            f"Cumulative PV Damages ({_sym})": f"{_sym}{{:,.0f}}",
            "PV as % of Value":        "{:.2f}%",
            "Acute Breach Year":       lambda v: str(int(v)) if pd.notna(v) else "—",
        })
    )

    st.dataframe(_sa_styled, use_container_width=True)
    st.caption(
        f"Threshold: cumulative PV damages ≥ {_stranded_threshold}% of replacement value. "
        f"Scenario: {SCENARIOS.get(view_scenario, {}).get('label', view_scenario)}. "
        "Red rows indicate assets at risk of financial impairment by climate damage."
    )
else:
    st.info("Run the damage calculation to perform stranded asset analysis.")

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — Historical Reference Panel
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("Historical Context")

HISTORICAL_NAT_CAT = [
    {"region": "EUR", "period": "2000–2023", "events": "Flood, Windstorm",          "insured_bn_usd": 23,  "total_bn_usd": 58,  "source": "Munich Re NatCatSERVICE 2024"},
    {"region": "USA", "period": "2000–2023", "events": "Hurricane, Flood, Wildfire", "insured_bn_usd": 120, "total_bn_usd": 210, "source": "Munich Re NatCatSERVICE 2024"},
    {"region": "CHN", "period": "2000–2023", "events": "Flood, Typhoon",             "insured_bn_usd": 8,   "total_bn_usd": 65,  "source": "Munich Re NatCatSERVICE 2024"},
    {"region": "IND", "period": "2000–2023", "events": "Flood, Cyclone",             "insured_bn_usd": 3,   "total_bn_usd": 38,  "source": "Munich Re NatCatSERVICE 2024"},
    {"region": "AUS", "period": "2000–2023", "events": "Flood, Wildfire, Cyclone",   "insured_bn_usd": 12,  "total_bn_usd": 20,  "source": "Munich Re NatCatSERVICE 2024"},
    {"region": "BRA", "period": "2000–2023", "events": "Flood, Drought",             "insured_bn_usd": 2,   "total_bn_usd": 22,  "source": "Munich Re NatCatSERVICE 2024"},
    {"region": "MEA", "period": "2000–2023", "events": "Drought, Flood",             "insured_bn_usd": 1,   "total_bn_usd": 18,  "source": "Munich Re NatCatSERVICE 2024"},
]

# Map asset regions to historical reference region codes
_REGION_MAP = {
    "GBR": "EUR", "FRA": "EUR", "NLD": "EUR", "DEU": "EUR",
    "ITA": "EUR", "ESP": "EUR", "CHE": "EUR", "SWE": "EUR",
    "NOR": "EUR", "DNK": "EUR", "POL": "EUR", "AUT": "EUR",
    "BEL": "EUR", "PRT": "EUR", "FIN": "EUR", "IRL": "EUR",
    "USA": "USA", "CAN": "USA",
    "CHN": "CHN",
    "IND": "IND", "PAK": "IND", "BGD": "IND",
    "AUS": "AUS", "NZL": "AUS",
    "BRA": "BRA", "ARG": "BRA", "CHL": "BRA", "COL": "BRA",
    "SAU": "MEA", "ARE": "MEA", "QAT": "MEA", "KWT": "MEA",
    "EGY": "MEA", "IRN": "MEA", "IRQ": "MEA", "ZAF": "MEA",
}

# Detect which reference regions the user's portfolio touches
_portfolio_regions = {a.region for a in assets}
_reference_regions = {_REGION_MAP.get(r, None) for r in _portfolio_regions} - {None}

_hist_df = pd.DataFrame(HISTORICAL_NAT_CAT).rename(columns={
    "region":         "Region",
    "period":         "Period",
    "events":         "Event Types",
    "insured_bn_usd": "Avg Annual Insured Losses (USD bn)",
    "total_bn_usd":   "Avg Annual Total Losses (USD bn)",
    "source":         "Source",
})

def _highlight_portfolio_regions(row):
    """Highlight rows whose region matches the user's portfolio."""
    if row["Region"] in _reference_regions:
        return [f"background-color: {_BSR['teal']}33; font-weight: 600;"] * len(row)
    return [""] * len(row)

_hist_styled = (
    _hist_df
    .style
    .apply(_highlight_portfolio_regions, axis=1)
    .format({
        "Avg Annual Insured Losses (USD bn)": "${:,.0f}bn",
        "Avg Annual Total Losses (USD bn)":   "${:,.0f}bn",
    })
)

st.dataframe(_hist_styled, use_container_width=True)

_matched_label = ", ".join(sorted(_reference_regions)) if _reference_regions else "None matched"
st.caption(
    f"Highlighted rows correspond to your portfolio's regions ({_matched_label}). "
    "Historical loss data from Munich Re NatCatSERVICE public summaries and EM-DAT "
    "(Centre for Research on the Epidemiology of Disasters). "
    "These are observed losses 1990–2023 for context against forward-looking projections."
)
