"""③ Technology Risk — TCFD transition category, driven by Layer 2 (learning curves)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tr_common as T  # noqa: E402

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from engine.transition.transition_engine import DEFAULT_HORIZON  # noqa: E402
from engine.transition.learning_curves import project_technology, find_crossover_year  # noqa: E402

st.set_page_config(page_title="Technology · " + T.APP_TITLE, page_icon="🔧", layout="wide")
T.init_state()
T.page_header(
    "Cost of moving to low-carbon technology: obsolescence, sunk cost and capex. "
    "Quantified by **Layer 2** — Wright's-Law cost crossover and stranding.",
    pillar="Technology",
)

active = T.portfolio_gate()
scenarios = T.sidebar_settings()
if not scenarios:
    st.info("Pick scenarios in the sidebar.")
    st.stop()

with st.expander("⚙ Layer-2 model options (stranding & adaptive capacity)"):
    st.checkbox(
        "Adaptive capacity (residual, not gross)", key="tr_adaptive",
        help="ON by default. Instead of eroding 100% of the incumbent product's revenue (a frozen "
             "company), model the company migrating toward the low-carbon business: it captures part "
             "of the green upside, spends transition capex, and — if already partly transitioned — "
             "strands less. Ambition defaults from the scenario narrative; positioning is derived from "
             "emissions, sector lever readiness and transition-plan strength (override on Data Entry).")
    st.checkbox(
        "Carbon-inclusive crossover (P6)", key="tr_carbon_inclusive_crossover",
        help="Add the incumbent technology's carbon cost (carbon price × emission factor) to its "
             "effective cost when finding the cost-parity crossover. A rising carbon price pulls the "
             "crossover — and stranding — earlier. Off by default (pure LCOE).")
    st.slider(
        "Non-fossil impairment base share (R1)", 0.0, 1.0,
        float(st.session_state.get("tr_non_fossil_base_frac", 0.5)), 0.05,
        key="tr_non_fossil_base_frac",
        help="For non-fossil sectors, the share of replacement value tied to the incumbent "
             "technology that can strand. Fossil-dependent sectors always use the full value.")

results = T.run_engine(active, scenarios)
if not results:
    st.error("No results — check Data Entry.")
    st.stop()
sym = T.sym()

sc = st.selectbox("Scenario", scenarios, format_func=T.scenario_label)
res = results.get(sc, [])

# --- Headline metrics ------------------------------------------------------
cum_imp = sum(sum(r.annual_impairment_usd.values()) for r in res)
n_stranded = sum(1 for r in res if r.layer2_result and r.layer2_result.crossover_year is not None)
m1, m2, m3 = st.columns(3)
m1.metric("Value at risk from obsolescence (cum. impairment 2025–50)", T.fmt_money(cum_imp))
m2.metric("Entities flagged for stranding", f"{n_stranded}/{len(res)}")
earliest = min([r.layer2_result.crossover_year for r in res
                if r.layer2_result and r.layer2_result.crossover_year], default=None)
m3.metric("Earliest crossover / trigger", str(earliest) if earliest else "none")

# --- Adaptive capacity: gross vs residual ----------------------------------
if st.session_state.get("tr_adaptive", True) and any(getattr(r, "strategy", None) for r in res):
    st.subheader("Adaptive capacity — gross exposure vs residual after transition")
    st.caption("Gross = the company frozen (loses its incumbent product demand, captures nothing). "
               "Residual = after it pivots toward the low-carbon business, given where it starts. "
               "Ambition is the scenario-narrative default; positioning is derived (or overridden).")
    rows = []
    for r in res:
        s = getattr(r, "strategy", None)
        if not s:
            continue
        gross_ero = sum(v / (1 - s.capture_fraction) if s.capture_fraction < 1 else 0.0
                        for v in r.layer_breakdown["L2_revenue_erosion"].values())
        resid_ero = sum(r.layer_breakdown["L2_revenue_erosion"].values())
        capex = sum(r.layer_breakdown["L2_transition_capex"].values())
        rows.append({
            "Entity": r.asset_id, "Sector": T.sector_label(r.sector),
            "Ambition": f"{s.ambition:.2f}", "Positioning": f"{s.positioning:.2f}",
            "": s.positioning_source.split()[0],
            "Capture of loss": f"{s.capture_fraction*100:.0f}%",
            f"Gross erosion ({sym})": T.fmt_money(gross_ero),
            f"Residual erosion ({sym})": T.fmt_money(resid_ero),
            f"Transition capex ({sym})": T.fmt_money(capex),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows).astype(str), use_container_width=True, hide_index=True)
        st.caption("Positioning source: *derived* = computed from emissions + sector lever readiness + "
                   "plan strength (Lever Library overlay); *override* = manual analyst score on Data Entry. "
                   "Transition capex is the investment that earns the capture (so a pivot is never free).")

# --- Stranding diagnostics -------------------------------------------------
st.subheader("Stranding diagnostics")
rows = []
for ar in res:
    l2 = ar.layer2_result
    if not l2:
        continue
    _rng = "—"
    if l2.crossover_year and (l2.crossover_year_early or l2.crossover_year_late):
        _rng = f"{l2.crossover_year_early or l2.crossover_year}–{l2.crossover_year_late or l2.crossover_year}"
    rows.append({
        "Entity": ar.asset_id, "Sector": T.sector_label(ar.sector),
        "Incumbent tech": l2.incumbent_tech or "—",
        "Challenger tech": l2.challenger_tech or "—",
        "Crossover / trigger": l2.crossover_year if l2.crossover_year else "none",
        "Crossover range (±1σ)": _rng,
        "% stranded (recognised by 2050)": f"{l2.stranded_fraction_2050*100:.1f}%",
        "Strandable ceiling": f"{l2.strandable_ceiling_frac*100:.1f}%",
        f"Cum. impairment ({sym})": T.fmt_money(sum(l2.annual_impairment_usd.values())),
    })
if rows:
    _ddf = pd.DataFrame(rows).astype(str)   # mixed int/str columns → str for clean Arrow display
    st.dataframe(_ddf, use_container_width=True, hide_index=True)
    st.caption(
        "**% stranded (recognised)** is the cumulative impairment actually booked over 2025–50 "
        "as a share of replacement value — it equals the dollar figure in the last column. The "
        "**strandable ceiling** is the theoretical maximum that *could* strand (demand-scaled). "
        "Impairment is a balance-sheet write-down and is **not added** to the transition cash-flow "
        "cost shown on the Results page."
    )

# --- Cost-crossover chart --------------------------------------------------
st.subheader("Technology cost crossover (Wright's Law)")
ent = st.selectbox("Entity", [a.id for a in active],
                   format_func=lambda aid: next((f"{a.id} — {T.sector_label(a.sector)}"
                                                 for a in active if a.id == aid), aid))
asset = next((a for a in active if a.id == ent), None)
if asset:
    meta = T.sector_meta(asset.sector)
    inc = meta.get("primary_technology")
    chal = meta.get("challenger_technology")
    years = list(DEFAULT_HORIZON)
    fig = go.Figure()
    if inc:
        proj = project_technology(inc, sc, years)
        fig.add_trace(go.Scatter(x=[p.year for p in proj], y=[p.projected_cost for p in proj],
                                 name=f"Incumbent — {inc}", line=dict(color="#B33")))
    if chal:
        projc = project_technology(chal, sc, years)
        fig.add_trace(go.Scatter(x=[p.year for p in projc], y=[p.projected_cost for p in projc],
                                 name=f"Challenger — {chal}", line=dict(color="#2A7")))
        fig.add_trace(go.Scatter(x=[p.year for p in projc], y=[p.cost_hi for p in projc],
                                 line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=[p.year for p in projc], y=[p.cost_lo for p in projc],
                                 fill="tonexty", fillcolor="rgba(42,170,119,0.15)",
                                 line=dict(width=0), name="Challenger Lafond ±1σ"))
        if inc:
            cx = find_crossover_year(inc, chal, sc)
            if cx:
                fig.add_vline(x=cx, line_dash="dash", line_color="#888",
                              annotation_text=f"crossover {cx}")
    fig.update_layout(height=420, title=f"{T.sector_label(asset.sector)} — normalised unit cost",
                      yaxis_title="Relative cost index", margin=dict(t=50, b=10),
                      legend=dict(orientation="h", y=-0.25))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("When the challenger's cost falls below the incumbent's, new-build economics flip "
               "and the incumbent faces obsolescence — the sunk-cost/stranding trigger.")

# --- Impairment timeline ---------------------------------------------------
st.subheader("Cumulative stranded-asset impairment")
rows = []
for scx, r in results.items():
    cum = 0.0
    for y in DEFAULT_HORIZON:
        cum += sum(a.annual_impairment_usd.get(y, 0.0) for a in r)
        rows.append({"Year": y, "Scenario": T.scenario_label(scx), f"Cum. impairment ({sym})": cum})
fig2 = px.line(pd.DataFrame(rows), x="Year", y=f"Cum. impairment ({sym})", color="Scenario")
fig2.update_layout(height=340, legend=dict(orientation="h", y=-0.25), margin=dict(t=20, b=10))
st.plotly_chart(fig2, use_container_width=True)

with st.expander("Learning rates for these technologies (Appendix C)"):
    from engine.transition.data_loader import load_learning_curves
    techs = set()
    for a in active:
        m = T.sector_meta(a.sector)
        techs.update([m.get("primary_technology"), m.get("challenger_technology")])
    lct = load_learning_curves()["technologies"]
    lrows = [{
        "Technology": d.get("label", k), "Learning rate": f"{d['learning_rate']*100:.1f}%",
        "Lafond σ": f"{d.get('lafond_sigma', 0):.3f}", "Source": d.get("source_ref", "—"),
    } for k, d in lct.items() if k in techs]
    if lrows:
        st.dataframe(pd.DataFrame(lrows), use_container_width=True, hide_index=True)

T.disclaimer()
