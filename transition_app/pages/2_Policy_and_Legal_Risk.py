"""② Policy & Legal Risk — TCFD transition category, driven by Layer 1 (carbon cost)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tr_common as T  # noqa: E402

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from engine.transition.transition_engine import DEFAULT_HORIZON  # noqa: E402

st.set_page_config(page_title="Policy & Legal · " + T.APP_TITLE, page_icon="⚖️", layout="wide")
T.init_state()
T.page_header(
    "Carbon pricing (taxes, ETS), efficiency mandates and litigation exposure. "
    "Quantified by **Layer 1** — direct carbon cost and pass-through.",
    pillar="Policy & Legal",
)

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

# --- Headline --------------------------------------------------------------
st.subheader("Net carbon cost (OpEx) over time")
rows = []
for sc, res in results.items():
    for y in DEFAULT_HORIZON:
        rows.append({"Year": y, "Scenario": T.scenario_label(sc),
                     f"Net carbon OpEx ({sym})":
                        sum(r.layer_breakdown.get("L1_carbon_opex", {}).get(y, 0.0) for r in res)})
fig = px.line(pd.DataFrame(rows), x="Year", y=f"Net carbon OpEx ({sym})", color="Scenario",
              title="Portfolio Layer-1 carbon cost (absorbed margin + Scope-3 indirect)")
fig.update_layout(height=400, legend=dict(orientation="h", y=-0.2), margin=dict(t=50, b=10))
st.plotly_chart(fig, use_container_width=True)

# --- Per-entity decomposition ----------------------------------------------
st.subheader("Carbon-cost decomposition")
c1, c2 = st.columns([1, 1])
with c1:
    sc = st.selectbox("Scenario", scenarios, format_func=T.scenario_label)
with c2:
    yr = st.select_slider("Year", options=list(DEFAULT_HORIZON), value=2040)

res = results.get(sc, [])
rows = []
for ar in res:
    l1 = next((x for x in ar.layer1_results if x.year == yr), None)
    if not l1:
        continue
    rows.append({
        "Entity": ar.asset_id, "Sector": T.sector_label(ar.sector),
        "NGFS region": l1.ngfs_region,
        "Carbon price (USD/t)": round(l1.carbon_price_usd_per_t, 1),
        "Pass-through": f"{l1.pass_through*100:.0f}%",
        f"Gross ({sym})": T.fmt_money(l1.gross_cost_usd),
        f"Absorbed — margin hit ({sym})": T.fmt_money(l1.absorbed_cost_usd),
        f"Passed-through → market ({sym})": T.fmt_money(l1.passed_through_usd),
        f"Net carbon OpEx ({sym})": T.fmt_money(l1.net_carbon_opex_usd),
    })
if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
st.caption(
    "**Absorbed** cost compresses the firm's own margin (the policy hit). **Passed-through** "
    "cost is pushed to customers and re-enters as the Market-risk supply-chain shock (Layer 3) — "
    "counted there, not twice. Net carbon OpEx = absorbed + Scope-3 indirect."
)

# --- Carbon price context --------------------------------------------------
with st.expander("NGFS carbon-price trajectories driving this (USD/tCO₂)"):
    cp = T.load_carbon_prices()
    region = st.selectbox("Region band", ["advanced", "emerging", "rest_of_world"])
    prows = []
    for sc_id in scenarios:
        scen = cp["scenarios"].get(sc_id, {})
        for y_str, v in scen.get(region, {}).items():
            prows.append({"Scenario": T.scenario_label(sc_id), "Year": int(y_str), "USD/tCO₂": float(v)})
    if prows:
        figp = px.line(pd.DataFrame(prows), x="Year", y="USD/tCO₂", color="Scenario")
        figp.update_layout(height=340, margin=dict(t=20, b=10))
        st.plotly_chart(figp, use_container_width=True)

# --- Qualitative litigation / regulatory note ------------------------------
st.subheader("Litigation & regulatory narrative (qualitative)")
gov = st.session_state.get("tr_governance", {})
gov["policy_legal_note"] = st.text_area(
    "Known or anticipated regulatory / litigation exposure not captured by carbon price",
    value=gov.get("policy_legal_note", ""),
    placeholder="e.g. pending greenwashing litigation; jurisdiction-specific ETS expansion; "
                "product energy-efficiency mandate from 2027.",
    height=90,
)
if st.button("💾 Save note"):
    st.session_state["tr_governance"] = gov
    st.success("Saved.")

T.disclaimer()
