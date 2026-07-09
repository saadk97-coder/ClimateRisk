"""⑥ Results — consolidated financial impact across all four categories."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tr_common as T  # noqa: E402

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from engine.transition.transition_engine import DEFAULT_HORIZON  # noqa: E402

st.set_page_config(page_title="Results · " + T.APP_TITLE, page_icon="📊", layout="wide")
T.init_state()
T.page_header("Consolidated financial impact and decarbonisation-target gap.", pillar="Results")

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
wacc = float(st.session_state.get("tr_wacc", 0.09))
BASE = 2025


def _pv(series: dict) -> float:
    return sum(v / (1.0 + wacc) ** (y - BASE) for y, v in series.items())


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
st.subheader(f"Present value of transition impact (discount {wacc*100:.1f}%)")
srows = []
for sc, res in results.items():
    pv_cost = sum(_pv(r.annual_total_cost_usd) for r in res)
    pv_imp = sum(_pv(r.annual_impairment_usd) for r in res)
    srows.append({
        "Scenario": T.scenario_label(sc),
        f"PV transition cost ({sym})": pv_cost,
        f"PV stranded impairment ({sym})": pv_imp,
        f"PV total ({sym})": pv_cost + pv_imp,
    })
sdf = pd.DataFrame(srows)
show = sdf.copy()
for c in show.columns[1:]:
    show[c] = show[c].map(T.fmt_money)
st.dataframe(show, use_container_width=True, hide_index=True)

fig = px.bar(sdf, x="Scenario", y=[f"PV transition cost ({sym})", f"PV stranded impairment ({sym})"],
             barmode="stack", title="PV of transition cost + stranded impairment")
fig.update_layout(height=380, legend=dict(orientation="h", y=-0.25), margin=dict(t=50, b=10))
st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# Category (layer) attribution of PV
# ===========================================================================
st.subheader("Attribution by TCFD category")
sc_att = st.selectbox("Scenario", scenarios, format_func=T.scenario_label, key="att_sc")
res = results.get(sc_att, [])
cat_map = [
    ("Policy & Legal (L1)", "L1_carbon_opex"),
    ("Technology (L2 revenue)", "L2_revenue_erosion"),
    ("Market (L3 network)", "L3_network_input_cost"),
    ("Reputation (L4)", "L4_revenue_modifier"),
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
# Decarbonisation target
# ===========================================================================
st.subheader("Decarbonisation target")
c1, c2 = st.columns([1, 2])
with c1:
    tgt = st.number_input("Net-zero target year (Scope 1+2)", 2030, 2060,
                          int(st.session_state.get("tr_target_year", 2050)), 1)
    st.session_state["tr_target_year"] = tgt
with c2:
    span = max(tgt - BASE, 1)
    annual_cut = (s1 + s2) / span
    st.metric("Required annual Scope 1+2 reduction (linear to target)", f"{annual_cut:,.0f} tCO₂/yr")
    st.caption(f"From {s1+s2:,.0f} tCO₂ today to zero by {tgt} implies a straight-line cut of "
               f"~{annual_cut:,.0f} tCO₂ each year. Compare against the carbon-cost trajectory on "
               "the Policy & Legal page to see the cost of *not* decarbonising.")

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
                "L3_network": r.layer_breakdown["L3_network_input_cost"].get(y, 0.0),
                "L4_reputation": r.layer_breakdown["L4_revenue_modifier"].get(y, 0.0),
                "total_cf_cost": r.annual_total_cost_usd.get(y, 0.0),
                "impairment": r.annual_impairment_usd.get(y, 0.0),
            })
st.download_button("Download full results CSV", pd.DataFrame(exp).to_csv(index=False),
                   file_name="transition_results.csv", mime="text/csv")

T.disclaimer()
