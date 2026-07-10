"""⑤ Reputation Risk — TCFD transition category, driven by Layer 4 (CCExposure)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tr_common as T  # noqa: E402

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from engine.transition.transition_engine import DEFAULT_HORIZON  # noqa: E402
from engine.transition.cc_exposure import ROUTE_WACC  # noqa: E402

st.set_page_config(page_title="Reputation · " + T.APP_TITLE, page_icon="📣", layout="wide")
T.init_state()
T.page_header(
    "Changing stakeholder perception → higher cost of capital and revenue effects. "
    "Quantified by **Layer 4** — Sautner CCExposure × empirical elasticities.",
    pillar="Reputation",
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
routing = st.session_state.get("tr_l4_routing")

sc = st.selectbox("Scenario", scenarios, format_func=T.scenario_label)
res = results.get(sc, [])

st.info(
    ("**Routing = Cash flows.** The revenue-growth modifier is applied to cash flows; the "
     "credit/equity premiums below are diagnostic. Switch to *WACC* in the sidebar to route "
     "the financing premium to the discount rate instead.")
    if routing != ROUTE_WACC else
    ("**Routing = WACC.** The credit + equity premium is added to the discount rate; the "
     "revenue modifier is zeroed to preserve non-duplication."),
    icon="🔀",
)

# --- CCExposure & premiums -------------------------------------------------
st.subheader("CCExposure sub-scores and capital-market premiums")
rows = []
for ar in res:
    l4 = ar.layer4_result
    if not l4:
        continue
    rows.append({
        "Entity": ar.asset_id, "Sector": T.sector_label(ar.sector),
        "CCE opportunity": round(l4.cce_opportunity, 2),
        "CCE regulatory": round(l4.cce_regulatory, 2),
        "CCE physical": round(l4.cce_physical, 2),
        "Credit spread Δ (bps)": round(l4.credit_spread_premium_bps, 0),
        "Equity premium Δ (bps)": round(l4.equity_premium_bps, 0),
        "Revenue growth Δ (bps)": round(l4.revenue_growth_modifier_bps, 0),
        "WACC premium (bps)": round(ar.wacc_premium_bps, 0),
    })
if rows:
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# --- Financing premium metric ----------------------------------------------
if routing == ROUTE_WACC:
    avg_bps = sum(r.wacc_premium_bps for r in res) / max(len(res), 1)
    st.metric("Average WACC premium from reputation/capital exposure", f"{avg_bps:.0f} bps")
else:
    st.subheader("Revenue effect over time (reputation → sales)")
    rows = []
    for scx, r in results.items():
        for y in DEFAULT_HORIZON:
            # L4 revenue modifier stored as a cost; negate to show revenue effect sign
            cost = sum(a.layer_breakdown.get("L4_revenue_modifier", {}).get(y, 0.0) for a in r)
            rows.append({"Year": y, "Scenario": T.scenario_label(scx),
                         f"Revenue effect ({sym})": -cost})
    fig = px.line(pd.DataFrame(rows), x="Year", y=f"Revenue effect ({sym})", color="Scenario",
                  title="Positive = reputational upside (opportunity); negative = drag")
    fig.add_hline(y=0, line_color="#999")
    fig.update_layout(height=360, legend=dict(orientation="h", y=-0.25), margin=dict(t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)

st.caption(
    "CCExposure is z-standardised against the pooled Sautner firm-year distribution (JoF 2023 "
    "Table 1), then priced per standard deviation: credit = 12·z_reg + 6·z_phys; equity = "
    "50·z_total; revenue = 35·z_opp − 25·z_reg. Sector exposures anchored to Sautner Table 4 by "
    "SIC industry; the CCE columns above are z-scores (SDs from the average firm)."
)

with st.expander("⬆ Firm-level CCExposure override (licensed Sautner feed)"):
    st.caption("Upload firm-level CCExposure to replace the sector-median proxy for specific "
               "entities. CSV columns: asset_id, opportunity, regulatory, physical — on the raw "
               "Sautner ×10³ scale (see Methodology for the pooled means).")
    fu = st.file_uploader("Firm CCExposure CSV", type="csv", key="firm_cce_up")
    if fu is not None:
        try:
            fdf = pd.read_csv(fu)
            ov = {}
            for _, r in fdf.iterrows():
                ov[str(r["asset_id"]).strip()] = {
                    "opportunity": float(r["opportunity"]),
                    "regulatory": float(r["regulatory"]),
                    "physical": float(r["physical"]),
                }
            st.session_state["tr_firm_cce"] = ov
            st.success(f"Loaded firm-level CCExposure for {len(ov)} entit(ies). Re-runs use it.")
        except Exception as e:
            st.error(f"Could not read firm CCExposure CSV: {e}")
    ov = st.session_state.get("tr_firm_cce") or {}
    if ov:
        st.markdown("**Overridden entities:** " + ", ".join(sorted(ov)))
        if st.button("Clear firm overrides"):
            st.session_state["tr_firm_cce"] = {}
            st.rerun()

T.disclaimer()
