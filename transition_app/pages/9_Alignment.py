"""⑨ Alignment — financed emissions (PCAF), Implied Temperature Rise, pathway alignment."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tr_common as T  # noqa: E402

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402

from engine.transition.alignment import (  # noqa: E402
    financed_emissions, implied_temperature_rise, pathway_alignment,
)

st.set_page_config(page_title="Alignment · " + T.APP_TITLE, page_icon="🎯", layout="wide")
T.init_state()
T.page_header("Financed emissions, Implied Temperature Rise, and pathway alignment.",
              pillar="Alignment & disclosure")

active = T.portfolio_gate()
T.portfolio_warnings_banner()
att = T.attribution_map()

# ===========================================================================
# 1. Financed / attributed emissions (PCAF)
# ===========================================================================
st.subheader("Financed / attributed emissions (PCAF)")
st.caption("Absolute emissions attributed to you by ownership/exposure share (Attribution % on "
           "Data Entry). 100% = corporate own-asset view; a lender/investor enters their stake.")
fe = financed_emissions(active, att)
e1, e2, e3, e4 = st.columns(4)
e1.metric("Financed Scope 1", f"{fe.scope1:,.0f} tCO₂")
e2.metric("Financed Scope 2", f"{fe.scope2:,.0f} tCO₂")
e3.metric("Financed Scope 3", f"{fe.scope3:,.0f} tCO₂")
e4.metric("Financed Scope 1+2", f"{fe.total_s1_s2:,.0f} tCO₂")

rows = []
for r in fe.per_asset:
    a = next(x for x in active if x.id == r["asset_id"])
    rev = a.annual_revenue  # USD
    rows.append({
        "Entity": r["asset_id"], "Sector": T.sector_label(a.sector),
        "Attribution": f"{r['attribution']*100:.0f}%",
        "Financed S1+2 (tCO₂)": round(r["scope1_2"], 0),
        "Financed S3 (tCO₂)": round(r["scope3"], 0),
        "Economic intensity (tCO₂/$M rev)": round(r["scope1_2"] / (rev / 1e6), 1) if rev > 0 else "—",
    })
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
st.caption("PCAF data-quality note: emissions are reported/estimated inputs; attribution here uses a "
           "single share per asset. For disclosure, document the PCAF data-quality score per position.")

st.divider()

# ===========================================================================
# 1b. Peer benchmarking
# ===========================================================================
st.subheader("Peer benchmarking — carbon intensity")
st.caption("Each entity's economic carbon intensity (tCO₂ Scope 1+2 per $M revenue) vs the real "
           "corporate-universe distribution (Sautner JoF 2023, ~10k firms: median 11, p75 85 tCO₂/$M).")
from engine.transition.alignment import intensity_benchmark  # noqa: E402
bench = intensity_benchmark(active)
if bench:
    bdf = pd.DataFrame(bench)
    fig_b = px.bar(bdf, x="asset_id", y="entity_intensity", color="position",
                   color_discrete_map={"low (bottom quartile)": "#2f7d4f", "below median": "#7bb661",
                                       "above median": "#c9922e", "high (top quartile)": "#c0392b"},
                   labels={"entity_intensity": "tCO₂ / $M revenue", "asset_id": "Entity"},
                   title="Carbon intensity vs corporate universe", log_y=True)
    fig_b.add_hline(y=bench[0]["universe_median"], line_dash="dot", line_color="#666",
                    annotation_text="universe median")
    fig_b.add_hline(y=bench[0]["universe_p75"], line_dash="dash", line_color="#999",
                    annotation_text="universe p75")
    fig_b.update_layout(height=340, margin=dict(t=50, b=10))
    st.plotly_chart(fig_b, use_container_width=True)
    st.dataframe(bdf.rename(columns={
        "asset_id": "Entity", "sector": "Sector", "entity_intensity": "Intensity (tCO₂/$M)",
        "universe_median": "Universe median", "universe_p75": "Universe p75", "position": "Position",
    }), use_container_width=True, hide_index=True)
    st.caption("Absolute position vs the cross-sector corporate universe; a sector-relative benchmark "
               "would need per-sector intensity distributions (future).")

st.divider()

# ===========================================================================
# 2. Implied Temperature Rise (ITR)
# ===========================================================================
st.subheader("Emissions-budget temperature score (screening ITR proxy)")
st.caption("⚠️ A **screening indicator**, not a standard-compliant Implied Temperature Rise "
           "(SBTi / CDP-WWF temperature scoring). Each entity's abated Scope 1+2 pathway is compared "
           "to a 1.5 °C linear-to-net-zero budget; the portfolio score is Scope 1+2 × attribution "
           "weighted and floored at 1.5 °C. Set targets on Data Entry to improve it.")
itr = implied_temperature_rise(active, att)
port = itr["portfolio_itr"]
band = "🟢 aligned" if port <= 1.6 else ("🟡 lagging" if port <= 2.0 else "🔴 misaligned")
m1, m2 = st.columns([1, 2])
m1.metric("Portfolio ITR", f"{port:.2f} °C", band)
per_itr = pd.DataFrame(itr["per_asset"])
if not per_itr.empty:
    per_itr["target_year"] = per_itr["target_year"].fillna(0).astype(int).replace(0, "—")
    fig = px.bar(per_itr, x="asset_id", y="itr", color="itr",
                 color_continuous_scale=["#2f7d4f", "#b5730a", "#c0392b"], range_color=[1.2, 3.5],
                 labels={"itr": "ITR (°C)", "asset_id": "Entity"}, title="Per-entity ITR")
    fig.add_hline(y=1.5, line_dash="dash", line_color="#666", annotation_text="1.5 °C")
    fig.update_layout(height=340, margin=dict(t=50, b=10), coloraxis_showscale=False)
    with m2:
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# ===========================================================================
# 3. Technology / pathway alignment (PACTA-style)
# ===========================================================================
st.subheader("Pathway alignment (PACTA-style)")
sc = st.selectbox("Benchmark scenario", T.scenario_options(),
                  index=T.scenario_options().index("net_zero_2050") if "net_zero_2050" in T.scenario_options() else 0,
                  format_func=T.scenario_label)
st.caption("Compares each entity's Scope 1+2 decline by 2050 against the scenario's sector demand "
           "pathway (the alignment benchmark).")
_ICON = {"aligned": "🟢 aligned", "lagging": "🟡 lagging", "misaligned": "🔴 misaligned"}
arows = []
for a in active:
    p = pathway_alignment(a, sc)
    arows.append({
        "Entity": a.id, "Sector": T.sector_label(a.sector),
        "Fossil-dependent": "✓" if p["fossil_dependent"] else "—",
        "Entity 2050 (index)": p["asset_2050_index"],
        "Benchmark 2050 (index)": p["benchmark_2050_index"],
        "Gap": p["gap"], "Status": _ICON[p["status"]],
    })
st.dataframe(pd.DataFrame(arows), use_container_width=True, hide_index=True)

# ===========================================================================
# 4. Attributed transition cost (ties alignment to the financial view)
# ===========================================================================
st.subheader("Attributed transition cost")
scenarios = st.session_state.get("tr_scenarios", T.DEFAULT_SCENARIOS)
results = T.run_engine(active, scenarios)
if results:
    wacc = T.real_discount()  # P2 real discount
    base_year = min(__import__("engine.transition.transition_engine", fromlist=["DEFAULT_HORIZON"]).DEFAULT_HORIZON)

    def _pv(series):
        return sum(v / (1 + wacc) ** (y - base_year) for y, v in series.items())

    trows = []
    for scn, res in results.items():
        tot = 0.0
        for r in res:
            f = att.get(r.asset_id, 1.0)
            tot += _pv(r.annual_total_cost_usd) * f
        trows.append({"Scenario": T.scenario_label(scn),
                      f"Attributed PV transition cost ({T.sym()})": T.fmt_money(tot)})
    st.dataframe(pd.DataFrame(trows), use_container_width=True, hide_index=True)
    st.caption("PV of transition cost scaled by each entity's attribution share — the financed "
               "equivalent of the headline Results figure.")

st.divider()

# ===========================================================================
# 5. Disclosure report (IFRS S2 / ESRS E1)
# ===========================================================================
st.subheader("Disclosure report (IFRS S2 / ESRS E1)")
st.caption("Generates a governance → strategy → risk-management → metrics report mapped to IFRS S2 "
           "and ESRS E1, populated from your governance narrative (set on the Governance inputs) and "
           "these results. Screening-grade — for internal use / pre-assurance drafting.")
gov = st.session_state.get("tr_governance", {})
with st.expander("Governance narrative inputs (populate the report's Governance section)"):
    gov["board_oversight"] = st.text_area(
        "Board oversight of transition risk", value=gov.get("board_oversight", ""),
        placeholder="e.g. The Risk Committee reviews scenario results quarterly; material stranding "
                    "is escalated to the board annually.", height=80)
    gc1, gc2 = st.columns(2)
    with gc1:
        gov["review_cadence"] = st.selectbox(
            "Review cadence", ["Quarterly", "Semi-annual", "Annual", "Ad hoc", "Not yet established"],
            index=["Quarterly", "Semi-annual", "Annual", "Ad hoc", "Not yet established"].index(
                gov.get("review_cadence", "Annual")))
    with gc2:
        gov["accountable_body"] = st.text_input(
            "Accountable committee / role", value=gov.get("accountable_body", ""),
            placeholder="Board Risk Committee / CRO")
    gov["management_role"] = st.text_area(
        "Management's role", value=gov.get("management_role", ""),
        placeholder="e.g. Sustainability & Finance jointly own the model and feed stranding flags "
                    "into impairment testing.", height=80)
    gov["strategy_integration"] = st.text_area(
        "Integration into strategy & financial planning", value=gov.get("strategy_integration", ""),
        placeholder="e.g. Layer-1 carbon OpEx is in the 5-year plan; stranding triggers inform capital "
                    "allocation.", height=70)
    if st.button("💾 Save governance narrative"):
        st.session_state["tr_governance"] = gov
        st.success("Saved — regenerate the report below.")

if results:
    report = T.build_disclosure_report(active, results, scenarios,
                                       T.real_discount())
    dcol1, dcol2 = st.columns([1, 3])
    with dcol1:
        st.download_button("⬇ Download report (Markdown)", report,
                           file_name="transition_disclosure_IFRS-S2_ESRS-E1.md",
                           mime="text/markdown", use_container_width=True)
    with st.expander("Preview report"):
        st.markdown(report)

T.disclaimer()
