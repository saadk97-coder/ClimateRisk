"""⑩ Abatement (MACC) — the decarbonise-vs-pay decision per entity."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tr_common as T  # noqa: E402

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from engine.transition.macc import evaluate_macc, macc_steps
from engine.transition.carbon_pricing import get_carbon_price  # noqa: E402
from engine.transition.data_loader import get_ngfs_region  # noqa: E402

st.set_page_config(page_title="Abatement · " + T.APP_TITLE, page_icon="🔧", layout="wide")
T.init_state()
T.page_header("Marginal abatement cost curves — is it cheaper to decarbonise or pay the price?",
              pillar="Decision support")

active = T.portfolio_gate()
scenarios = T.sidebar_settings()
if not scenarios:
    st.info("Pick scenarios in the sidebar.")
    st.stop()

c1, c2 = st.columns(2)
with c1:
    sc = st.selectbox("Scenario", scenarios, format_func=T.scenario_label)
with c2:
    yr = st.select_slider("Year", options=list(range(2025, 2051, 5)), value=2040)

# ===========================================================================
# Portfolio decarbonise-vs-pay summary at this price point
# ===========================================================================
st.subheader("Decarbonise vs pay — portfolio")
rows = []
tot_abate_cost = tot_avoided = tot_residual = 0.0
for a in active:
    e12 = a.scope1_emissions_tco2 + a.scope2_emissions_tco2
    if e12 <= 0:
        continue
    price = get_carbon_price(sc, yr, get_ngfs_region(a.region))
    r = evaluate_macc(a.sector, e12, price)
    tot_abate_cost += r.abatement_cost_usd
    tot_avoided += r.carbon_cost_avoided_usd
    tot_residual += r.residual_carbon_cost_usd
    rows.append({
        "Entity": a.id, "Sector": T.sector_label(a.sector),
        "Carbon price (USD/t)": round(r.carbon_price, 0),
        "Cost-effective abatement": f"{r.cost_effective_frac*100:.0f}%",
        f"Abatement spend ({T.sym()})": T.fmt_money(r.abatement_cost_usd),
        f"Carbon cost avoided ({T.sym()})": T.fmt_money(r.carbon_cost_avoided_usd),
        f"Net benefit ({T.sym()})": T.fmt_money(r.net_benefit_usd),
        f"Residual carbon cost ({T.sym()})": T.fmt_money(r.residual_carbon_cost_usd),
    })
if rows:
    m1, m2, m3 = st.columns(3)
    m1.metric("Portfolio abatement spend", T.fmt_money(tot_abate_cost))
    m2.metric("Carbon cost avoided", T.fmt_money(tot_avoided))
    m3.metric("Net benefit of abating", T.fmt_money(tot_avoided - tot_abate_cost))
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
st.caption(f"At the {yr} carbon price, measures with marginal cost ≤ price are cost-effective. "
           "Net benefit > 0 means decarbonising beats paying. Compare with the target you set on "
           "Data Entry — the MACC shows the *economically optimal* level of abatement.")

# ===========================================================================
# MACC curve for a selected entity
# ===========================================================================
st.subheader("Marginal abatement cost curve")
ent = st.selectbox("Entity", [a.id for a in active],
                   format_func=lambda x: next((f"{a.id} — {T.sector_label(a.sector)}" for a in active if a.id == x), x))
a = next(x for x in active if x.id == ent)
e12 = a.scope1_emissions_tco2 + a.scope2_emissions_tco2
price = get_carbon_price(sc, yr, get_ngfs_region(a.region))
steps = macc_steps(a.sector, e12 if e12 > 0 else 1.0)

fig = go.Figure()
for sstep in steps:
    fig.add_shape(type="rect", x0=sstep["from_frac"] * 100, x1=sstep["to_frac"] * 100,
                  y0=0, y1=sstep["cost_usd_per_tco2"],
                  fillcolor="#2A7" if sstep["cost_usd_per_tco2"] <= price else "#c9922e",
                  opacity=0.55, line=dict(color="#fff", width=1))
    fig.add_annotation(x=(sstep["from_frac"] + sstep["to_frac"]) * 50, y=sstep["cost_usd_per_tco2"],
                       text=sstep["measure"], showarrow=False, yshift=8, font=dict(size=10))
fig.add_hline(y=price, line_dash="dash", line_color="#F4721A",
              annotation_text=f"carbon price {yr} = ${price:,.0f}/t")
fig.update_layout(height=420, xaxis_title="Cumulative abatement (% of Scope 1+2)",
                  yaxis_title="Marginal cost (USD/tCO₂)", margin=dict(t=20, b=10),
                  title=f"{T.sector_label(a.sector)} MACC — measures below the price line are cost-effective")
st.plotly_chart(fig, use_container_width=True)
st.caption("Green bars: cheaper than the carbon price (worth doing). Amber: costlier than paying — "
           "abate only under policy mandate or a higher price. Source: IPCC AR6 WG3-informed screening curves.")

T.disclaimer()
