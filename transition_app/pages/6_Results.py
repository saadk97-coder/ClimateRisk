"""⑥ Results — consolidated financial impact across all four categories."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tr_common as T  # noqa: E402

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from engine.transition.transition_engine import DEFAULT_HORIZON  # noqa: E402

st.set_page_config(page_title="Results · " + T.APP_TITLE, page_icon="📊", layout="wide")
T.init_state()
T.page_header("Consolidated financial impact and decarbonisation-target gap.", pillar="Results")

active = T.portfolio_gate()
T.portfolio_warnings_banner()
scenarios = T.sidebar_settings()
if not scenarios:
    st.info("Pick scenarios in the sidebar.")
    st.stop()

results = T.run_engine(active, scenarios)
if not results:
    st.error("No results — check Data Entry.")
    st.stop()
sym = T.sym()
wacc = T.real_discount()   # P2 — real cash flows discounted at a real rate
BASE = 2025


def _pv(series: dict) -> float:
    # End-of-year convention (y − BASE + 1), consistent with the engine PV helpers.
    return sum(v / (1.0 + wacc) ** (y - BASE + 1) for y, v in series.items())


# ===========================================================================
# Emissions summary
# ===========================================================================
st.subheader("Emissions (Scope 1/2/3)")
s1 = sum(a.scope1_emissions_tco2 for a in active)
s2 = sum(a.scope2_emissions_tco2 for a in active)
s3 = sum(a.scope3_emissions_tco2 for a in active)
e1, e2, e3, e4 = st.columns(4)
e1.metric("Scope 1 (tCO₂)", f"{s1:,.0f}")
e2.metric("Scope 2 (tCO₂)", f"{s2:,.0f}")
e3.metric("Scope 3 (tCO₂)", f"{s3:,.0f}")
e4.metric("Scope 1+2 (tCO₂)", f"{s1+s2:,.0f}")

# ===========================================================================
# PV of transition impact by scenario
# ===========================================================================
st.subheader(f"Present value of transition impact (real discount {wacc*100:.1f}%)")
srows = []
for sc, res in results.items():
    pv_cost = sum(_pv(r.annual_total_cost_usd) for r in res)
    pv_imp = sum(_pv(r.annual_impairment_usd) for r in res)
    srows.append({
        "Scenario": T.scenario_label(sc),
        f"PV transition cost ({sym})": pv_cost,
        f"PV stranded impairment ({sym})": pv_imp,
    })
sdf = pd.DataFrame(srows)
show = sdf.copy()
for c in show.columns[1:]:
    show[c] = show[c].map(T.fmt_money)
st.dataframe(show, use_container_width=True, hide_index=True)

# P1 — the two are ALTERNATIVE LENSES on the same demand-collapse loss, not additive.
# Cash-flow cost carries it through eroded revenue; stranded impairment is the PV writedown
# of the same future cash flows. Shown side-by-side (grouped), never summed.
fig = px.bar(sdf, x="Scenario", y=[f"PV transition cost ({sym})", f"PV stranded impairment ({sym})"],
             barmode="group", title="PV impact — two lenses (do not add)")
fig.update_layout(height=380, legend=dict(orientation="h", y=-0.25), margin=dict(t=50, b=10))
st.plotly_chart(fig, use_container_width=True)
st.caption("⚠️ **Not additive.** Cash-flow transition cost and stranded impairment are two lenses on "
           "the same demand-collapse loss — the impairment is the PV writedown of the very cash flows "
           "the erosion already reflects. Read them as alternatives, never as a combined total.")

# ===========================================================================
# Firm-level roll-up (diversified multi-line firms)
# ===========================================================================
if any(getattr(a, "firm_id", "") for a in active):
    from engine.transition.transition_engine import firm_rollup  # noqa: E402
    st.subheader("Firm-level roll-up (diversified companies)")
    fsc = st.selectbox("Scenario", scenarios, format_func=T.scenario_label, key="firm_sc")
    rolls = firm_rollup(results.get(fsc, []), active)
    frows = []
    for fid, fr in sorted(rolls.items()):
        if fr.n_lines < 2 and fid == fr.business_lines[0]:
            continue   # skip standalone single-line entities
        frows.append({
            "Firm": fid, "Business lines": fr.n_lines,
            "Sectors": ", ".join(T.sector_label(s) for s in fr.sectors),
            "Regions": ", ".join(fr.regions),
            f"PV transition cost ({sym})": T.fmt_money(_pv(fr.annual_total_cost_usd)),
            f"PV impairment ({sym})": T.fmt_money(_pv(fr.annual_impairment_usd)),
        })
    if frows:
        st.dataframe(pd.DataFrame(frows), use_container_width=True, hide_index=True)
        st.caption("A diversified firm is the **independent sum** of its business lines — each line "
                   "keeps its own sector- and region-specific positioning (correct: a steel division and "
                   "a data-centre division transition differently). ⚠️ Group-level correlation, "
                   "cross-subsidy, shared capital and a single optimised group plan are **not** modelled.")

# ===========================================================================
# Uncertainty (Monte-Carlo)
# ===========================================================================
st.subheader("Uncertainty — Monte-Carlo")
st.caption("Re-runs the four-layer model over many draws, perturbing the carbon-price path "
           "(log-normal), pass-through (normal) and network substitution σ (uniform). Turns "
           "single-point estimates into a P5–P95 range.")
st.caption("⚠️ **The P5–P95 range is a *conditional floor*, not full uncertainty.** It is "
           "conditional on the selected NGFS scenario and varies only the three sampled "
           "parameters — it excludes scenario/policy-path uncertainty, the L2 stranding "
           "trigger-year and the demand pathway. Widen with the Sensitivity tornado below "
           "(cost **and** impairment views) for the trigger-year and pathway drivers.")
uc1, uc2, uc3 = st.columns([2, 2, 1])
with uc1:
    mc_sc = st.selectbox("Scenario", scenarios, format_func=T.scenario_label, key="mc_sc")
with uc2:
    draws = st.select_slider("Draws", options=[100, 200, 400, 800], value=400)
with uc3:
    st.write("")
    run_mc = st.button("▶ Run", use_container_width=True)

if run_mc:
    from engine.transition.uncertainty import run_monte_carlo, MCConfig  # noqa: E402
    from engine.transition.cc_exposure import ROUTE_WACC  # noqa: E402
    with st.spinner(f"Running {draws} draws…"):
        mc = run_monte_carlo(
            active, mc_sc, discount_rate=wacc,
            layer4_routing=st.session_state.get("tr_l4_routing", ROUTE_WACC),
            enable_layers=tuple(st.session_state.get("tr_layers", [1, 2, 3, 4])),
            scope3_mode=st.session_state.get("tr_scope3_mode", "auto"),
            config=MCConfig(draws=draws),
        )
    st.session_state["mc_result"] = {
        "scenario": mc_sc, "draws": draws, "summary": mc.summary(),
        "cost_samples": mc.pv_cost.tolist(),
    }

mc_res = st.session_state.get("mc_result")
if mc_res:
    sc_cost = mc_res["summary"]["transition_cost"]
    st.markdown(f"**{T.scenario_label(mc_res['scenario'])}** · {mc_res['draws']} draws · "
                "PV of transition cost")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("P5 (optimistic)", T.fmt_money(sc_cost["p5"]))
    q2.metric("P50 (median)", T.fmt_money(sc_cost["p50"]))
    q3.metric("P95 (conditional floor)", T.fmt_money(sc_cost["p95"]))
    q4.metric("Base (deterministic)", T.fmt_money(sc_cost["base"]))
    hist = px.histogram(pd.DataFrame({f"PV transition cost ({sym})": mc_res["cost_samples"]}),
                        x=f"PV transition cost ({sym})", nbins=40,
                        title="Distribution of PV transition cost")
    hist.add_vline(x=sc_cost["p50"], line_dash="dash", line_color="#F4721A",
                   annotation_text="P50")
    hist.add_annotation(xref="paper", yref="paper", x=0.5, y=1.12, showarrow=False,
                        font=dict(size=11, color="#B33"),
                        text="Conditional floor — excludes scenario / model-form / data uncertainty")
    hist.update_layout(height=360, margin=dict(t=70, b=10), showlegend=False)
    st.plotly_chart(hist, use_container_width=True)

# ===========================================================================
# Sensitivity (tornado) — which assumption drives the number?
# ===========================================================================
st.subheader("Sensitivity — what drives the number?")
st.caption("One-at-a-time swing of each assumption (others held at base). The widest bar is the "
           "assumption your result is most exposed to — where better data pays off most.")
tcol1, tcol2 = st.columns(2)
with tcol1:
    tsc = st.selectbox("Scenario", scenarios, format_func=T.scenario_label, key="tornado_sc")
with tcol2:
    tgt_label = st.radio("Target", ["Cash-flow cost", "Stranded impairment"],
                         horizontal=True, key="tornado_target",
                         help="Cost view swings price/pass-through drivers; impairment view "
                              "swings the L2 trigger-year, stranding slope and base — the "
                              "assumptions that dominate stranding.")
tgt = "impairment" if tgt_label.startswith("Stranded") else "cost"
fx = T.fx_to_usd()  # USD → reporting currency divisor for chart axes
from engine.transition.sensitivity import tornado  # noqa: E402
from engine.transition.cc_exposure import ROUTE_WACC as _RW  # noqa: E402
with st.spinner("Computing sensitivities…"):
    tor = tornado(active, tsc, discount_rate=wacc,
                  layer4_routing=st.session_state.get("tr_l4_routing", _RW),
                  enable_layers=tuple(st.session_state.get("tr_layers", [1, 2, 3, 4])),
                  scope3_mode=st.session_state.get("tr_scope3_mode", "auto"),
                  target=tgt)
base_pv = tor["base_pv"]
bars = tor["bars"]
_axis_label = "PV stranded impairment" if tgt == "impairment" else "PV transition cost"
if bars:
    fig = go.Figure()
    for b in reversed(bars):  # widest at top
        lo, hi = min(b.low_pv, b.high_pv), max(b.low_pv, b.high_pv)
        fig.add_trace(go.Bar(
            y=[b.driver], x=[(hi - lo) / fx], base=[lo / fx], orientation="h",
            marker_color="#4f8cc9", showlegend=False,
            hovertemplate=f"{b.low_label}: %{{base:,.0f}}<br>{b.high_label}: {hi/fx:,.0f}<extra></extra>"))
    fig.add_vline(x=base_pv / fx, line_dash="dash", line_color="#F4721A",
                  annotation_text="base")
    fig.update_layout(height=300, margin=dict(t=30, b=10),
                      xaxis_title=f"{_axis_label} ({sym})",
                      title=f"Sensitivity — {T.scenario_label(tsc)} · {tgt_label}")
    st.plotly_chart(fig, use_container_width=True)
    top = bars[0]
    st.caption(f"Most influential: **{top.driver}** (swing {T.fmt_money(top.swing)}). "
               "Prioritise firming up this input.")

# ===========================================================================
# Category (layer) attribution of PV
# ===========================================================================
st.subheader("Attribution by TCFD category")
sc_att = st.selectbox("Scenario", scenarios, format_func=T.scenario_label, key="att_sc")
res = results.get(sc_att, [])
cat_map = [
    ("Policy & Legal (L1)", "L1_carbon_opex"),
    ("Technology (L2 revenue)", "L2_revenue_erosion"),
    ("Technology (L2 pivot capex)", "L2_transition_capex"),
    ("Technology (L2 product use-phase)", "L2_product_use_phase"),
    ("Market (L3 network)", "L3_network_input_cost"),
    ("Reputation (L4)", "L4_revenue_modifier"),
    ("Financed emissions (financials)", "Financed_emissions_exposure"),
]
arows = []
for label, key in cat_map:
    pv = sum(_pv(r.layer_breakdown.get(key, {})) for r in res)
    arows.append({"Category": label, f"PV cash-flow cost ({sym})": pv})
# Technology also carries the separate impairment stream
imp_pv = sum(_pv(r.annual_impairment_usd) for r in res)
arows.append({"Category": "Technology (L2 impairment)", f"PV cash-flow cost ({sym})": imp_pv})
adf = pd.DataFrame(arows)
figa = px.bar(adf, x="Category", y=f"PV cash-flow cost ({sym})",
              title=f"PV attribution — {T.scenario_label(sc_att)}")
figa.update_layout(height=380, margin=dict(t=50, b=10))
st.plotly_chart(figa, use_container_width=True)
st.caption("L2 impairment is a balance-sheet value loss, shown alongside the cash-flow channels "
           "for completeness but not summed into the cash-flow total.")

# ===========================================================================
# Decarbonisation target (per-asset, now driving Layer 1)
# ===========================================================================
st.subheader("Decarbonisation targets")
from engine.transition.carbon_pricing import abatement_index  # noqa: E402

n_target = sum(1 for a in active if a.decarb_target_year)
modelled_2050 = 0.0
for a in active:
    s12 = a.scope1_emissions_tco2 + a.scope2_emissions_tco2
    m = abatement_index(a.decarb_target_year, a.decarb_residual_pct, [2050])[2050] \
        if a.decarb_target_year else 1.0
    modelled_2050 += s12 * m
cut_pct = (1 - modelled_2050 / (s1 + s2)) * 100 if (s1 + s2) > 0 else 0.0

t1, t2, t3 = st.columns(3)
t1.metric("Entities with a net-zero target", f"{n_target}/{len(active)}")
t2.metric("Modelled Scope 1+2 in 2050", f"{modelled_2050:,.0f} tCO₂")
t3.metric("Portfolio reduction by 2050", f"{cut_pct:.0f}%")
st.caption(
    "Targets are set per entity on **① Data Entry** (Net-zero target yr). They now feed "
    "**Layer 1** directly: an entity on a decarbonisation path pays carbon cost only on its "
    "declining residual emissions, so abatement is rewarded rather than assumed away. "
    "Entities with no target hold emissions flat (legacy behaviour)."
)

# ===========================================================================
# Export
# ===========================================================================
st.subheader("Export")
exp = []
for sc, res in results.items():
    for r in res:
        for y in DEFAULT_HORIZON:
            exp.append({
                "scenario": sc, "entity": r.asset_id, "sector": r.sector, "year": y,
                "L1_carbon": r.layer_breakdown["L1_carbon_opex"].get(y, 0.0),
                "L2_revenue": r.layer_breakdown["L2_revenue_erosion"].get(y, 0.0),
                "L2_pivot_capex": r.layer_breakdown.get("L2_transition_capex", {}).get(y, 0.0),
                "L2_product_use_phase": r.layer_breakdown.get("L2_product_use_phase", {}).get(y, 0.0),
                "L3_network": r.layer_breakdown["L3_network_input_cost"].get(y, 0.0),
                "L4_reputation": r.layer_breakdown["L4_revenue_modifier"].get(y, 0.0),
                "financed_emissions": r.layer_breakdown.get("Financed_emissions_exposure", {}).get(y, 0.0),
                "total_cf_cost": r.annual_total_cost_usd.get(y, 0.0),
                "impairment": r.annual_impairment_usd.get(y, 0.0),
            })
d1, d2 = st.columns(2)
with d1:
    st.download_button("⬇ Full results (CSV)", pd.DataFrame(exp).to_csv(index=False),
                       file_name="transition_results.csv", mime="text/csv",
                       use_container_width=True)
with d2:
    xlsx = T.build_results_xlsx(results, active, scenarios, wacc)
    st.download_button("⬇ Report workbook (XLSX)", xlsx,
                       file_name="transition_report.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True,
                       help="Summary, annual detail, portfolio and a run manifest with provenance.")

T.disclaimer()
