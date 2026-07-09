"""⑦ Methodology & Data — reference for the four-layer model and its calibration."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tr_common as T  # noqa: E402

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from engine.transition.data_loader import (  # noqa: E402
    load_carbon_prices, load_sector_pass_through, load_learning_curves,
    load_sector_taxonomy, load_io_matrix,
)

st.set_page_config(page_title="Methodology · " + T.APP_TITLE, page_icon="📚", layout="wide")
T.init_state()
T.page_header("Four-layer mathematics, calibration, and data provenance.", pillar="Reference")

st.markdown(
    """
### TCFD transition-risk categories → engine layers

| TCFD category | Layer | Mechanism | Routes to |
|---|:--:|---|---|
| **Policy & Legal** | L1 | (Scope 1+2) × NGFS carbon price × (1 − pass-through); Scope-3 indirect | Cash-flow OpEx |
| **Technology** | L2 | Wright's-Law cost crossover → logistic impairment; obsolescence/sunk cost | Cash flow + asset value |
| **Market** | L3 | Sector shock → Leontief inverse → input cost; demand-collapse stranding | Cash-flow input cost |
| **Reputation** | L4 | Sautner CCExposure × elasticities (credit / equity / revenue) | Cash flow **or** WACC |

**Non-duplication.** Each channel routes exactly once. Passed-through carbon cost (L1) becomes
the L3 network shock — booked in Market, not double-counted in Policy & Legal. Stranded-asset
impairment (L2) is a balance-sheet value loss, reported separately from the cash-flow stream.

### Key formulae
- **L1** `gross = (S1+S2)·price`; `absorbed = gross·(1−PT)`; `passed = gross·PT`;
  `net_opex = absorbed + S3·price·(1−PT)`.
- **L2** `Cost(Q) = Cost₀·(Q/Q₀)^b`, `b = log₂(1−LR)`; logistic impairment centred on the
  crossover year, `slope = 0.20`; cap scales with scenario demand collapse.
- **L3** `total_shock_j = Σᵢ L[i,j]·sᵢ`, `L = (I−A)⁻¹`; CES damping scales off-diagonals by 1/σ.
- **L4** `credit_bps = 12·reg + 6·phys`; `equity_bps = 50·(opp+reg+phys)`;
  `revenue_bps = 35·opp − 25·reg`.

### Known limitations
- I-O matrix is a 20-sector aggregation of EXIOBASE-3 world totals (screening grade).
- CCExposure uses sector-median proxies; firm-level Sautner data is licensed separately.
- Carbon prices are NGFS Phase V REMIND-MAgPIE; refresh from the NGFS portal for disclosures.
- Pass-through is sector-median; firm-specific values vary with market power and trade exposure.
"""
)

# --- Data provenance -------------------------------------------------------
st.subheader("Data provenance")
cp_m = load_carbon_prices().get("_meta", {})
io_m = load_io_matrix().get("_meta", {})
prov = pd.DataFrame([
    ["Carbon prices (L1)", cp_m.get("model", "NGFS Phase V"),
     cp_m.get("reported_unit", cp_m.get("source_unit", "USD/tCO₂")),
     cp_m.get("retrieved_utc", "—")],
    ["I-O matrix (L3)", (io_m.get("sources", ["EXIOBASE-3"])[0] if io_m.get("sources") else "EXIOBASE-3"),
     str(io_m.get("calibration_year", "2019")), io_m.get("retrieved_utc", "—")],
], columns=["Component", "Source", "Unit / basis", "Vintage"])
st.dataframe(prov, use_container_width=True, hide_index=True)

# --- Reference tables ------------------------------------------------------
with st.expander("Appendix D — NGFS carbon-price trajectories"):
    cp = load_carbon_prices()
    region = st.selectbox("Region", ["advanced", "emerging", "rest_of_world"])
    rows = []
    for sid, scen in cp["scenarios"].items():
        for y, v in scen.get(region, {}).items():
            rows.append({"Scenario": scen.get("label", sid), "Year": int(y), "USD/tCO₂": float(v)})
    if rows:
        fig = px.line(pd.DataFrame(rows), x="Year", y="USD/tCO₂", color="Scenario")
        fig.update_layout(height=360, margin=dict(t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

with st.expander("Appendix B — Sector pass-through"):
    spt = load_sector_pass_through()["sectors"]
    st.dataframe(pd.DataFrame([{
        "Sector": k, "Pass-through": f"{d['pass_through']*100:.0f}%",
        "Demand η": f"{d.get('demand_elasticity', 0):+.2f}",
        "Market structure": d.get("market_structure", "—"),
        "Trade-exposed": "✓" if d.get("trade_exposed") else "—",
        "Source": d.get("source_ref", "—"),
    } for k, d in spt.items()]), use_container_width=True, hide_index=True)

with st.expander("Appendix C — Technology learning rates"):
    lc = load_learning_curves()["technologies"]
    st.dataframe(pd.DataFrame([{
        "Technology": d.get("label", k), "Category": d.get("category", "—"),
        "Learning rate": f"{d['learning_rate']*100:.1f}%",
        "Lafond σ": f"{d.get('lafond_sigma', 0):.3f}", "Source": d.get("source_ref", "—"),
    } for k, d in lc.items()]), use_container_width=True, hide_index=True)

with st.expander("Appendix A — Sector taxonomy"):
    tax = load_sector_taxonomy()["sectors"]
    st.dataframe(pd.DataFrame([{
        "Key": k, "Label": v.get("label", k), "Incumbent": v.get("primary_technology", "—"),
        "Challenger": v.get("challenger_technology", "—"),
        "Fossil-dep.": "✓" if v.get("fossil_dependent") else "—",
        "EI (tCO₂/M$)": v.get("emission_intensity_t_per_revenue", "—"),
    } for k, v in tax.items()]), use_container_width=True, hide_index=True)

st.divider()
st.caption(
    "Reference: *BSR Transition Risk Methodology — Implementation v1* (14 pp). Bibliography: "
    "Sijm 2012; Fabra & Reguant 2014; Way et al. 2022; Lafond et al. 2018; Stadler et al. 2018; "
    "Acemoglu et al. 2012; Papageorgiou et al. 2017; Sautner et al. 2023; NGFS Phase V; IEA WEO 2023."
)
