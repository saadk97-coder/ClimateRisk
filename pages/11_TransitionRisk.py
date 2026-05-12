"""
Page 11 — Transition Risk

Four-layer transition risk per the BSR Climate Risk Practice memo (May 2026):
  L1 — Direct carbon cost (with sector pass-through)
  L2 — Technology disruption (Wright's Law / Lafond bands) + stranded-asset trigger
  L3 — Production-network propagation (Leontief inverse, screening grade)
  L4 — Reputational / capital-access overlay (Sautner CCExposure)

Non-duplication: each channel is routed exactly once (CFs, asset value, or WACC).
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from engine.asset_model import normalize_asset_state
from engine.fmt import currency_symbol as _currency_symbol, fmt as _fmt_cur
from engine.scenario_model import SCENARIOS
from engine.transition.transition_engine import (
    run_asset_transition,
    run_portfolio_transition,
    DEFAULT_HORIZON,
)
from engine.transition.cc_exposure import ROUTE_CASHFLOWS, ROUTE_WACC
from engine.transition.data_loader import (
    load_sector_taxonomy,
    load_sector_pass_through,
    load_carbon_prices,
    load_learning_curves,
    list_sectors,
    map_scenario_to_ngfs,
)

st.set_page_config(page_title="Transition Risk", page_icon="⚡", layout="wide")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(
    "<h1 style='color:#333;'>"
    "<span style='color:#F4721A;font-weight:900;'>BSR</span> Transition Risk Layer"
    "</h1>",
    unsafe_allow_html=True,
)
st.caption(
    "Four-layer transition risk decomposition per the BSR Climate Risk Practice memo "
    "(internal, May 2026). Implements Layers 1–4 from that document at screening grade."
)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
assets = normalize_asset_state(st.session_state)
cur = st.session_state.get("currency_code", "USD")
sym = _currency_symbol(cur)

if not assets:
    st.warning("No portfolio loaded. Add assets on the **Portfolio** page first.")
    st.stop()

selected_scenarios = st.session_state.get("selected_scenarios") or ["net_zero_2050", "current_policies"]

# ---------------------------------------------------------------------------
# Sector assignment status
# ---------------------------------------------------------------------------
unassigned = [a.id for a in assets if not a.sector]
if unassigned:
    st.warning(
        f"⚠️ {len(unassigned)} asset(s) have no `sector` set — they will be excluded "
        "from transition risk analysis. Edit the asset on the Portfolio page and pick "
        "a sector from the taxonomy. Affected: " + ", ".join(unassigned[:5]) + ("…" if len(unassigned) > 5 else "")
    )

active_assets = [a for a in assets if a.sector]
if not active_assets:
    st.error("No assets have a sector assignment. Set `sector` on at least one asset to use this page.")
    st.stop()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
with st.expander("⚙️ Configuration", expanded=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        l4_route = st.radio(
            "Layer 4 routing",
            options=[ROUTE_CASHFLOWS, ROUTE_WACC],
            index=0,
            help="Where does the CCExposure premium flow? Cash flows (revenue modifier) "
                 "OR WACC (financing premium) — pick one to preserve the BSR non-duplication rule.",
        )
    with c2:
        elasticity = st.slider(
            "Layer 3 substitution elasticity (CES σ)",
            0.5, 3.0, 1.0, 0.1,
            help="Cobb-Douglas baseline = 1.0. Higher values dampen network propagation "
                 "(more substitution between inputs); lower values amplify it. "
                 "Empirical estimates cluster 1.3–3.0 (Papageorgiou et al. 2017).",
        )
    with c3:
        layers_enabled = st.multiselect(
            "Enable layers",
            [1, 2, 3, 4],
            default=[1, 2, 3, 4],
            format_func=lambda i: {1: "L1 Carbon", 2: "L2 Technology", 3: "L3 Network", 4: "L4 Reputation"}[i],
        )

# ---------------------------------------------------------------------------
# Run transition engine
# ---------------------------------------------------------------------------
with st.spinner("Running four-layer transition model…"):
    results_by_scenario = run_portfolio_transition(
        assets=active_assets,
        scenario_ids=selected_scenarios,
        horizon=DEFAULT_HORIZON,
        layer4_routing=l4_route,
        elasticity=elasticity,
        enable_layers=tuple(layers_enabled),
    )

# ---------------------------------------------------------------------------
# Portfolio summary by scenario
# ---------------------------------------------------------------------------
st.subheader("Portfolio Summary by Scenario")

summary_rows = []
for sc, res in results_by_scenario.items():
    if not res:
        continue
    label = SCENARIOS.get(sc, {}).get("label", sc)
    cf_2030 = sum(r.annual_total_cost_usd.get(2030, 0.0) for r in res)
    cf_2050 = sum(r.annual_total_cost_usd.get(2050, 0.0) for r in res)
    imp_total = sum(sum(r.annual_impairment_usd.values()) for r in res)
    n_stranded = sum(1 for r in res if r.layer2_result and r.layer2_result.crossover_year is not None)
    avg_wacc_bps = sum(r.wacc_premium_bps for r in res) / max(len(res), 1)
    summary_rows.append({
        "Scenario": label,
        f"Annual Cost 2030 ({sym})": _fmt_cur(cf_2030, cur),
        f"Annual Cost 2050 ({sym})": _fmt_cur(cf_2050, cur),
        f"Cumulative Impairment 2025–2050 ({sym})": _fmt_cur(imp_total, cur),
        "Stranded Assets": f"{n_stranded}/{len(res)}",
        "Avg WACC Premium (bps)": f"{avg_wacc_bps:.0f}" if l4_route == ROUTE_WACC else "—",
    })

if summary_rows:
    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Tabs: time series, layer attribution, asset detail, methodology
# ---------------------------------------------------------------------------
tab_ts, tab_layer, tab_asset, tab_method = st.tabs([
    "📈 Time Series",
    "🧩 Layer Attribution",
    "🔍 Asset Detail",
    "📚 Methodology",
])

# --- Time series -----------------------------------------------------------
with tab_ts:
    st.markdown("Annual transition cost across scenarios. Sums all enabled layers per year.")
    rows = []
    for sc, res in results_by_scenario.items():
        if not res:
            continue
        label = SCENARIOS.get(sc, {}).get("label", sc)
        for y in DEFAULT_HORIZON:
            tot = sum(r.annual_total_cost_usd.get(y, 0.0) for r in res)
            rows.append({"Year": y, "Scenario": label, "Annual Cost (USD)": tot})
    if rows:
        df_ts = pd.DataFrame(rows)
        fig = px.line(
            df_ts, x="Year", y="Annual Cost (USD)", color="Scenario",
            title="Portfolio Annual Transition Cost (Layers 1–4 combined)",
        )
        fig.update_layout(height=420, margin=dict(t=50, b=10), legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, use_container_width=True)

    # Cumulative impairment
    rows = []
    for sc, res in results_by_scenario.items():
        if not res:
            continue
        label = SCENARIOS.get(sc, {}).get("label", sc)
        cum = 0.0
        for y in DEFAULT_HORIZON:
            cum += sum(r.annual_impairment_usd.get(y, 0.0) for r in res)
            rows.append({"Year": y, "Scenario": label, "Cumulative Impairment (USD)": cum})
    if rows:
        df_imp = pd.DataFrame(rows)
        fig = px.line(
            df_imp, x="Year", y="Cumulative Impairment (USD)", color="Scenario",
            title="Cumulative Stranded-Asset Impairment (Layer 2)",
        )
        fig.update_layout(height=380, margin=dict(t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)

# --- Layer attribution -----------------------------------------------------
with tab_layer:
    st.markdown(
        "Attribution of total annual cost across the four layers. Selecting a single "
        "scenario isolates the channel driving the impact."
    )
    sc_choice = st.selectbox(
        "Scenario", options=selected_scenarios,
        format_func=lambda s: SCENARIOS.get(s, {}).get("label", s),
    )
    res = results_by_scenario.get(sc_choice, [])
    if res:
        rows = []
        for y in DEFAULT_HORIZON:
            for ar in res:
                for layer_key, label in [
                    ("L1_carbon_opex", "L1 Carbon Opex"),
                    ("L2_revenue_erosion", "L2 Revenue Erosion"),
                    ("L3_network_input_cost", "L3 Network Input Cost"),
                    ("L4_revenue_modifier", "L4 Reputation/Capital"),
                ]:
                    rows.append({
                        "Year": y,
                        "Layer": label,
                        "Cost (USD)": ar.layer_breakdown.get(layer_key, {}).get(y, 0.0),
                    })
        df_l = pd.DataFrame(rows)
        df_agg = df_l.groupby(["Year", "Layer"], as_index=False)["Cost (USD)"].sum()
        fig = px.area(
            df_agg, x="Year", y="Cost (USD)", color="Layer",
            title=f"Layer Attribution — {SCENARIOS.get(sc_choice, {}).get('label', sc_choice)}",
        )
        fig.update_layout(height=440, margin=dict(t=50, b=10))
        st.plotly_chart(fig, use_container_width=True)

# --- Asset detail ----------------------------------------------------------
with tab_asset:
    st.markdown("Drill into a specific asset across scenarios.")
    asset_choice = st.selectbox(
        "Asset",
        options=[a.id for a in active_assets],
        format_func=lambda aid: next((f"{a.id} — {a.name} ({a.sector})" for a in active_assets if a.id == aid), aid),
    )
    if asset_choice:
        rows = []
        for sc in selected_scenarios:
            res = results_by_scenario.get(sc, [])
            ar = next((r for r in res if r.asset_id == asset_choice), None)
            if not ar:
                continue
            label = SCENARIOS.get(sc, {}).get("label", sc)
            for y in DEFAULT_HORIZON:
                rows.append({
                    "Year": y, "Scenario": label,
                    "L1 Carbon": ar.layer_breakdown["L1_carbon_opex"].get(y, 0.0),
                    "L2 Revenue": ar.layer_breakdown["L2_revenue_erosion"].get(y, 0.0),
                    "L3 Network": ar.layer_breakdown["L3_network_input_cost"].get(y, 0.0),
                    "L4 Reputation": ar.layer_breakdown["L4_revenue_modifier"].get(y, 0.0),
                    "Total CF Cost": ar.annual_total_cost_usd.get(y, 0.0),
                    "Annual Impairment": ar.annual_impairment_usd.get(y, 0.0),
                })
        if rows:
            df_a = pd.DataFrame(rows)
            with st.expander("Annual breakdown (table)", expanded=False):
                st.dataframe(df_a, use_container_width=True, hide_index=True)

            # Stranding crossover summary
            cross_rows = []
            for sc in selected_scenarios:
                res = results_by_scenario.get(sc, [])
                ar = next((r for r in res if r.asset_id == asset_choice), None)
                if not ar or not ar.layer2_result:
                    continue
                l2 = ar.layer2_result
                cross_rows.append({
                    "Scenario": SCENARIOS.get(sc, {}).get("label", sc),
                    "Incumbent Tech": l2.incumbent_tech or "—",
                    "Challenger Tech": l2.challenger_tech or "—",
                    "Crossover Year": l2.crossover_year if l2.crossover_year else "no crossover",
                    "Stranded Fraction by 2050": f"{l2.stranded_fraction_2050*100:.1f}%",
                })
            if cross_rows:
                st.markdown("**Layer 2 — Stranding Diagnostics**")
                st.dataframe(pd.DataFrame(cross_rows), use_container_width=True, hide_index=True)

            # CCExposure scores
            cce_rows = []
            for sc in selected_scenarios:
                res = results_by_scenario.get(sc, [])
                ar = next((r for r in res if r.asset_id == asset_choice), None)
                if not ar or not ar.layer4_result:
                    continue
                l4 = ar.layer4_result
                cce_rows.append({
                    "Scenario": SCENARIOS.get(sc, {}).get("label", sc),
                    "CCE Opportunity": f"{l4.cce_opportunity:.2f}",
                    "CCE Regulatory":  f"{l4.cce_regulatory:.2f}",
                    "CCE Physical":    f"{l4.cce_physical:.2f}",
                    "Credit Spread Δ (bps)": f"{l4.credit_spread_premium_bps:.0f}",
                    "Equity Premium Δ (bps)": f"{l4.equity_premium_bps:.0f}",
                    "Revenue Growth Δ (bps)": f"{l4.revenue_growth_modifier_bps:.0f}",
                })
            if cce_rows:
                st.markdown("**Layer 4 — Reputational / Capital Diagnostics**")
                st.dataframe(pd.DataFrame(cce_rows), use_container_width=True, hide_index=True)

            # Top upstream sources from one scenario / mid-horizon
            mid_year = 2040
            sc_first = selected_scenarios[0]
            ar = next((r for r in results_by_scenario.get(sc_first, []) if r.asset_id == asset_choice), None)
            if ar and ar.layer3_results:
                l3 = next((x for x in ar.layer3_results if x.year == mid_year), ar.layer3_results[0])
                if l3.top_upstream_sources:
                    st.markdown(f"**Layer 3 — Top Upstream Cost Sources ({SCENARIOS.get(sc_first, {}).get('label', sc_first)}, {l3.year})**")
                    st.dataframe(
                        pd.DataFrame(l3.top_upstream_sources, columns=["Upstream Sector", f"Indirect Cost ({sym})"]),
                        use_container_width=True, hide_index=True,
                    )

# --- Methodology -----------------------------------------------------------
with tab_method:
    st.markdown("""
