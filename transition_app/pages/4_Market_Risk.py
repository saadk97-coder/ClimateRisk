"""④ Market Risk — TCFD transition category, driven by Layer 3 (network) + demand shift."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tr_common as T  # noqa: E402

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from engine.transition.transition_engine import DEFAULT_HORIZON  # noqa: E402

st.set_page_config(page_title="Market · " + T.APP_TITLE, page_icon="📉", layout="wide")
T.init_state()
T.page_header(
    "Shifting demand, input-cost pressure through the supply chain, and devaluation of "
    "high-carbon assets. Quantified by **Layer 3** (network) plus demand-driven stranding.",
    pillar="Market",
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

sc = st.selectbox("Scenario", scenarios, format_func=T.scenario_label)
res = results.get(sc, [])

# ===========================================================================
# A. Demand shift (sector pathways)
# ===========================================================================
st.subheader("A. Demand shift by sector")
st.caption("Sector production-volume index (2025 = 1.0). A falling index is contracting "
           "market demand — the market driver of asset devaluation.")
rows = []
for ar in res:
    ri = ar.layer2_result.revenue_index if ar.layer2_result else {}
    for y in DEFAULT_HORIZON:
        if y in ri:
            rows.append({"Year": y, "Entity": f"{ar.asset_id} ({T.sector_label(ar.sector)})",
                         "Demand index": ri[y]})
if rows:
    fig = px.line(pd.DataFrame(rows), x="Year", y="Demand index", color="Entity",
                  title=f"Demand pathway — {T.scenario_label(sc)}")
    fig.add_hline(y=0.5, line_dash="dot", line_color="#B33",
                  annotation_text="0.5 = demand-collapse stranding threshold")
    fig.update_layout(height=380, legend=dict(orientation="h", y=-0.3), margin=dict(t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)

# ===========================================================================
# B. Supply-chain input-cost pressure (Layer 3)
# ===========================================================================
st.subheader("B. Supply-chain input-cost pressure (Layer 3)")
tot_rows = []
for scx, r in results.items():
    for y in DEFAULT_HORIZON:
        tot_rows.append({"Year": y, "Scenario": T.scenario_label(scx),
                         f"Indirect input cost ({sym})":
                            sum(a.layer_breakdown.get("L3_network_input_cost", {}).get(y, 0.0) for a in r)})
fig2 = px.line(pd.DataFrame(tot_rows), x="Year", y=f"Indirect input cost ({sym})", color="Scenario",
               title="Portfolio indirect input cost via the EXIOBASE Leontief network")
fig2.update_layout(height=360, legend=dict(orientation="h", y=-0.25), margin=dict(t=50, b=10))
st.plotly_chart(fig2, use_container_width=True)

yr = st.select_slider("Top upstream sources at year", options=list(DEFAULT_HORIZON), value=2040)
for ar in res:
    l3 = next((x for x in ar.layer3_results if x.year == yr), None)
    if not l3 or not l3.top_upstream_sources:
        continue
    with st.expander(f"{ar.asset_id} — {T.sector_label(ar.sector)} · "
                     f"indirect cost {T.fmt_money(l3.total_indirect_cost_usd)}"):
        st.dataframe(
            pd.DataFrame(
                [(T.sector_label(s), T.fmt_money(v)) for s, v in l3.top_upstream_sources],
                columns=["Upstream sector", f"Contribution ({sym})"]),
            use_container_width=True, hide_index=True,
        )

# ===========================================================================
# C. High-carbon asset devaluation (demand-driven stranding)
# ===========================================================================
st.subheader("C. High-carbon asset devaluation")
dev = []
for ar in res:
    l2 = ar.layer2_result
    if not l2:
        continue
    meta = T.sector_meta(ar.sector)
    pathway_2050 = (l2.revenue_index or {}).get(2050, 1.0)
    demand_collapse = bool(meta.get("fossil_dependent")) and pathway_2050 < 0.5
    dev.append({
        "Entity": ar.asset_id, "Sector": T.sector_label(ar.sector),
        "Fossil-dependent": "✓" if meta.get("fossil_dependent") else "—",
        "Demand 2050": f"{pathway_2050:.2f}",
        "Demand-collapse stranding": "⚠️ yes" if demand_collapse else "no",
        f"Impairment ({sym})": T.fmt_money(sum(l2.annual_impairment_usd.values())),
    })
if dev:
    st.dataframe(pd.DataFrame(dev), use_container_width=True, hide_index=True)
st.caption("Devaluation from demand collapse is the *market* pathway to stranding (fossil-dependent "
           "sectors whose 2050 demand falls below 0.5). The impairment figure is the same Layer-2 "
           "value shown under Technology Risk — reported once, viewed through both lenses.")

T.disclaimer()
