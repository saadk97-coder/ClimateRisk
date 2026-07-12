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


tab_entity, tab_library = st.tabs(["🏭 Entity lever map", "📚 Full library"])

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
# TAB 2 — full library reference
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
