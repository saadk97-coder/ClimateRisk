"""① Data Entry — transition-risk intake (foundational TCFD input)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tr_common as T  # noqa: E402

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

st.set_page_config(page_title="Data Entry · " + T.APP_TITLE, page_icon="📋", layout="wide")
T.init_state()
T.page_header("Define the entities to analyse: sector, emissions, and financials.", pillar="Data intake")

# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------
cc1, cc2 = st.columns([1, 3])
with cc1:
    cur = st.selectbox(
        "Reporting currency", ["USD", "EUR", "GBP", "JPY", "CAD", "AUD"],
        index=["USD", "EUR", "GBP", "JPY", "CAD", "AUD"].index(T.currency()),
        help="NGFS carbon prices are USD-denominated (US$2020). Enter financials in the "
             "same currency; non-USD is a display convenience, not an FX conversion.",
    )
    st.session_state["tr_currency"] = cur

st.divider()

# ---------------------------------------------------------------------------
# Portfolio editor
# ---------------------------------------------------------------------------
st.subheader("Portfolio")
st.caption(
    "Add one row per entity. **Sector** drives pass-through, learning-curve mapping and "
    "I-O position. **Region** is an ISO3 country code (→ NGFS advanced / emerging / RoW). "
    "Emissions are annual tonnes CO₂; financials are in the reporting currency."
)

# Column groups so the data_editor column types match the underlying dtypes even
# when the portfolio is empty (an empty list column infers float64, which breaks
# the text/selectbox column config).
_STR_COLS = ["id", "name", "region", "sector"]
_NUM_COLS = ["replacement_value", "annual_revenue", "scope1", "scope2", "scope3",
             "target_year", "priced_pct"]

rows = T.get_portfolio()
if rows:
    df = pd.DataFrame(rows, columns=T.PORTFOLIO_COLUMNS)
else:
    df = pd.DataFrame({**{c: pd.Series(dtype="object") for c in _STR_COLS},
                       **{c: pd.Series(dtype="float64") for c in _NUM_COLS}})
# enforce dtypes on both paths
for c in _STR_COLS:
    df[c] = df[c].astype("object")
for c in _NUM_COLS:
    df[c] = pd.to_numeric(df[c], errors="coerce")

edited = st.data_editor(
    df,
    num_rows="dynamic",
    use_container_width=True,
    key="tr_editor",
    column_config={
        "id": st.column_config.TextColumn("ID", required=True, width="small"),
        "name": st.column_config.TextColumn("Name", required=True),
        "region": st.column_config.TextColumn("ISO3", help="e.g. USA, DEU, CHN, IND", width="small"),
        "sector": st.column_config.SelectboxColumn(
            "Sector", options=T.sector_options(), required=True, width="medium"),
        "replacement_value": st.column_config.NumberColumn(
            f"Replacement value ({T.sym()})", min_value=0.0, format="%.0f"),
        "annual_revenue": st.column_config.NumberColumn(
            f"Annual revenue ({T.sym()})", min_value=0.0, format="%.0f"),
        "scope1": st.column_config.NumberColumn("Scope 1 (tCO₂)", min_value=0.0, format="%.0f"),
        "scope2": st.column_config.NumberColumn("Scope 2 (tCO₂)", min_value=0.0, format="%.0f"),
        "scope3": st.column_config.NumberColumn("Scope 3 (tCO₂)", min_value=0.0, format="%.0f"),
        "target_year": st.column_config.NumberColumn(
            "Net-zero target yr", min_value=0, max_value=2060, step=1, format="%d",
            help="Scope 1+2 net-zero target year. Blank / 0 = no abatement (emissions held flat)."),
        "priced_pct": st.column_config.NumberColumn(
            "Priced %", min_value=0, max_value=100, step=5, format="%d",
            help="% of Scope 1+2 exposed to the carbon price, net of free allocation. Blank = 100%."),
    },
)

b1, b2, b3, b4 = st.columns([1, 1, 1, 3])
with b1:
    if st.button("💾 Save portfolio", type="primary"):
        clean = edited.dropna(subset=["id", "name"]).copy()
        # blank priced_pct means fully priced (100), not 0
        if "priced_pct" in clean:
            clean["priced_pct"] = clean["priced_pct"].fillna(100)
        if "target_year" in clean:
            clean["target_year"] = clean["target_year"].fillna(0)
        clean = clean.fillna(0)
        recs = clean.to_dict("records")
        # normalise types
        for r in recs:
            r["id"] = str(r["id"]).strip()
            r["name"] = str(r["name"]).strip()
            r["region"] = str(r.get("region", "USA")).strip().upper() or "USA"
            r["sector"] = str(r.get("sector", "")).strip().lower()
        T.set_portfolio(recs)
        st.success(f"Saved {len(recs)} entit{'y' if len(recs)==1 else 'ies'}.")
with b2:
    if st.button("📥 Load examples"):
        T.set_portfolio([dict(r) for r in T.SAMPLE_PORTFOLIO])
        st.rerun()
with b3:
    if st.button("🗑️ Clear all"):
        T.set_portfolio([])
        st.rerun()

# ---------------------------------------------------------------------------
# Validation feedback
# ---------------------------------------------------------------------------
saved = T.get_portfolio()
if saved:
    problems = []
    for r in saved:
        if len(str(r.get("region", ""))) != 3:
            problems.append(f"`{r.get('id','?')}`: region must be a 3-letter ISO3 code.")
        if not r.get("sector"):
            problems.append(f"`{r.get('id','?')}`: no sector assigned.")
    if problems:
        st.warning("**Fix before analysing:**\n\n" + "\n\n".join(f"- {p}" for p in problems))
    else:
        # region classification preview
        prev = []
        for r in saved:
            prev.append({
                "ID": r["id"], "Sector": T.sector_label(r["sector"]),
                "NGFS region": T.get_ngfs_region(r["region"]),
                "Fossil-dependent": "✓" if T.sector_meta(r["sector"]).get("fossil_dependent") else "—",
                "EI (tCO₂/M$)": T.sector_meta(r["sector"]).get("emission_intensity_t_per_revenue", "—"),
            })
        st.markdown("**Ready to analyse** — sector & region resolved:")
        st.dataframe(pd.DataFrame(prev), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# CSV import / export
# ---------------------------------------------------------------------------
with st.expander("⇄ CSV import / export"):
    st.caption("Columns: " + ", ".join(T.PORTFOLIO_COLUMNS))
    up = st.file_uploader("Upload portfolio CSV", type="csv")
    if up is not None:
        try:
            in_df = pd.read_csv(up)
            keep = [c for c in T.PORTFOLIO_COLUMNS if c in in_df.columns]
            recs = in_df[keep].to_dict("records")
            T.set_portfolio(recs)
            st.success(f"Imported {len(recs)} rows. Review above and Save.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not read CSV: {e}")
    if saved:
        st.download_button(
            "Download current portfolio CSV",
            pd.DataFrame(saved, columns=T.PORTFOLIO_COLUMNS).to_csv(index=False),
            file_name="transition_portfolio.csv", mime="text/csv",
        )

# ---------------------------------------------------------------------------
# Project save / load (full state, survives refresh)
# ---------------------------------------------------------------------------
with st.expander("💼 Save / load project (full state)"):
    import json
    _STATE_KEYS = ["tr_assets", "tr_currency", "tr_scenarios", "tr_l4_routing",
                   "tr_elasticity", "tr_layers", "tr_wacc", "tr_scope3_mode",
                   "tr_governance", "tr_target_year"]
    st.caption("Bundles the portfolio, analysis settings and governance narrative into one file — "
               "the session itself is not persisted, so download to keep your work across refreshes.")
    project = {k: st.session_state.get(k) for k in _STATE_KEYS}
    st.download_button("⬇ Download project (.json)", json.dumps(project, indent=2),
                       file_name="transition_project.json", mime="application/json")
    up_proj = st.file_uploader("⬆ Load project (.json)", type="json", key="proj_up")
    if up_proj is not None:
        try:
            loaded = json.load(up_proj)
            for k in _STATE_KEYS:
                if k in loaded and loaded[k] is not None:
                    st.session_state[k] = loaded[k]
            st.success("Project loaded. Review the portfolio above.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not load project: {e}")

# ---------------------------------------------------------------------------
# Sector reference
# ---------------------------------------------------------------------------
with st.expander("📖 Sector taxonomy reference (Appendix A)"):
    tax = T.load_sector_taxonomy()["sectors"]
    ref = [{
        "Key": k, "Label": v.get("label", k),
        "Incumbent": v.get("primary_technology", "—"),
        "Challenger": v.get("challenger_technology", "—"),
        "Fossil-dep.": "✓" if v.get("fossil_dependent") else "—",
        "EI (tCO₂/M$)": v.get("emission_intensity_t_per_revenue", "—"),
    } for k, v in tax.items()]
    st.dataframe(pd.DataFrame(ref), use_container_width=True, hide_index=True)

T.disclaimer()
