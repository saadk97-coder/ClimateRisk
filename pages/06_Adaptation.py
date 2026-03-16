"""
Page 6 – Adaptation: NPV-based multi-year cost-benefit analysis with
mini financial modelling platform, per-asset measure selection, and
portfolio-level investment frontier.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import math
from engine.fmt import currency_symbol as _currency_symbol, fmt as _fmt_cur
from engine.adaptation_engine import (
    list_measures,
    calc_adaptation,
    calc_adaptation_npv,
    portfolio_adaptation_frontier,
    portfolio_adaptation_frontier_npv,
    AdaptationResult,
    AdaptationNPVResult,
)
from engine.scenario_model import SCENARIOS
from engine.export_engine import export_adaptation_xlsx

st.set_page_config(page_title="Adaptation", page_icon="🛡️", layout="wide")

# ── BSR colour palette ────────────────────────────────────────────────────────
_BSR = {
    "orange": "#F4721A", "navy": "#1A3A5C", "teal": "#2A9D8F",
    "amber": "#E9C46A", "red": "#C94040", "green": "#27ae60",
    "light": "#F8F4F0",
}

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    total_val = sum(a.replacement_value for a in st.session_state.get("assets", []))
    _cur = st.session_state.get("currency_code", "GBP")
    st.metric("Assets", n)
    st.metric("Total Value", _fmt_cur(total_val, _cur))

st.title("Adaptation Measures")
st.markdown(
    "NPV-based multi-year cost-benefit analysis for adaptation investments. "
    "All benefits are computed against the **full 2025-2050 annual damage stream** "
    "so that escalating climate risk is properly captured."
)

from engine.asset_model import Asset as _Asset
assets = [_Asset.from_dict(a) if isinstance(a, dict) else a for a in st.session_state.get("assets", [])]
annual_df: pd.DataFrame = st.session_state.get("annual_damages", pd.DataFrame())
results = st.session_state.get("results", [])
discount_rate = st.session_state.get("discount_rate", 0.035)
_cur = st.session_state.get("currency_code", "GBP")
_sym = _currency_symbol(_cur)

if not assets:
    st.warning("No assets defined.")
    st.stop()
if annual_df.empty and not results:
    st.warning("No damage results. Run the calculation on the Results page first.")
    st.stop()

selected_scenarios = st.session_state.get("selected_scenarios", [])

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — Financial modelling controls
# ═══════════════════════════════════════════════════════════════════════════════
st.divider()

st.markdown(
    f"<h3 style='color:{_BSR['navy']};margin:0;'>Financial Model Parameters</h3>",
    unsafe_allow_html=True,
)
st.caption("Configure investment timing, capex phasing, and discount assumptions.")

fc1, fc2, fc3, fc4 = st.columns(4)
with fc1:
    adap_scenario = st.selectbox(
        "Climate Scenario",
        selected_scenarios if selected_scenarios else list(SCENARIOS.keys()),
        format_func=lambda s: SCENARIOS.get(s, {}).get("label", s),
    )
with fc2:
    impl_year = st.number_input(
        "Implementation Year",
        min_value=2025, max_value=2048, value=2027, step=1,
        help="Year the measure becomes operational and starts reducing damage.",
    )
with fc3:
    adap_discount = st.number_input(
        "Discount Rate (%)",
        min_value=0.0, max_value=15.0, value=discount_rate * 100, step=0.5,
        help="Annual rate for PV calculations. Default matches your global setting.",
    ) / 100.0
with fc4:
    capex_phase_mode = st.selectbox(
        "Capex Phasing",
        ["Upfront (year before)", "2-year split", "3-year split", "Custom"],
        help="How capital expenditure is spread across years.",
    )

# Build capex_phases dict from mode
def _build_capex_phases(mode: str, impl_yr: int) -> dict:
    if mode == "Upfront (year before)":
        return {impl_yr - 1: 1.0}
    elif mode == "2-year split":
        return {impl_yr - 2: 0.5, impl_yr - 1: 0.5}
    elif mode == "3-year split":
        return {impl_yr - 3: 0.34, impl_yr - 2: 0.33, impl_yr - 1: 0.33}
    return None  # Custom handled in UI

capex_phases = _build_capex_phases(capex_phase_mode, impl_year)

if capex_phase_mode == "Custom":
    st.caption("Enter capex allocation by year (fractions summing to 1.0):")
    cc1, cc2, cc3 = st.columns(3)
    custom_phases = {}
    with cc1:
        y1 = st.number_input("Year 1", min_value=2025, max_value=2050, value=impl_year - 2, key="cp_y1")
        f1 = st.number_input("Fraction", min_value=0.0, max_value=1.0, value=0.5, step=0.1, key="cp_f1")
        if f1 > 0:
            custom_phases[y1] = f1
    with cc2:
        y2 = st.number_input("Year 2", min_value=2025, max_value=2050, value=impl_year - 1, key="cp_y2")
        f2 = st.number_input("Fraction", min_value=0.0, max_value=1.0, value=0.5, step=0.1, key="cp_f2")
        if f2 > 0:
            custom_phases[y2] = f2
    with cc3:
        y3 = st.number_input("Year 3 (optional)", min_value=2025, max_value=2050, value=impl_year, key="cp_y3")
        f3 = st.number_input("Fraction", min_value=0.0, max_value=1.0, value=0.0, step=0.1, key="cp_f3")
        if f3 > 0:
            custom_phases[y3] = f3
    capex_phases = custom_phases if custom_phases else {impl_year - 1: 1.0}


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: extract annual EAD stream for an asset+scenario from annual_df
# ═══════════════════════════════════════════════════════════════════════════════
def _get_annual_eads(asset_id: str, scenario_id: str, hazard: str = None) -> dict:
    """Return {year: ead} from the annual damages dataframe."""
    if annual_df.empty:
        return {}
    mask = (annual_df["asset_id"] == asset_id) & (annual_df["scenario_id"] == scenario_id)
    if hazard:
        mask &= (annual_df["hazard"] == hazard)
    sub = annual_df[mask].groupby("year")["ead"].sum()
    return sub.to_dict()


def _get_hazard_annual_eads(asset_id: str, scenario_id: str) -> dict:
    """Return {hazard: {year: ead}}."""
    if annual_df.empty:
        return {}
    mask = (annual_df["asset_id"] == asset_id) & (annual_df["scenario_id"] == scenario_id)
    sub = annual_df[mask]
    out = {}
    for haz in sub["hazard"].unique():
        haz_sub = sub[sub["hazard"] == haz].groupby("year")["ead"].sum()
        out[haz] = haz_sub.to_dict()
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — Per-Asset NPV Adaptation Analysis
# ═══════════════════════════════════════════════════════════════════════════════
st.divider()
st.markdown(
    f"<h3 style='color:{_BSR['navy']};margin:0;'>Asset-Level Adaptation</h3>",
    unsafe_allow_html=True,
)

asset_names = {a.id: a.name for a in assets}
sel_asset_id = st.selectbox(
    "Select Asset",
    [a.id for a in assets],
    format_func=lambda i: asset_names.get(i, i),
)
sel_asset = next((a for a in assets if a.id == sel_asset_id), None)

# Get baseline annual EADs
total_annual_eads = _get_annual_eads(sel_asset_id, adap_scenario)
hazard_annual_eads = _get_hazard_annual_eads(sel_asset_id, adap_scenario)

# Fallback to coarse results if annual_df is empty
if not total_annual_eads and results:
    _matches = [r for r in results if r.asset_id == sel_asset_id and r.scenario_id == adap_scenario]
    for rm in _matches:
        total_annual_eads[rm.year] = rm.total_ead
        for haz, hr in rm.hazard_results.items():
            hazard_annual_eads.setdefault(haz, {})[rm.year] = hr.ead

if sel_asset and total_annual_eads:
    # NPV of baseline damage stream
    _npv_baseline = sum(
        ead / (1 + adap_discount) ** (yr - 2025) for yr, ead in total_annual_eads.items()
    )
    _ead_2025 = total_annual_eads.get(2025, 0.0)
    _ead_2050 = total_annual_eads.get(2050, 0.0)

    bm1, bm2, bm3, bm4 = st.columns(4)
    bm1.metric("NPV Baseline Damages (2025-2050)", _fmt_cur(_npv_baseline, _cur))
    bm2.metric("EAD 2025", _fmt_cur(_ead_2025, _cur))
    bm3.metric("EAD 2050", _fmt_cur(_ead_2050, _cur),
               delta=f"+{(_ead_2050 - _ead_2025) / max(_ead_2025, 1) * 100:.0f}%" if _ead_2025 > 0 else None)
    bm4.metric("Asset Value", _fmt_cur(sel_asset.replacement_value, _cur))

    # ── Measure selection ─────────────────────────────────────────────────────
    measures = list_measures(asset_type=sel_asset.asset_type)

    if not measures:
        st.info("No adaptation measures available for this asset type.")
    else:
        measures_by_hazard = {}
        for m in measures:
            measures_by_hazard.setdefault(m["hazard"], []).append(m)

        selected_measure_ids = st.session_state.get(f"selected_measures_{sel_asset_id}", [])
        new_selected = []

        for haz, haz_measures in measures_by_hazard.items():
            haz_eads = hazard_annual_eads.get(haz, {})
            haz_npv = sum(
                ead / (1 + adap_discount) ** (yr - 2025) for yr, ead in haz_eads.items()
            )
            with st.expander(
                f"🔧 {haz.capitalize()} — NPV Baseline: {_fmt_cur(haz_npv, _cur)}",
            ):
                for m in haz_measures:
                    checked = m["id"] in selected_measure_ids
                    capex_est = sel_asset.replacement_value * m["capex_pct"] / 100
                    label = (
                        f"**{m['label']}** — Capex: ~{_fmt_cur(capex_est, _cur)} | "
                        f"Reduction: {m['damage_reduction_pct']}% | "
                        f"Life: {m['design_life_years']} yrs"
                    )
                    if st.checkbox(label, value=checked, key=f"m_{sel_asset_id}_{m['id']}"):
                        new_selected.append(m["id"])
                    st.caption(m["description"])

        st.session_state[f"selected_measures_{sel_asset_id}"] = new_selected

        # ═════════════════════════════════════════════════════════════════════
        # SECTION 3 — NPV Cost-Benefit Analysis
        # ═════════════════════════════════════════════════════════════════════
        if new_selected:
            st.divider()
            st.markdown(
                f"<h3 style='color:{_BSR['navy']};margin:0;'>NPV Cost-Benefit Analysis</h3>",
                unsafe_allow_html=True,
            )
            st.caption(
                f"All values discounted at {adap_discount*100:.1f}% to 2025. "
                f"Implementation year: {impl_year}. Capex: {capex_phase_mode}."
            )

            npv_results: list[AdaptationNPVResult] = []
            for mid in new_selected:
                m = next((x for x in measures if x["id"] == mid), None)
                if m:
                    haz_eads = hazard_annual_eads.get(m["hazard"], total_annual_eads)
                    try:
                        ar = calc_adaptation_npv(
                            mid, sel_asset_id, sel_asset.replacement_value,
                            haz_eads, adap_discount,
                            implementation_year=impl_year,
                            capex_phases=capex_phases,
                        )
                        npv_results.append(ar)
                    except Exception as e:
                        st.error(f"Error calculating {mid}: {e}")

            if npv_results:
                # ── Headline metrics ──────────────────────────────────────
                total_capex = sum(r.capex_total for r in npv_results)
                total_cost = sum(r.total_cost for r in npv_results)
                total_npv_avoided = sum(r.npv_avoided_damages for r in npv_results)

                if len(npv_results) > 1:
                    st.warning(
                        "**Combined benefit estimates may overstate savings.** "
                        "Multiple measures targeting the same hazard are evaluated independently "
                        "against the same baseline loss. Interactions between measures are not modelled — "
                        "actual combined benefit will be less than the sum of individual benefits.",
                        icon="⚠️",
                    )
                total_net_npv = total_npv_avoided - total_cost
                combined_cbr = total_npv_avoided / total_cost if total_cost > 0 else 0.0
                combined_roi = (total_npv_avoided - total_cost) / total_cost * 100 if total_cost > 0 else 0.0

                hm1, hm2, hm3, hm4, hm5 = st.columns(5)
                hm1.metric(
                    "Net NPV",
                    _fmt_cur(total_net_npv, _cur),
                    help="NPV of avoided damages minus NPV of all costs. Positive = value-creating investment.",
                )
                hm2.metric(
                    "Adaptation ROI",
                    f"{combined_roi:.0f}%",
                    help="(NPV Benefits − NPV Costs) / NPV Costs × 100.",
                )
                hm3.metric(
                    "Cost-Benefit Ratio",
                    f"{combined_cbr:.2f}×",
                    help="NPV Avoided Damages / NPV Total Cost. >1.0 = net positive.",
                )
                # IRR — use the combined cashflows
                _combined_cf = {}
                for r in npv_results:
                    for row in r.annual_cashflows:
                        _combined_cf[row["year"]] = _combined_cf.get(row["year"], 0.0) + row["net_cashflow"]
                _combined_irr = npv_results[0].irr if len(npv_results) == 1 else float("nan")
                if len(npv_results) > 1:
                    from engine.adaptation_engine import _calc_irr
                    try:
                        _combined_irr = _calc_irr([_combined_cf[y] for y in sorted(_combined_cf)])
                    except Exception:
                        _combined_irr = float("nan")
                hm4.metric(
                    "IRR",
                    f"{_combined_irr * 100:.1f}%" if not math.isnan(_combined_irr) else "N/A",
                    help="Internal Rate of Return — the discount rate at which Net NPV = 0.",
                )
                # Discounted payback
                _earliest_payback = min(
                    (r.discounted_payback_year for r in npv_results if r.discounted_payback_year),
                    default=None,
                )
                hm5.metric(
                    "Discounted Payback",
                    str(_earliest_payback) if _earliest_payback else "Beyond 2050",
                    help="First year in which cumulative discounted net cash flow turns positive.",
                )

                # ── Per-measure summary table ─────────────────────────────
                cb_rows = []
                for r in npv_results:
                    cb_rows.append({
                        "Measure": r.measure_label,
                        "Hazard": r.hazard.capitalize(),
                        f"Capex ({_sym})": r.capex_total,
                        f"NPV Cost ({_sym})": r.total_cost,
                        f"NPV Avoided ({_sym})": r.npv_avoided_damages,
                        f"Net NPV ({_sym})": r.net_npv,
                        "CBR": r.cbr,
                        "ROI (%)": r.roi_pct,
                        "IRR": r.irr * 100 if not math.isnan(r.irr) else None,
                        "Payback": r.discounted_payback_year,
                    })
                cb_df = pd.DataFrame(cb_rows)

                # Format
                _fmt_map = {
                    f"Capex ({_sym})": lambda x: _fmt_cur(x, _cur),
                    f"NPV Cost ({_sym})": lambda x: _fmt_cur(x, _cur),
                    f"NPV Avoided ({_sym})": lambda x: _fmt_cur(x, _cur),
                    f"Net NPV ({_sym})": lambda x: _fmt_cur(x, _cur),
                    "CBR": lambda x: f"{x:.2f}×",
                    "ROI (%)": lambda x: f"{x:.0f}%",
                    "IRR": lambda x: f"{x:.1f}%" if pd.notna(x) else "N/A",
                    "Payback": lambda x: str(int(x)) if pd.notna(x) else ">2050",
                }
                cb_display = cb_df.copy()
                for col, fn in _fmt_map.items():
                    if col in cb_display.columns:
                        cb_display[col] = cb_display[col].apply(fn)

                st.dataframe(cb_display, use_container_width=True, hide_index=True)

                # ═════════════════════════════════════════════════════════════
                # SECTION 4 — Year-by-Year Cash Flow Detail
                # ═════════════════════════════════════════════════════════════
                st.divider()
                st.markdown(
                    f"<h3 style='color:{_BSR['navy']};margin:0;'>Year-by-Year Cash Flows</h3>",
                    unsafe_allow_html=True,
                )

                # Aggregate across all selected measures
                cf_combined = {}
                for r in npv_results:
                    for row in r.annual_cashflows:
                        yr = row["year"]
                        if yr not in cf_combined:
                            cf_combined[yr] = {
                                "year": yr,
                                "baseline_ead": 0.0, "avoided_damage": 0.0,
                                "adapted_ead": 0.0, "capex": 0.0, "opex": 0.0,
                                "net_cashflow": 0.0, "net_cashflow_pv": 0.0,
                                "cumulative_npv": 0.0,
                            }
                        for k in ["baseline_ead", "avoided_damage", "adapted_ead",
                                  "capex", "opex", "net_cashflow", "net_cashflow_pv"]:
                            cf_combined[yr][k] += row[k]

                # Rebuild cumulative NPV
                cum = 0.0
                for yr in sorted(cf_combined):
                    cum += cf_combined[yr]["net_cashflow_pv"]
                    cf_combined[yr]["cumulative_npv"] = cum

                cf_df = pd.DataFrame([cf_combined[yr] for yr in sorted(cf_combined)])

                # ── Cash flow waterfall chart ─────────────────────────────
                tab_chart, tab_table = st.tabs(["📊 Cash Flow Chart", "📋 Detailed Table"])

                with tab_chart:
                    fig_cf = go.Figure()

                    # Avoided damage bars (positive)
                    fig_cf.add_trace(go.Bar(
                        x=cf_df["year"], y=cf_df["avoided_damage"],
                        name="Avoided Damage",
                        marker_color=_BSR["green"],
                        hovertemplate=f"Avoided: {_sym}%{{y:,.0f}}<extra></extra>",
                    ))
                    # Capex bars (negative)
                    fig_cf.add_trace(go.Bar(
                        x=cf_df["year"], y=-cf_df["capex"],
                        name="Capex",
                        marker_color=_BSR["red"],
                        hovertemplate=f"Capex: {_sym}%{{customdata:,.0f}}<extra></extra>",
                        customdata=cf_df["capex"],
                    ))
                    # Opex bars (negative)
                    fig_cf.add_trace(go.Bar(
                        x=cf_df["year"], y=-cf_df["opex"],
                        name="Opex",
                        marker_color=_BSR["amber"],
                        hovertemplate=f"Opex: {_sym}%{{customdata:,.0f}}<extra></extra>",
                        customdata=cf_df["opex"],
                    ))
                    # Cumulative NPV line
                    fig_cf.add_trace(go.Scatter(
                        x=cf_df["year"], y=cf_df["cumulative_npv"],
                        name="Cumulative NPV",
                        mode="lines+markers",
                        line=dict(color=_BSR["navy"], width=2.5),
                        marker=dict(size=4),
                        yaxis="y2",
                        hovertemplate=f"Cum. NPV: {_sym}%{{y:,.0f}}<extra></extra>",
                    ))

                    fig_cf.update_layout(
                        barmode="relative",
                        xaxis_title="Year",
                        yaxis_title=f"Annual Cash Flow ({_sym})",
                        yaxis2=dict(
                            title=f"Cumulative NPV ({_sym})",
                            overlaying="y", side="right",
                            showgrid=False,
                        ),
                        height=420,
                        margin=dict(l=20, r=20, t=30, b=20),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02),
                        hovermode="x unified",
                    )
                    # Zero line
                    fig_cf.add_hline(y=0, line_dash="solid", line_color="#ccc", line_width=0.8)
                    st.plotly_chart(fig_cf, use_container_width=True)

                with tab_table:
                    cf_display = cf_df.copy()
                    fmt_cols = [
                        "baseline_ead", "avoided_damage", "adapted_ead",
                        "capex", "opex", "net_cashflow", "net_cashflow_pv", "cumulative_npv",
                    ]
                    cf_display.columns = [
                        "Year", f"Baseline EAD ({_sym})", f"Avoided Damage ({_sym})",
                        f"Adapted EAD ({_sym})", f"Capex ({_sym})", f"Opex ({_sym})",
                        f"Net CF ({_sym})", f"Net CF PV ({_sym})", f"Cum. NPV ({_sym})",
                    ]
                    for col in cf_display.columns[1:]:
                        cf_display[col] = cf_display[col].apply(lambda x: f"{_sym}{x:,.0f}")
                    cf_display["Year"] = cf_display["Year"].astype(int)
                    st.dataframe(cf_display, use_container_width=True, hide_index=True, height=500)

                # ═════════════════════════════════════════════════════════════
                # SECTION 5 — Scenario Sensitivity
                # ═════════════════════════════════════════════════════════════
                if len(selected_scenarios) > 1:
                    st.divider()
                    st.markdown(
                        f"<h3 style='color:{_BSR['navy']};margin:0;'>Scenario Sensitivity</h3>",
                        unsafe_allow_html=True,
                    )
                    st.caption("How does the investment case change under different climate scenarios?")

                    sens_rows = []
                    for sc_id in selected_scenarios:
                        sc_label = SCENARIOS.get(sc_id, {}).get("label", sc_id)
                        sc_eads = _get_annual_eads(sel_asset_id, sc_id)
                        if not sc_eads:
                            continue
                        sc_npv_base = sum(
                            ead / (1 + adap_discount) ** (yr - 2025)
                            for yr, ead in sc_eads.items()
                        )
                        # Run first selected measure as representative
                        _first_mid = new_selected[0]
                        _first_m = next((x for x in measures if x["id"] == _first_mid), None)
                        if _first_m:
                            _haz_eads_sc = _get_annual_eads(sel_asset_id, sc_id, _first_m["hazard"])
                            if not _haz_eads_sc:
                                _haz_eads_sc = sc_eads
                            try:
                                _sc_r = calc_adaptation_npv(
                                    _first_mid, sel_asset_id, sel_asset.replacement_value,
                                    _haz_eads_sc, adap_discount,
                                    implementation_year=impl_year, capex_phases=capex_phases,
                                )
                                sens_rows.append({
                                    "Scenario": sc_label,
                                    f"NPV Baseline ({_sym})": sc_npv_base,
                                    f"NPV Avoided ({_sym})": _sc_r.npv_avoided_damages,
                                    f"Net NPV ({_sym})": _sc_r.net_npv,
                                    "CBR": _sc_r.cbr,
                                    "ROI (%)": _sc_r.roi_pct,
                                    "color": SCENARIOS.get(sc_id, {}).get("color", "#888"),
                                })
                            except Exception:
                                pass

                    if sens_rows:
                        sens_df = pd.DataFrame(sens_rows)

                        fig_sens = go.Figure()
                        fig_sens.add_trace(go.Bar(
                            x=sens_df["Scenario"],
                            y=sens_df[f"Net NPV ({_sym})"],
                            marker_color=sens_df["color"].tolist(),
                            text=[f"{_sym}{v:,.0f}" for v in sens_df[f"Net NPV ({_sym})"]],
                            textposition="outside",
                            hovertemplate=(
                                "<b>%{x}</b><br>"
                                f"Net NPV: {_sym}%{{y:,.0f}}<extra></extra>"
                            ),
                        ))
                        fig_sens.add_hline(y=0, line_dash="solid", line_color="#ccc")
                        fig_sens.update_layout(
                            title=f"Net NPV of {npv_results[0].measure_label} by Scenario",
                            yaxis_title=f"Net NPV ({_sym})",
                            height=340,
                            margin=dict(l=20, r=20, t=50, b=80),
                            xaxis_tickangle=-20,
                            showlegend=False,
                        )
                        st.plotly_chart(fig_sens, use_container_width=True)

                        # Display table
                        sens_display = sens_df.drop(columns=["color"]).copy()
                        for col in [f"NPV Baseline ({_sym})", f"NPV Avoided ({_sym})", f"Net NPV ({_sym})"]:
                            sens_display[col] = sens_display[col].apply(lambda x: _fmt_cur(x, _cur))
                        sens_display["CBR"] = sens_display["CBR"].apply(lambda x: f"{x:.2f}×")
                        sens_display["ROI (%)"] = sens_display["ROI (%)"].apply(lambda x: f"{x:.0f}%")
                        st.dataframe(sens_display, use_container_width=True, hide_index=True)

elif sel_asset:
    st.info("No annual damage data available for this asset/scenario. Run the damage calculation on the Results page.")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — Portfolio Adaptation Frontier (NPV-based)
# ═══════════════════════════════════════════════════════════════════════════════
st.divider()
st.markdown(
    f"<h3 style='color:{_BSR['navy']};margin:0;'>Portfolio Adaptation Frontier</h3>",
    unsafe_allow_html=True,
)
st.caption(
    "All measures ranked by NPV cost-benefit ratio. "
    "The frontier shows the optimal investment sequence across your entire portfolio."
)

if st.button("📊 Compute Portfolio Frontier", type="primary"):
    all_npv_results = []
    all_legacy_results = []

    for asset in assets:
        haz_eads_all = _get_hazard_annual_eads(asset.id, adap_scenario)
        total_eads = _get_annual_eads(asset.id, adap_scenario)

        # Fallback for assets without annual data
        if not total_eads and results:
            _am = [r for r in results if r.asset_id == asset.id and r.scenario_id == adap_scenario]
            for rm in _am:
                total_eads[rm.year] = rm.total_ead
                for haz, hr in rm.hazard_results.items():
                    haz_eads_all.setdefault(haz, {})[rm.year] = hr.ead

        if not total_eads:
            continue

        asset_measures = list_measures(asset_type=asset.asset_type)

        for m in asset_measures:
            haz_eads = haz_eads_all.get(m["hazard"], total_eads)
            if not haz_eads or sum(haz_eads.values()) == 0:
                continue
            try:
                ar = calc_adaptation_npv(
                    m["id"], asset.id, asset.replacement_value,
                    haz_eads, adap_discount,
                    implementation_year=impl_year, capex_phases=capex_phases,
                )
                all_npv_results.append(ar)
            except Exception:
                pass

            # Also compute legacy for export compatibility
            baseline_ead = haz_eads.get(2050, haz_eads.get(max(haz_eads), 0.0))
            if baseline_ead > 0:
                try:
                    lr = calc_adaptation(m["id"], asset.id, asset.replacement_value, baseline_ead, adap_discount)
                    all_legacy_results.append(lr)
                except Exception:
                    pass

    if all_npv_results:
        frontier = portfolio_adaptation_frontier_npv(all_npv_results)
        frontier_df = pd.DataFrame(frontier)

        # ── Frontier chart ────────────────────────────────────────────────
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=frontier_df["cumulative_capex"],
            y=frontier_df["cumulative_npv_avoided"],
            mode="lines+markers",
            name="NPV Risk Reduction Frontier",
            line=dict(color=_BSR["green"], width=2.5),
            fill="tozeroy",
            fillcolor="rgba(39,174,96,0.1)",
            text=frontier_df["measure_label"] + " | " + frontier_df["asset_id"],
            hovertemplate=(
                f"<b>%{{text}}</b><br>"
                f"Cumulative Capex: {_sym}%{{x:,.0f}}<br>"
                f"Cumulative NPV Avoided: {_sym}%{{y:,.0f}}<br>"
                "CBR: %{customdata:.2f}×"
                "<extra></extra>"
            ),
            customdata=frontier_df["cbr"],
        ))

        # Break-even line (45° where benefits = cost)
        _max_x = frontier_df["cumulative_capex"].max()
        fig.add_trace(go.Scatter(
            x=[0, _max_x], y=[0, _max_x],
            mode="lines", name="Break-even (CBR=1)",
            line=dict(color="#ccc", dash="dot", width=1.5),
            hoverinfo="skip",
        ))

        fig.update_layout(
            xaxis_title=f"Cumulative Capex ({_sym})",
            yaxis_title=f"Cumulative NPV Avoided Damages ({_sym})",
            height=420,
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Top measures table ────────────────────────────────────────────
        st.subheader("Top Adaptation Investments by NPV Return")
        top_df = frontier_df[[
            "measure_label", "asset_id", "capex", "npv_avoided", "net_npv", "cbr", "roi_pct",
        ]].head(15).copy()
        top_df.columns = [
            "Measure", "Asset ID", f"Capex ({_sym})",
            f"NPV Avoided ({_sym})", f"Net NPV ({_sym})", "CBR", "ROI (%)",
        ]
        top_df.index = range(1, len(top_df) + 1)
        top_df[f"Capex ({_sym})"] = top_df[f"Capex ({_sym})"].apply(lambda x: _fmt_cur(x, _cur))
        top_df[f"NPV Avoided ({_sym})"] = top_df[f"NPV Avoided ({_sym})"].apply(lambda x: _fmt_cur(x, _cur))
        top_df[f"Net NPV ({_sym})"] = top_df[f"Net NPV ({_sym})"].apply(lambda x: _fmt_cur(x, _cur))
        top_df["CBR"] = top_df["CBR"].apply(lambda x: f"{x:.2f}×")
        top_df["ROI (%)"] = top_df["ROI (%)"].apply(lambda x: f"{x:.0f}%")
        st.dataframe(top_df, use_container_width=True)

        # ── Portfolio summary ─────────────────────────────────────────────
        _pf_total_capex = sum(r.capex_total for r in all_npv_results)
        _pf_total_npv_avoided = sum(r.npv_avoided_damages for r in all_npv_results)
        _pf_total_cost = sum(r.total_cost for r in all_npv_results)
        _pf_net_npv = _pf_total_npv_avoided - _pf_total_cost
        _pf_cbr = _pf_total_npv_avoided / _pf_total_cost if _pf_total_cost > 0 else 0.0

        pm1, pm2, pm3, pm4 = st.columns(4)
        pm1.metric("Total Measures Evaluated", len(all_npv_results))
        pm2.metric("Total Capex (all measures)", _fmt_cur(_pf_total_capex, _cur))
        pm3.metric("Total Net NPV", _fmt_cur(_pf_net_npv, _cur))
        pm4.metric("Portfolio CBR", f"{_pf_cbr:.2f}×")

        # ── Export ────────────────────────────────────────────────────────
        st.divider()
        export_npv_df = pd.DataFrame([{
            "measure_id": r.measure_id,
            "measure": r.measure_label,
            "hazard": r.hazard,
            "asset_id": r.asset_id,
            "capex_total": r.capex_total,
            "npv_cost": r.total_cost,
            "npv_baseline_damages": r.npv_baseline_damages,
            "npv_avoided_damages": r.npv_avoided_damages,
            "net_npv": r.net_npv,
            "cbr": r.cbr,
            "roi_pct": r.roi_pct,
            "irr": r.irr,
            "discounted_payback": r.discounted_payback_year,
            "implementation_year": impl_year,
            "discount_rate": adap_discount,
        } for r in all_npv_results])

        col_a, col_b = st.columns(2)
        with col_a:
            try:
                # Use legacy results for the existing export format
                if all_legacy_results:
                    legacy_export_df = pd.DataFrame([{
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
                    } for r in all_legacy_results])
                    legacy_frontier = portfolio_adaptation_frontier(all_legacy_results)
                    legacy_frontier_df = pd.DataFrame(legacy_frontier)
                    xlsx_bytes = export_adaptation_xlsx(legacy_export_df, legacy_frontier_df)
                    st.download_button(
                        "⬇️ Export Adaptation Analysis (.xlsx)", data=xlsx_bytes,
                        file_name="adaptation_results.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
            except Exception as e:
                st.warning(f"XLSX export unavailable: {e}")
        with col_b:
            csv_bytes = export_npv_df.to_csv(index=False).encode()
            st.download_button(
                "⬇️ Export NPV Analysis (.csv)", csv_bytes,
                "adaptation_npv_results.csv", "text/csv",
            )
    else:
        st.info("No adaptation results generated (no assets with EAD > 0).")