### Architecture (BSR memo, four-layer)

| Layer | Channel | Mechanism | Routes to |
|------:|---------|-----------|-----------|
| **L1** | Carbon cost | Scope 1+2 emissions × NGFS carbon price × (1 − pass-through) | Cash flow OpEx |
| **L2** | Technology / stranding | Wright's Law cost crossover + sector demand pathway | Cash flow + asset impairment |
| **L3** | Network propagation | Sector-typical shock vector → Leontief inverse → focal sector input cost | Cash flow input cost |
| **L4** | Reputation / capital | Sautner CCExposure × empirical elasticities | Cash flow OR WACC (one only) |

### Non-duplication rule
Each channel routes exactly once. Layer 4 routing is configurable; default is cash
flows. Stranded-asset impairment (L2) flows to balance sheet (annual_impairment),
not cash flows — consistent with the BSR framework's distinction between OpEx
adjustment and value impairment.

### Sources
- Sijm et al. (2012) · Fabra & Reguant (2014) · Cludius et al. (2020) — pass-through
- Way et al. (Joule 2022) · Lafond et al. (TFSC 2018) — learning curves
- Acemoglu et al. (2012) · Reisch et al. (arXiv 2025) · Stadler et al. (JIE 2018) — IO networks
- Sautner et al. (JoF 2023, Mgmt Sci 2023) — CCExposure
- NGFS Phase V REMIND-MAgPIE 3.2 (2023) — carbon prices
- IEA WEO 2023 — sector pathways

