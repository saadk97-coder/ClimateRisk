"""
Page 6 – Adaptation: per-asset measure selection, cost-benefit analysis, frontier chart.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from dataclasses import asdict

from engine.adaptation_engine import list_measures, calc_adaptation, portfolio_adaptation_frontier, AdaptationResult
from engine.scenario_model import SCENARIOS
from engine.export_engine import export_adaptation_xlsx

st.set_page_config(page_title="Adaptation", page_icon="🛡️", layout="wide")

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    total_val = sum(a.replacement_value for a in st.session_state.get("assets", []))
    st.metric("Assets", n)
    st.metric("Total Value", f"£{total_val:,.0f}")

st.title("Adaptation Measures")
st.markdown(
    "Evaluate the cost-effectiveness of adaptation measures at asset and portfolio level."
)

from engine.asset_model import Asset as _Asset
assets = [_Asset.from_dict(a) if isinstance(a, dict) else a for a in st.session_state.get("assets", [])]
results = st.session_state.get("results", [])
discount_rate = st.session_state.get("discount_rate", 0.035)

if not assets:
    st.warning("No assets defined.")
    st.stop()
if not results:
    st.warning("No damage results. Run the calculation on the Results page first.")
    st.stop()

selected_scenarios = st.session_state.get("selected_scenarios", [])
selected_horizons = st.session_state.get("selected_horizons", [2050])

# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------
col1, col2 = st.columns(2)
with col1:
    adap_scenario = st.selectbox(
        "Base Scenario",
        selected_scenarios if selected_scenarios else list(SCENARIOS.keys()),
        format_func=lambda s: SCENARIOS.get(s, {}).get("label", s),
    )
with col2:
    adap_year = st.selectbox("Year", selected_horizons if selected_horizons else [2050])

# ---------------------------------------------------------------------------
# Per-asset adaptation panel
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Asset-Level Adaptation")

asset_names = {a.id: a.name for a in assets}
sel_asset_id = st.selectbox(
    "Select Asset",
    [a.id for a in assets],
    format_func=lambda i: asset_names.get(i, i),
)
sel_asset = next((a for a in assets if a.id == sel_asset_id), None)

# Get baseline EAD for selected asset
asset_results_match = [
    r for r in results
    if r.asset_id == sel_asset_id and r.scenario_id == adap_scenario and r.year == adap_year
]
baseline_ead_total = asset_results_match[0].total_ead if asset_results_match else 0.0
hazard_eads = {}
if asset_results_match:
    for haz, hr in asset_results_match[0].hazard_results.items():
        hazard_eads[haz] = hr.ead

if sel_asset:
    st.metric("Baseline Total EAD", f"£{baseline_ead_total:,.0f}", delta=None)
    st.caption(f"Asset Value: £{sel_asset.replacement_value:,.0f} | Discount Rate: {discount_rate*100:.1f}%")

    # Get applicable measures
    measures = list_measures(asset_type=sel_asset.asset_type)

    if not measures:
        st.info("No adaptation measures available for this asset type.")
    else:
        # Group by hazard
        measures_by_hazard = {}
        for m in measures:
            haz = m["hazard"]
            measures_by_hazard.setdefault(haz, []).append(m)

        selected_measure_ids = st.session_state.get(f"selected_measures_{sel_asset_id}", [])
        new_selected = []

        for haz, haz_measures in measures_by_hazard.items():
            baseline_haz_ead = hazard_eads.get(haz, 0.0)
            with st.expander(f"🔧 {haz.capitalize()} Measures (Baseline EAD: £{baseline_haz_ead:,.0f})"):
                for m in haz_measures:
                    checked = m["id"] in selected_measure_ids
                    capex_est = sel_asset.replacement_value * m["capex_pct"] / 100
                    label = (
                        f"**{m['label']}** — Capex: ~£{capex_est:,.0f} | "
                        f"Reduction: {m['damage_reduction_pct']}% | "
                        f"Life: {m['design_life_years']} yrs"
                    )
                    if st.checkbox(label, value=checked, key=f"m_{sel_asset_id}_{m['id']}"):
                        new_selected.append(m["id"])
                    st.caption(m["description"])

        st.session_state[f"selected_measures_{sel_asset_id}"] = new_selected

        # Cost-benefit table for selected measures
        if new_selected:
            st.subheader("Cost-Benefit Analysis")
            adap_results = []
            for mid in new_selected:
                m = next((x for x in measures if x["id"] == mid), None)
                if m:
                    baseline = hazard_eads.get(m["hazard"], baseline_ead_total)
                    try:
                        ar = calc_adaptation(mid, sel_asset_id, sel_asset.replacement_value, baseline, discount_rate)
                        adap_results.append(ar)
                    except Exception as e:
                        st.error(f"Error calculating {mid}: {e}")

            if adap_results:
                # ── Headline ROI metrics ─────────────────────────────────────────
                total_capex   = sum(ar.capex for ar in adap_results)
                total_opex_pv = sum(ar.npv_opex for ar in adap_results)
                total_cost    = sum(ar.total_cost for ar in adap_results)
                total_benefits_pv = sum(ar.npv_benefits for ar in adap_results)
                total_avoided = sum(ar.avoided_ead_annual for ar in adap_results)
                avg_cbr       = total_benefits_pv / total_cost if total_cost > 0 else 0.0
                roi_pct       = (total_benefits_pv - total_cost) / total_cost * 100 if total_cost > 0 else 0.0

                roi_col, cbr_col, payback_col, info_col = st.columns([2, 2, 2, 1])
                with roi_col:
                    st.metric(
                        "Adaptation ROI",
                        f"{roi_pct:.0f}%",
                        help=(
                            "Adaptation Return on Investment: (NPV Benefits − Total Cost) / Total Cost × 100. "
                            "Positive = benefits exceed costs over the design life at the chosen discount rate."
                        ),
                    )
                with cbr_col:
                    st.metric(
                        "Cost-Benefit Ratio",
                        f"{avg_cbr:.2f}×",
                        help=(
                            "NPV Benefits ÷ Total Cost. CBR > 1.0 means the measure pays back. "
                            "Preferred threshold: ≥ 1.5× for robust investment decisions under uncertainty."
                        ),
                    )
                with payback_col:
                    avg_payback = total_capex / total_avoided if total_avoided > 0 else 999
                    st.metric(
                        "Simple Payback",
                        f"{avg_payback:.1f} yrs" if avg_payback < 99 else ">50 yrs",
                        help="Upfront capex ÷ avoided EAD per year. A simple non-discounted breakeven metric.",
                    )
                with info_col:
                    with st.popover("ℹ️ ROI methodology"):
                        st.markdown(
                            "**Adaptation Return on Investment (ROI)**\n\n"
                            "Calculated as: `(NPV Benefits − Total Cost) / Total Cost × 100`\n\n"
                            "**NPV Benefits** = Σ (avoided_EAD_annual × discount_factor) over design life\n\n"
                            "**Total Cost** = Capex + NPV of annual opex (maintenance)\n\n"
                            "**Discount factor** = 1 / (1 + r)^t at the chosen discount rate r\n\n"
                            "**Cost-Benefit Ratio (CBR)** = NPV Benefits / Total Cost\n"
                            "- CBR > 1.0: Benefits exceed costs — measure is economically justified\n"
                            "- CBR > 2.0: Strongly positive case for investment\n\n"
                            "**Payback period** = Capex / avoided_EAD_annual\n"
                            "(simple, undiscounted — use as a quick screen only)\n\n"
                            "Source framework: FEMA BCA Toolkit (2021); EA Appraisal of Flood "
                            "Risk Management Measures (2019); HM Treasury Green Book."
                        )

                # ── Cost-benefit table ───────────────────────────────────────────
                cb_rows = []
                for ar in adap_results:
                    ar_roi = (ar.npv_benefits - ar.total_cost) / ar.total_cost * 100 if ar.total_cost > 0 else 0.0
                    cb_rows.append({
                        "Measure":             ar.measure_label,
                        "Hazard":              ar.hazard.capitalize(),
                        "Capex (£)":           f"£{ar.capex:,.0f}",
                        "NPV Opex (£)":        f"£{ar.npv_opex:,.0f}",
                        "Avoided EAD/yr (£)":  f"£{ar.avoided_ead_annual:,.0f}",
                        "NPV Benefits (£)":    f"£{ar.npv_benefits:,.0f}",
                        "ROI (%)":             f"{ar_roi:.0f}%",
                        "CBR":                 f"{ar.cbr:.2f}×",
                        "Payback (yrs)":       f"{ar.payback_years:.1f}" if ar.payback_years < 999 else ">50",
                        "Reduction (%)":       f"{ar.damage_reduction_pct:.0f}%",
                    })

                st.dataframe(pd.DataFrame(cb_rows), use_container_width=True, hide_index=True)

                adapted_ead = max(0, baseline_ead_total - total_avoided)
                st.metric(
                    "Adapted Total EAD",
                    f"£{adapted_ead:,.0f}",
                    delta=f"-£{total_avoided:,.0f}/yr avoided",
                    delta_color="inverse",
                )

# ---------------------------------------------------------------------------
# Portfolio-level adaptation frontier
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Portfolio Adaptation Frontier")

if st.button("📊 Compute Portfolio Frontier", type="primary"):
    all_adap_results = []
    for asset in assets:
        asset_match = [
            r for r in results
            if r.asset_id == asset.id and r.scenario_id == adap_scenario and r.year == adap_year
        ]
        if not asset_match:
            continue

        hazard_eads_all = {haz: hr.ead for haz, hr in asset_match[0].hazard_results.items()}
        measures_all = list_measures(asset_type=asset.asset_type)

        for m in measures_all:
            baseline = hazard_eads_all.get(m["hazard"], 0.0)
            if baseline > 0:
                try:
                    ar = calc_adaptation(m["id"], asset.id, asset.replacement_value, baseline, discount_rate)
                    all_adap_results.append(ar)
                except Exception:
                    pass

    if all_adap_results:
        frontier = portfolio_adaptation_frontier(all_adap_results)
        frontier_df = pd.DataFrame(frontier)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=frontier_df["cumulative_capex"],
            y=frontier_df["cumulative_avoided_ead_annual"],
            mode="lines+markers",
            name="Risk reduction frontier",
            line=dict(color="#27ae60", width=2),
            fill="tozeroy",
            fillcolor="rgba(39,174,96,0.1)",
            text=frontier_df["measure_label"] + " | " + frontier_df["asset_id"],
            hovertemplate="<b>%{text}</b><br>Cumulative Capex: £%{x:,.0f}<br>Avoided EAD: £%{y:,.0f}/yr<extra></extra>",
        ))
        fig.update_layout(
            xaxis_title="Cumulative Capex (£)",
            yaxis_title="Cumulative Avoided EAD (£/yr)",
            height=400,
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Top measures by CBR
        st.subheader("Top Adaptation Measures by Cost-Benefit Ratio")
        top_df = frontier_df[["measure_label", "asset_id", "capex", "cbr"]].copy()
        top_df.columns = ["Measure", "Asset ID", "Capex (£)", "CBR"]
        top_df = top_df.head(15).reset_index(drop=True)
        top_df.index += 1
        top_df["Capex (£)"] = top_df["Capex (£)"].apply(lambda x: f"£{x:,.0f}")
        top_df["CBR"] = top_df["CBR"].apply(lambda x: f"{x:.2f}x")
        st.dataframe(top_df, use_container_width=True)

        # Export
        export_df = pd.DataFrame([{
            "measure_id": r.measure_id,
            "measure": r.measure_label,
            "hazard": r.hazard,
            "asset_id": r.asset_id,
            "capex": r.capex,
            "npv_opex": r.npv_opex,
            "total_cost": r.total_cost,
            "baseline_ead": r.baseline_ead,
            "adapted_ead": r.adapted_ead,
            "avoided_ead_annual": r.avoided_ead_annual,
            "npv_benefits": r.npv_benefits,
            "cbr": r.cbr,
            "payback_years": r.payback_years,
        } for r in all_adap_results])
        col_a, col_b = st.columns(2)
        with col_a:
            try:
                xlsx_bytes = export_adaptation_xlsx(export_df, frontier_df)
                st.download_button(
                    "⬇️ Export Full Adaptation Analysis (.xlsx)", data=xlsx_bytes,
                    file_name="adaptation_results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            except Exception as e:
                st.warning(f"XLSX export unavailable: {e}")
        with col_b:
            csv_bytes = export_df.to_csv(index=False).encode()
            st.download_button("⬇️ Export Full Adaptation Analysis (.csv)", csv_bytes, "adaptation_results.csv", "text/csv")
    else:
        st.info("No adaptation results generated (no assets with EAD > 0).")
