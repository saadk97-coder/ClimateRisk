"""⑧ Audit — full calculation trace for one entity × scenario × year."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tr_common as T  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from engine.transition.transition_engine import DEFAULT_HORIZON  # noqa: E402
from engine.transition.carbon_pricing import abatement_index  # noqa: E402
from engine.transition.cc_exposure import ROUTE_WACC  # noqa: E402

st.set_page_config(page_title="Audit · " + T.APP_TITLE, page_icon="🧾", layout="wide")
T.init_state()
T.page_header("Every headline number traced to its inputs, formula and data vintage.", pillar="Audit trail")

active = T.portfolio_gate()
scenarios = T.sidebar_settings()
if not scenarios:
    st.info("Pick scenarios in the sidebar.")
    st.stop()
results = T.run_engine(active, scenarios)
if not results:
    st.error("No results — check Data Entry.")
    st.stop()
sym = T.sym()

c1, c2, c3 = st.columns(3)
with c1:
    aid = st.selectbox("Entity", [a.id for a in active],
                       format_func=lambda x: next((f"{a.id} — {a.name}" for a in active if a.id == x), x))
with c2:
    sc = st.selectbox("Scenario", scenarios, format_func=T.scenario_label)
with c3:
    yr = st.select_slider("Year", options=list(DEFAULT_HORIZON), value=2040)

asset = next(a for a in active if a.id == aid)
res = next((r for r in results.get(sc, []) if r.asset_id == aid), None)
if res is None:
    st.stop()


def trace(rows):
    st.dataframe(pd.DataFrame(rows, columns=["Quantity", "Value", "How it is computed"]),
                 use_container_width=True, hide_index=True)


st.markdown(f"### Layer 1 — Policy &amp; Legal (carbon cost), {yr}")
l1 = next((x for x in res.layer1_results if x.year == yr), None)
if l1:
    m = abatement_index(asset.decarb_target_year, asset.decarb_residual_pct, [yr])[yr]
    trace([
        ("NGFS region", l1.ngfs_region, f"get_ngfs_region({asset.region})"),
        ("Carbon price", f"${l1.carbon_price_usd_per_t:,.1f}/tCO₂", "NGFS Phase V REMIND, interpolated to year"),
        ("Abatement multiplier", f"{m:.3f}", f"linear path to net-zero {asset.decarb_target_year or '— (none)'}"),
        ("Priced fraction", f"{asset.priced_emissions_fraction:.2f}", "net of free allocation"),
        ("Scope 1+2 (effective)", f"{(asset.scope1_emissions_tco2+asset.scope2_emissions_tco2)*m:,.0f} tCO₂",
         "(S1+S2) × abatement multiplier"),
        ("Pass-through", f"{l1.pass_through*100:.0f}%", f"{l1.notes or 'sector median'}"),
        ("Gross cost", T.fmt_money(l1.gross_cost_usd), "effective S1+2 × priced fraction × price"),
        ("Absorbed (margin hit)", T.fmt_money(l1.absorbed_cost_usd), "gross × (1 − pass-through)"),
        ("Passed-through → L3", T.fmt_money(l1.passed_through_usd), "gross × pass-through"),
        ("Scope-3 indirect", T.fmt_money(l1.scope3_indirect_usd), "S3 × price × (1 − PT); 0 if scope3_mode=auto & L3 on"),
        ("Net carbon OpEx", T.fmt_money(l1.net_carbon_opex_usd), "absorbed + scope-3 indirect"),
    ])

st.markdown("### Layer 2 — Technology (stranding)")
l2 = res.layer2_result
if l2:
    trace([
        ("Incumbent / challenger", f"{l2.incumbent_tech} → {l2.challenger_tech or '—'}", "sector taxonomy"),
        ("Crossover / trigger year", l2.crossover_year or "none", "challenger ≤ incumbent cost, or demand < 0.5"),
        ("Demand index @2050", f"{(l2.revenue_index or {}).get(2050, 1.0):.2f}", "sector pathway"),
        ("Stranded fraction @2050", f"{l2.stranded_fraction_2050*100:.1f}%", "logistic(2050) × cap ÷ value"),
        (f"Impairment @{yr}", T.fmt_money(l2.annual_impairment_usd.get(yr, 0.0)),
         "(logistic(y) − logistic(y−1)) × cap"),
        ("Cumulative impairment", T.fmt_money(sum(l2.annual_impairment_usd.values())), "Σ annual impairment"),
    ])

st.markdown(f"### Layer 3 — Market (network), {yr}")
l3 = next((x for x in res.layer3_results if x.year == yr), None)
if l3:
    trace([
        ("Direct (own) shock", f"{l3.direct_carbon_shock:.5f}", "own-sector carbon shock / output"),
        ("Propagated input shock", f"{l3.propagated_input_shock:.5f}", "Σ L[i,j]·sᵢ − own (Leontief)"),
        ("Indirect input cost", T.fmt_money(l3.total_indirect_cost_usd), "propagated shock × revenue"),
    ])
    if l3.top_upstream_sources:
        st.caption("Top upstream sources")
        st.dataframe(pd.DataFrame([(T.sector_label(s), T.fmt_money(v)) for s, v in l3.top_upstream_sources],
                                  columns=["Upstream sector", f"Contribution ({sym})"]),
                     use_container_width=True, hide_index=True)

st.markdown(f"### Layer 4 — Reputation (CCExposure), {yr}")
l4 = res.layer4_result
if l4:
    routing = st.session_state.get("tr_l4_routing")
    trace([
        ("CCE opportunity / regulatory / physical",
         f"{l4.cce_opportunity:.2f} / {l4.cce_regulatory:.2f} / {l4.cce_physical:.2f}",
         "sector median × scenario modifier"),
        ("Credit spread Δ", f"{l4.credit_spread_premium_bps:.0f} bps", "12·reg + 6·phys"),
        ("Equity premium Δ", f"{l4.equity_premium_bps:.0f} bps", "50·(opp+reg+phys)"),
        ("Revenue growth Δ", f"{l4.revenue_growth_modifier_bps:.0f} bps", "35·opp − 25·reg"),
        (f"Revenue modifier @{yr}", T.fmt_money(l4.annual_revenue_modifier_usd.get(yr, 0.0)),
         "applied to CFs" if routing != ROUTE_WACC else "zeroed (routed to WACC)"),
        ("WACC premium", f"{res.wacc_premium_bps:.0f} bps", "credit + equity, only if routed to WACC"),
    ])

st.divider()
st.markdown(f"### Total, {yr}")
trace([
    ("Total cash-flow cost", T.fmt_money(res.annual_total_cost_usd.get(yr, 0.0)),
     "L1 + L2 revenue erosion + L3 + L4 (revenue modifier)"),
    ("Impairment (balance sheet, separate)", T.fmt_money(res.annual_impairment_usd.get(yr, 0.0)),
     "L2 stranding — not in the cash-flow total"),
])

T.disclaimer()
