"""
BSR Transition Risk — standalone application (entry point).

Run with:  streamlit run transition_app/Home.py

A self-contained, TCFD-aligned front end over the four-layer transition-risk
engine in engine/transition/. Independent of the physical-risk app.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tr_common as T  # noqa: E402

import streamlit as st  # noqa: E402

st.set_page_config(page_title=T.APP_TITLE, page_icon="⚡", layout="wide")
T.init_state()

T.page_header("Four-layer, channel-decomposed transition-risk analytics for a firm or portfolio.")

# --- What this is ----------------------------------------------------------
st.markdown(
    """
This application quantifies the financial impact of decarbonisation on an asset or
portfolio, organised around the **four TCFD transition-risk categories** — Policy &
Legal, Technology, Market, and Reputation. Each category is quantified by one layer of
the **BSR Transition Risk Methodology v1**, routed to exactly one financial destination
(the *non-duplication* rule).
"""
)

c1, c2 = st.columns([3, 2])

with c1:
    st.subheader("TCFD transition-risk categories → engine layers")
    st.markdown(
        """
| TCFD category | Layer | What it captures | Routes to |
|---|:--:|---|---|
| **Policy & Legal** | L1 | Carbon pricing / ETS, mandates, litigation → carbon cost & pass-through | Cash-flow OpEx |
| **Technology** | L2 | Obsolescence, sunk cost, capex, cost-crossover stranding | Cash flow + asset value |
| **Market** | L3 | Demand shifts, input/raw-material cost, supply-chain, asset devaluation | Cash-flow input cost |
| **Reputation** | L4 | Stakeholder perception → cost of capital, revenue | Cash flow **or** WACC (one) |

*Each channel routes once. Stranded-asset impairment (L2) is reported separately from the
cash-flow stream — obsolescence/value loss vs operating-cost adjustment.*
        """
    )

with c2:
    st.subheader("Portfolio status")
    assets = T.get_assets()
    active = [a for a in assets if a.sector]
    st.metric("Entities loaded", len(assets))
    st.metric("With a sector (analysable)", len(active))
    st.metric("Scenarios selected", len(st.session_state.get("tr_scenarios", [])))
    if not active:
        st.warning("Start on **① Data Entry** →", icon="👉")
        if st.button("Load worked-example portfolio"):
            T.set_portfolio([dict(r) for r in T.SAMPLE_PORTFOLIO])
            st.rerun()
    else:
        st.success("Ready — open a risk category to run scenarios.", icon="✅")

st.divider()

# --- Section map -----------------------------------------------------------
st.subheader("Sections")
st.markdown("Enter data first, then work through the four TCFD transition-risk categories; "
            "**⑥ Results** consolidates the financial impact.")

rows = [
    ("① Data Entry", "—", "Intake per entity: sector, Scope 1/2/3 emissions, replacement value, revenue."),
]
for name, layer, section, desc in T.TCFD_CATEGORIES:
    rows.append((section, layer, desc))
rows.append(("⑥ Results", "L1–L4", "Consolidated financial impact: PV of transition cost, "
             "stranded impairment, Monte-Carlo P5–P95 range, emissions and decarbonisation target."))
rows.append(("⑦ Methodology & Data", "—", "Four-layer mathematics, calibration, Appendices A–E."))
rows.append(("⑧ Audit", "L1–L4", "Full calculation trace: every number → its inputs, formula and vintage."))
rows.append(("⑨ Alignment", "—", "Financed emissions (PCAF), Implied Temperature Rise, pathway alignment."))
rows.append(("⑩ Abatement", "—", "Marginal abatement cost curves — decarbonise vs pay the carbon price."))

import pandas as pd  # noqa: E402
st.dataframe(
    pd.DataFrame(rows, columns=["Section", "Layer", "What it covers"]),
    use_container_width=True, hide_index=True,
)

st.divider()
T.disclaimer()
st.caption(
    "Reference: *BSR Transition Risk Methodology — Implementation v1*; "
    "BSR Climate Risk Practice memo *Quantifying Transition Risk* (May 2026)."
)
