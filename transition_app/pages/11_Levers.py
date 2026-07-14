"""⑪ Decarbonization Levers — map each entity's sector to its available
decarbonization levers by value-chain position, and overlay the entity's own
transition plan for a descriptive gap analysis.

Structured REFERENCE (approach adapted from BSR's Decarbonization Lever
Library) — not a scoring engine. The plan overlay is a manual analyst input and
the output is a factual coverage count + gap list, never a synthetic rating.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tr_common as T  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from engine.transition import levers as LV  # noqa: E402
from engine.transition import lever_planner as LP  # noqa: E402

st.set_page_config(page_title="Levers · " + T.APP_TITLE, page_icon="🧭", layout="wide")
T.init_state()
T.page_header(
    "Map each entity's sector to its available **decarbonization levers** by value-chain "
    "position, then overlay the transition plan to see coverage and gaps.",
    pillar="Cross-cutting",
)

_POT_ICON = {"high": "🟢 High", "medium": "🟡 Medium", "low": "⚪ Low"}
_MAT_ICON = {"mature": "Mature", "commercial": "Commercial", "emerging": "Emerging",
             "frontier": "Frontier"}


def _lever_card(sl: LV.SectorLever, key_prefix: str, checked: bool) -> bool:
    """Render one lever as an expander with a plan checkbox. Returns the checkbox state."""
    lv = sl.lever
    tag = "⭐ Primary" if sl.relevance == "primary" else "Secondary"
    mark = "✅ " if checked else ""
    with st.expander(f"{mark}{lv.name}  ·  {tag}  ·  {lv.domain_label}"):
        in_plan = st.checkbox("In our transition plan", value=checked,
                              key=f"{key_prefix}_{lv.id}")
        st.markdown(f"*{lv.description}*")
        st.markdown(f"**Why it applies here:** {sl.rationale}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Abatement cost", lv.cost_label())
        c2.metric("Global potential", _POT_ICON.get(lv.mitigation_potential, lv.mitigation_potential))
        c3.metric("Maturity", _MAT_ICON.get(lv.maturity, lv.maturity))
        st.markdown(f"**Role to 2050:** {lv.net_zero_2050_role}")
        if lv.dependencies:
            st.markdown("**Key dependencies:** " + "; ".join(lv.dependencies))
        np = lv.nature_people
        if np:
            st.markdown("**Nature & people (just-transition lens):**")
            st.markdown(
                f"- *Upstream:* {np.get('upstream','—')}\n"
                f"- *Operations:* {np.get('operations','—')}\n"
                f"- *Downstream:* {np.get('downstream','—')}"
            )
        if lv.references:
            st.caption("Sources: " + "; ".join(lv.references))
    return in_plan


tab_entity, tab_capital, tab_library = st.tabs(
    ["🏭 Entity lever map", "💰 Capital plan", "📚 Full library"])

# ===========================================================================
# TAB 1 — per-entity lever map + plan overlay
# ===========================================================================
with tab_entity:
    active = T.portfolio_gate()
    st.session_state.setdefault("tr_plan_levers", {})   # {entity_id: [lever_id,...]}

    labels = {a.id: f"{a.name} · {T.sector_label(a.sector)}" for a in active}
    eid = st.selectbox("Entity", [a.id for a in active], format_func=lambda i: labels[i])
    entity = next(a for a in active if a.id == eid)
    sector = entity.sector

    mapped = LV.sector_levers(sector)
    if not mapped:
        st.warning(f"No levers mapped for sector '{sector}'.")
        st.stop()

    saved_plan = list(st.session_state["tr_plan_levers"].get(eid, []))

    st.markdown(
        f"### {entity.name} — {T.sector_label(sector)}\n"
        f"{len(mapped)} levers mapped across the value chain. Tick the levers that are in "
        f"**{entity.name}'s** transition plan to see coverage and gaps."
    )

    grouped = LV.sector_levers_by_position(sector)
    new_plan: list[str] = []
    cols = st.columns(3)
    for col, pos in zip(cols, LV.POSITIONS):
        with col:
            st.markdown(f"#### {LV.POSITION_LABELS[pos]}")
            items = grouped.get(pos, [])
            if not items:
                st.caption("_No levers at this stage._")
            for sl in items:
                checked = _lever_card(sl, key_prefix=f"plan_{eid}",
                                      checked=sl.lever.id in saved_plan)
                if checked:
                    new_plan.append(sl.lever.id)

    st.session_state["tr_plan_levers"][eid] = new_plan

    # ---- gap analysis --------------------------------------------------
    st.divider()
    st.subheader("Transition-plan overlay — coverage & gaps")
    gap = LV.overlay_plan(sector, new_plan)

    m1, m2, m3 = st.columns(3)
    m1.metric("Primary levers covered", f"{gap.primary_covered} / {gap.primary_total}")
    m2.metric("Levers in plan", f"{len(gap.covered)} / {len(mapped)}")
    m3.metric("Open gaps", f"{len(gap.gaps)}")
    st.caption(gap.coverage_caption + "  —  a factual count, not a readiness score.")

    primary_gaps = [sl for sl in gap.gaps if sl.relevance == "primary"]
    if primary_gaps:
        st.error("**Primary levers not in the plan** (core abatement routes for this sector):")
        for sl in primary_gaps:
            st.markdown(f"- **{sl.lever.name}** — {LV.POSITION_LABELS[sl.position].split(' (')[0]}: "
                        f"{sl.rationale}")
    elif gap.primary_total:
        st.success("All primary levers for this sector are marked in-plan.")

    if gap.gaps:
        with st.expander(f"All {len(gap.gaps)} unaddressed levers"):
            df = pd.DataFrame([{
                "Lever": sl.lever.name,
                "Position": LV.POSITION_LABELS[sl.position].split(" (")[0],
                "Relevance": sl.relevance,
                "Cost ($/tCO₂e)": sl.lever.cost_label().replace(" $/tCO₂e", ""),
                "Maturity": sl.lever.maturity,
            } for sl in gap.gaps])
            st.dataframe(df, use_container_width=True, hide_index=True)

    # ---- export --------------------------------------------------------
    exp_rows = []
    for sl in mapped:
        exp_rows.append({
            "entity": entity.name, "sector": T.sector_label(sector),
            "lever": sl.lever.name, "position": sl.position,
            "relevance": sl.relevance, "in_plan": sl.lever.id in new_plan,
            "cost_usd_per_tco2": sl.lever.cost_label().replace(" $/tCO₂e", ""),
            "maturity": sl.lever.maturity, "rationale": sl.rationale,
        })
    st.download_button(
        "⬇ Download this entity's lever map (CSV)",
        pd.DataFrame(exp_rows).to_csv(index=False).encode("utf-8"),
        file_name=f"lever_map_{eid}.csv", mime="text/csv",
    )

# ===========================================================================
# TAB 2 — Capital plan (editable per-lever adoption + forward capex build)
# ===========================================================================
with tab_capital:
    active = T.portfolio_gate()
    st.session_state.setdefault("tr_lever_plan", {})       # {eid: [row dict, ...]}
    st.session_state.setdefault("tr_capex_schedule", {})   # {eid: {year: USD}} applied to engine

    labels = {a.id: f"{a.name} · {T.sector_label(a.sector)}" for a in active}
    ceid = st.selectbox("Entity", [a.id for a in active], format_func=lambda i: labels[i],
                        key="cap_entity")
    cent = next(a for a in active if a.id == ceid)
    csector = cent.sector
    cmapped = LV.sector_levers(csector)
    if not cmapped:
        st.warning(f"No levers mapped for sector '{csector}' — nothing to plan.")
        st.stop()

    scenarios_all = T.scenario_options()
    plan_sc = st.selectbox("Planning scenario (sets ambition / target adoption)", scenarios_all,
                           index=scenarios_all.index("net_zero_2050") if "net_zero_2050" in scenarios_all else 0,
                           format_func=T.scenario_label, key="cap_scenario")

    st.markdown(
        "Each lever the entity is exposed to, with its **current adoption**, a **target**, the "
        "**abatement** it can address, and the **forward capex** to close the gap. The forward "
        "capex is seeded by decomposing the model's top-down transition-capex estimate — then "
        "**edit any cell**, including the capital-planning start/end years. The bottom-up total "
        "and its phasing feed the engine's transition capex when you apply the plan."
    )

    fx = T.fx_to_usd()
    _sym = T.sym()

    # --- seed (or reload a saved plan) ------------------------------------
    from engine.transition.adaptive_capacity import build_strategy as _bs
    from engine.transition.data_loader import get_ngfs_region as _gnr

    def _seed_rows():
        strat = _bs(asset_id=cent.id, sector=csector, scenario_id=plan_sc,
                    region_band=_gnr(cent.region),
                    scope12_tco2=cent.scope1_emissions_tco2 + cent.scope2_emissions_tco2,
                    revenue_usd=cent.annual_revenue, replacement_value=cent.replacement_value,
                    horizon=list(T.DEFAULT_HORIZON),
                    target_year=getattr(cent, "decarb_target_year", 0),
                    residual_pct=getattr(cent, "decarb_residual_pct", 0.0),
                    positioning_override=(cent.positioning_override
                                          if cent.positioning_override >= 0 else None))
        in_plan = st.session_state.get("tr_plan_levers", {}).get(ceid, [])
        return LP.default_lever_plan(
            csector, cent.scope1_emissions_tco2 + cent.scope2_emissions_tco2,
            cent.scope3_emissions_tco2, getattr(cent, "scope3_use_phase_tco2", 0.0),
            strat.transition_capex_usd, strat.ambition, list(T.DEFAULT_HORIZON),
            in_plan_lever_ids=in_plan, target_year=getattr(cent, "decarb_target_year", 0)), \
            strat.transition_capex_usd

    reseed = st.button("↻ Re-seed from model estimate", key="cap_reseed",
                       help="Discard edits and re-decompose the top-down estimate.")
    saved = st.session_state["tr_lever_plan"].get(ceid)
    if saved and not reseed:
        rows = [LP.LeverPlanRow(**d) for d in saved]
        _, topdown = _seed_rows()
    else:
        rows, topdown = _seed_rows()

    # --- editable table ---------------------------------------------------
    df = pd.DataFrame([{
        "Lever": r.name,
        "Stage": {"own_operations": "Own ops", "upstream": "Upstream",
                  "downstream": "Downstream"}.get(r.position, r.position),
        "MAC $/t": r.mac_label(),
        "Addressable (kt/yr)": round(r.addressable_tco2 / 1e3, 1),
        "Adoption now %": round(r.adoption_now * 100),
        "Target %": round(r.adoption_target * 100),
        f"Forward capex ({_sym}M)": round(r.capex_usd / fx / 1e6, 2),
        f"Opex ({_sym}M/yr)": round(r.opex_usd_per_year / fx / 1e6, 3),
        "Start": int(r.start_year),
        "End": int(r.end_year),
    } for r in rows])

    edited = st.data_editor(
        df, use_container_width=True, hide_index=True, num_rows="fixed", key=f"cap_ed_{ceid}",
        column_config={
            "Lever": st.column_config.TextColumn(disabled=True, width="medium"),
            "Stage": st.column_config.TextColumn(disabled=True, width="small"),
            "MAC $/t": st.column_config.TextColumn(disabled=True, width="small",
                        help="Reference marginal abatement cost range from the lever library."),
            "Addressable (kt/yr)": st.column_config.NumberColumn(disabled=True, format="%.1f",
                        help="Annual tCO₂ this lever can address for this entity (potential × emissions base)."),
            "Adoption now %": st.column_config.NumberColumn(min_value=0, max_value=100, step=5, format="%d"),
            "Target %": st.column_config.NumberColumn(min_value=0, max_value=100, step=5, format="%d"),
            f"Forward capex ({_sym}M)": st.column_config.NumberColumn(min_value=0.0, format="%.2f"),
            f"Opex ({_sym}M/yr)": st.column_config.NumberColumn(min_value=0.0, format="%.3f"),
            "Start": st.column_config.NumberColumn(min_value=2025, max_value=2050, step=1, format="%d"),
            "End": st.column_config.NumberColumn(min_value=2025, max_value=2050, step=1, format="%d"),
        },
    )

    # --- reconstruct edited rows (row order fixed → align by index) --------
    new_rows = []
    for r, (_, e) in zip(rows, edited.iterrows()):
        new_rows.append(LP.LeverPlanRow(
            lever_id=r.lever_id, name=r.name, domain_label=r.domain_label,
            position=r.position, relevance=r.relevance, mac_low=r.mac_low, mac_high=r.mac_high,
            addressable_tco2=r.addressable_tco2,
            adoption_now=float(e["Adoption now %"]) / 100.0,
            adoption_target=float(e["Target %"]) / 100.0,
            capex_usd=float(e[f"Forward capex ({_sym}M)"]) * 1e6 * fx,
            opex_usd_per_year=float(e[f"Opex ({_sym}M/yr)"]) * 1e6 * fx,
            start_year=int(e["Start"]), end_year=int(e["End"]),
        ))
    st.session_state["tr_lever_plan"][ceid] = [r.__dict__ for r in new_rows]

    sched = LP.build_capex_schedule(new_rows, list(T.DEFAULT_HORIZON))
    bottom_up = LP.plan_total_capex(new_rows)
    tot_opex = LP.plan_total_opex(new_rows)
    tot_abate = LP.plan_total_abatement(new_rows)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Bottom-up capex", T.fmt_money(bottom_up))
    k2.metric("Model top-down est.", T.fmt_money(topdown),
              delta=f"{(bottom_up-topdown)/fx/1e6:+,.0f}M", delta_color="off")
    k3.metric(f"Ongoing opex ({_sym}/yr)", f"{_sym}{tot_opex/fx/1e6:,.1f}M")
    k4.metric("Abatement @target", f"{tot_abate/1e6:,.2f} MtCO₂/yr")

    # --- phasing chart ----------------------------------------------------
    import plotly.express as px  # noqa: E402
    ph = pd.DataFrame({"Year": list(sched.keys()),
                       f"Capex ({_sym}M)": [v / fx / 1e6 for v in sched.values()]})
    fig = px.bar(ph, x="Year", y=f"Capex ({_sym}M)", title="Bottom-up transition-capex phasing")
    fig.update_layout(height=300, margin=dict(t=44, b=8))
    st.plotly_chart(fig, use_container_width=True)

    # --- apply / clear ----------------------------------------------------
    applied = ceid in st.session_state["tr_capex_schedule"]
    ca, cb, cc = st.columns([2, 2, 3])
    with ca:
        if st.button("✅ Apply this plan to the model", key="cap_apply", type="primary"):
            st.session_state["tr_capex_schedule"][ceid] = sched
            st.success("Applied — Results now uses this bottom-up capex build for this entity.")
    with cb:
        if st.button("✖ Remove applied plan", key="cap_clear", disabled=not applied):
            st.session_state["tr_capex_schedule"].pop(ceid, None)
            st.info("Reverted to the model's top-down capex estimate.")
    with cc:
        if applied:
            st.caption("🟢 **Applied** — this entity's transition capex = the bottom-up lever build above.")
        else:
            st.caption("Not yet applied — the model still uses its top-down estimate for this entity.")

    st.download_button(
        "⬇ Download capital plan (CSV)",
        edited.assign(entity=cent.name, sector=T.sector_label(csector),
                      scenario=plan_sc).to_csv(index=False).encode("utf-8"),
        file_name=f"capital_plan_{ceid}.csv", mime="text/csv",
    )
    st.caption(
        "Forward capex seeds by decomposing the model's calibrated top-down estimate across levers "
        "(weighted by adoption-gap × addressable abatement × relevance), so the aggregate is "
        "unchanged until you edit it. Addressable abatement is a per-lever potential, not additive "
        "across overlapping levers. Screening-grade planning aid — not an optimiser."
    )

# ===========================================================================
# TAB 3 — full library reference
# ===========================================================================
with tab_library:
    st.markdown(
        "The full library — **29 levers across 5 domains**. Approach adapted from BSR's "
        "*Decarbonization Lever Library*; cost / maturity / potential figures refreshed from "
        "recent public sources (IEA, IPCC AR6, IRENA 2024, Lazard 2025, Mission Possible "
        "Partnership). Indicative screening ranges — not a scoring engine."
    )
    doms = LV.domains()
    all_lv = LV.all_levers()
    pick = st.selectbox("Filter by domain", ["All domains"] + list(doms.values()))
    for dom_id, dom_label in doms.items():
        if pick != "All domains" and pick != dom_label:
            continue
        dom_levers = [lv for lv in all_lv if lv.domain == dom_id]
        st.markdown(f"### {dom_label}")
        df = pd.DataFrame([{
            "Lever": lv.name,
            "Cost ($/tCO₂e)": lv.cost_label().replace(" $/tCO₂e", ""),
            "Potential": lv.mitigation_potential,
            "Maturity": lv.maturity,
            "Applies to (sectors)": len(lv.applicable_sectors),
        } for lv in dom_levers])
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.download_button(
        "⬇ Download full lever library (CSV)",
        pd.DataFrame([{
            "domain": lv.domain_label, "lever": lv.name, "description": lv.description,
            "cost_usd_per_tco2_low": lv.cost_range_usd_per_tco2[0],
            "cost_usd_per_tco2_high": lv.cost_range_usd_per_tco2[1],
            "mitigation_potential": lv.mitigation_potential, "maturity": lv.maturity,
            "net_zero_2050_role": lv.net_zero_2050_role,
            "dependencies": "; ".join(lv.dependencies),
            "applicable_sectors": "; ".join(lv.applicable_sectors),
            "references": "; ".join(lv.references),
        } for lv in all_lv]).to_csv(index=False).encode("utf-8"),
        file_name="decarbonization_lever_library.csv", mime="text/csv",
    )

st.caption(
    "Approach adapted from BSR's Decarbonization Lever Library (bsr.org). Value-chain "
    "positioning and nature/people impact lens carried over; cost/maturity/potential figures "
    "refreshed and indicative. This is a structured reference and manual plan-overlay tool, "
    "not a transition-readiness score."
)
T.disclaimer()