### Known limitations (screening grade)
- I-O matrix is a 20-sector single-region aggregation. For production: use full
  EXIOBASE-3 MRIO (200 sectors × 49 regions).
- Sector pass-through is sector-median; firm-specific values vary materially with
  market power and trade exposure.
- CCExposure uses sector medians as proxies — firm-level Sautner data is licensed
  separately (override `firm_override` in `compute_exposure_premium`).
- Carbon-price values approximate published NGFS Phase V REMIND outputs;
  refresh from the NGFS Scenarios Portal for regulatory disclosures.
""")

    # Carbon price viewer
    with st.expander("📊 Carbon price trajectories (USD/tCO2)", expanded=False):
        cp = load_carbon_prices()
        rows = []
        for sc_id, scen in cp["scenarios"].items():
            label = scen.get("label", sc_id)
            for region in ("advanced", "emerging", "rest_of_world"):
                curve = scen.get(region, {})
                for y_str, v in curve.items():
                    rows.append({"Scenario": label, "Region": region, "Year": int(y_str), "Price": float(v)})
        df_cp = pd.DataFrame(rows)
        if not df_cp.empty:
            sel_region = st.selectbox("Region", ["advanced", "emerging", "rest_of_world"])
            df_show = df_cp[df_cp["Region"] == sel_region]
            fig = px.line(df_show, x="Year", y="Price", color="Scenario",
                          title=f"NGFS Phase V Carbon Prices — {sel_region}",
                          labels={"Price": "USD/tCO2"})
            fig.update_layout(height=380)
            st.plotly_chart(fig, use_container_width=True)

    # Pass-through table
    with st.expander("📊 Sector pass-through reference table", expanded=False):
        spt = load_sector_pass_through()
        rows = []
        for sec_key, d in spt["sectors"].items():
            rows.append({
                "Sector": sec_key,
                "Pass-through": f"{d['pass_through']*100:.0f}%",
                "Demand Elasticity": f"{d['demand_elasticity']:+.2f}",
                "Market Structure": d["market_structure"],
                "Trade Exposed": "✓" if d["trade_exposed"] else "—",
                "Source": d.get("source_ref", "—"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("📊 Learning rates by technology", expanded=False):
        lc = load_learning_curves()
        rows = []
        for tech, d in lc["technologies"].items():
            rows.append({
                "Technology": d.get("label", tech),
                "Category": d.get("category", "—"),
                "Learning Rate": f"{d['learning_rate']*100:.1f}%",
                "Lafond σ": f"{d.get('lafond_sigma', 0):.3f}",
                "Source": d.get("source_ref", "—"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "**Reference:** BSR Climate Risk Practice Memo (May 2026) — *Quantifying Transition Risk: "
    "Landscape, Frontier, and a Path Forward*. Path A productisation."
)
