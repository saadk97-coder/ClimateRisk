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
from engine.damage_engine import run_portfolio
from engine.annual_risk import compute_portfolio_annual_damages, summarise_annual, DEFAULT_YEARS
from engine.portfolio_aggregator import results_to_dataframe, aggregate_portfolio, scenario_comparison_table
from engine.scenario_model import SCENARIOS
from engine.hazard_fetcher import fetch_all_hazards
from engine.export_engine import export_results_xlsx, df_to_xlsx

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

assets: list = [_Asset.from_dict(a) if isinstance(a, dict) else a
                for a in st.session_state.get("assets", [])]
if not assets:
    st.warning("No assets defined. Go to the Portfolio page first.")
    st.stop()

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
m1.metric("Total Portfolio Value",    f"£{total_value:,.0f}")
m2.metric("EAD (2025 baseline)",      f"£{total_ead_2025:,.0f}")
m3.metric("EAD (2050 projected)",     f"£{total_ead_2050:,.0f}",
          delta=f"+{(total_ead_2050-total_ead_2025)/max(total_ead_2025,1)*100:.1f}%" if total_ead_2025 > 0 else None)
m4.metric("Total PV Damages 2025–50", f"£{total_pv:,.0f}")
m5.metric("EAD as % of Value (2050)", f"{total_ead_2050/total_value*100:.3f}%")

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
            hovertemplate=f"<b>{sc_label}</b><br>Year: %{{x}}<br>EAD: £%{{y:,.0f}}<extra></extra>",
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
        xaxis_title="Year", yaxis_title="Portfolio EAD (£)",
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
            hovertemplate=f"<b>{haz.capitalize()}</b><br>Year: %{{x}}<br>EAD: £%{{y:,.0f}}<extra></extra>",
        ))
    fig_stack.update_layout(
        title=f"EAD by Hazard — {SCENARIOS.get(view_scenario, {}).get('label', view_scenario)}",
        xaxis_title="Year", yaxis_title="Portfolio EAD (£)",
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
    sc_haz_pv.columns = ["Hazard", "PV (£)"]
    sc_haz_pv["Hazard"] = sc_haz_pv["Hazard"].str.capitalize()
    sc_haz_pv = sc_haz_pv.sort_values("PV (£)", ascending=False)
    sc_haz_pv["color"] = sc_haz_pv["Hazard"].str.lower().map(HAZARD_COLORS)

    col_pie, col_bar = st.columns(2)
    with col_pie:
        st.caption("Total PV of Damages 2025–2050 by Hazard")
        fig_pie = px.pie(
            sc_haz_pv, names="Hazard", values="PV (£)", hole=0.42,
            color="Hazard",
            color_discrete_map={h.capitalize(): c for h, c in HAZARD_COLORS.items()},
        )
        fig_pie.update_traces(textposition="outside", textinfo="percent+label")
        fig_pie.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)
    with col_bar:
        st.caption("Total PV by Hazard (£)")
        fig_hbar = px.bar(
            sc_haz_pv, y="Hazard", x="PV (£)", orientation="h",
            color="Hazard",
            color_discrete_map={h.capitalize(): c for h, c in HAZARD_COLORS.items()},
            text="PV (£)",
        )
        fig_hbar.update_traces(texttemplate="£%{x:,.0f}", textposition="outside")
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
            hovertemplate=f"<b>{aname}</b><br>Year: %{{x}}<br>EAD: £%{{y:,.0f}}<extra></extra>",
        ))
    fig_assets.update_layout(
        title=f"EAD per Asset — {SCENARIOS.get(view_scenario, {}).get('label', view_scenario)}",
        xaxis_title="Year", yaxis_title="Asset EAD (£)",
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
            labels={"asset_name": "Asset", "total_ead": "EAD (£)", "ead_pct": "EAD %"},
            text="total_ead",
        )
        fig_snap.update_traces(texttemplate="£%{x:,.0f}", textposition="outside")
        fig_snap.update_layout(
            title=f"Asset EAD in {snap_year} — {SCENARIOS.get(view_scenario, {}).get('label', view_scenario)}",
            height=max(300, 40 * len(assets) + 100),
            margin=dict(l=20, r=80, t=40, b=20),
            xaxis_title="EAD (£)", yaxis_title="",
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
            labels={"asset_name": "Asset", "ead": "EAD (£)", "hazard": "Hazard"},
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
        "asset_name": "Asset", "asset_value": "Value (£)",
        "total_ead": "EAD 2050 (£)", "total_ead_pct": "EAD %",
        "total_pv_damages": "PV Damages 2025–50 (£)",
    }
    for hc in haz_cols:
        rename[hc] = hc.replace("ead_", "").capitalize() + " EAD (£)"
    disp_df = disp_df.rename(columns=rename)

    fmt_currency = ["Value (£)", "EAD 2050 (£)", "PV Damages 2025–50 (£)"] + \
                   [v for k, v in rename.items() if "EAD (£)" in v and "EAD 2050" not in v]
    for col in fmt_currency:
        if col in disp_df.columns:
            disp_df[col] = disp_df[col].apply(lambda x: f"£{x:,.0f}" if pd.notna(x) else "N/A")
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
        "Total PV (£)": sc_sub["pv"].sum(),
        "Mean Annual EAD (£)": sc_sub.groupby("year")["ead"].sum().mean() if not sc_sub.empty else 0,
        "EAD 2050 (£)": sc_sub[sc_sub["year"] == 2050]["ead"].sum(),
        "color": SCENARIOS.get(sc_id, {}).get("color", "#888"),
    })
sc_pv_df = pd.DataFrame(sc_pv_rows)

fig_sc = px.bar(sc_pv_df, x="Scenario", y="Total PV (£)",
                color="Scenario",
                color_discrete_map={r["Scenario"]: r["color"] for r in sc_pv_rows},
                text="Total PV (£)")
fig_sc.update_traces(texttemplate="£%{y:,.0f}", textposition="outside")
fig_sc.update_layout(height=340, showlegend=False,
                     margin=dict(l=20, r=20, t=20, b=100),
                     xaxis_tickangle=-20, yaxis_title="Total PV of Damages (£)")
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
            hovertemplate="Loss: £%{x:,.0f}<br>AEP: %{y:.4f}<extra></extra>",
        ))
        fig_ep.update_layout(
            xaxis_title="Loss (£)", yaxis_title="Annual Exceedance Probability",
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
                    "Total Portfolio Value (£)": f"£{total_value:,.0f}",
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
