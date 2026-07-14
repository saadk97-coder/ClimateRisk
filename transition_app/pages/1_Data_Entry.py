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
        help="Enter financials in this currency. The engine runs in USD (NGFS prices are "
             "USD/tCO₂); inputs are converted to USD and results converted back for display.",
    )
    st.session_state["tr_currency"] = cur
with cc2:
    if cur != "USD":
        st.caption(f"FX: 1 {cur} = {T.fx_to_usd(cur):.4f} USD · basis {T.FX_AS_OF}. "
                   "Financials are converted to USD for the engine and back for display.")

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
_STR_COLS = ["id", "name", "region", "sector", "firm_id"]
_NUM_COLS = ["replacement_value", "annual_revenue", "scope1", "scope2", "scope3",
             "scope3_use_phase", "financed_emissions",
             "target_year", "residual_pct", "priced_pct", "attribution_pct",
             "transition_capex", "positioning_pct"]

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
        "region": st.column_config.TextColumn(
            "Region", width="small",
            help="ISO3 (USA, DEU, ESP, CHN, IND) OR a sub-national code for higher resolution in the "
                 "US & Europe: USA-TX, USA-CA, USA-SW, ESP-S, ITA-N … Drives (1) the NGFS carbon-price "
                 "band, (2) a jurisdiction carbon-stringency factor — EU/UK above the band, US/Canada "
                 "below, converging by ~2040 — and (3) the region-aware technology-cost crossover "
                 "(a watt in Texas ≠ one in California)."),
        "sector": st.column_config.SelectboxColumn(
            "Sector", options=T.sector_options(), required=True, width="medium"),
        "replacement_value": st.column_config.NumberColumn(
            f"Replacement value ({T.sym()})", min_value=0.0, format="%.0f"),
        "annual_revenue": st.column_config.NumberColumn(
            f"Annual revenue ({T.sym()})", min_value=0.0, format="%.0f"),
        "scope1": st.column_config.NumberColumn("Scope 1 (tCO₂)", min_value=0.0, format="%.0f"),
        "scope2": st.column_config.NumberColumn("Scope 2 (tCO₂)", min_value=0.0, format="%.0f"),
        "scope3": st.column_config.NumberColumn(
            "Scope 3 upstream (tCO₂)", min_value=0.0, format="%.0f",
            help="Upstream value-chain emissions (GHG Protocol cat 1–9) → priced as supply-chain input cost (L3)."),
        "scope3_use_phase": st.column_config.NumberColumn(
            "Scope 3 use-phase (tCO₂)", min_value=0.0, format="%.0f",
            help="Downstream use-of-sold-products (cat 11) — customers' emissions from your products. "
                 "Drives product-demand risk for engine/machinery/fuel makers. Leave 0 if not a product maker."),
        "financed_emissions": st.column_config.NumberColumn(
            "Financed emissions (tCO₂)", min_value=0.0, format="%.0f",
            help="Lender/investor book (Scope 3 cat 15) — THE material transition exposure for a bank or "
                 "asset manager. Priced as a screening portfolio-transition risk. Leave 0 if not a financial. "
                 "A real figure needs PCAF portfolio data."),
        "target_year": st.column_config.NumberColumn(
            "Net-zero target yr", min_value=0, max_value=2060, step=1, format="%d",
            help="Scope 1+2 net-zero target year. Blank / 0 = no abatement (emissions held flat)."),
        "residual_pct": st.column_config.NumberColumn(
            "Residual % at target", min_value=0, max_value=100, step=5, format="%d",
            help="% of today's Scope 1+2 still emitted at the target year. 0 = full net-zero (default); "
                 "20 = an 80% reduction target. Only used when a target year is set."),
        "priced_pct": st.column_config.NumberColumn(
            "Priced %", min_value=0, max_value=100, step=5, format="%d",
            help="% of Scope 1+2 exposed to the carbon price, net of free allocation. Blank = 100%."),
        "attribution_pct": st.column_config.NumberColumn(
            "Attribution %", min_value=0, max_value=100, step=5, format="%d",
            help="Share of the asset attributed to you (PCAF). 100 = fully owned; a lender/investor "
                 "enters their stake. Blank = 100%."),
        "transition_capex": st.column_config.NumberColumn(
            f"Transition capex ({T.sym()})", min_value=0.0, format="%.0f",
            help="Planned investment to pivot toward the low-carbon business (adaptive capacity). "
                 "Blank / 0 = let the model estimate it from pivot scale, sector and geography."),
        "positioning_pct": st.column_config.NumberColumn(
            "Positioning (0–100)", min_value=0, max_value=100, step=5, format="%d",
            help="Manual 'art' override of how well-placed the company is today to transition "
                 "(0 = laggard, 100 = leader). Blank = derive from emissions, sector lever readiness "
                 "and transition-plan strength ('science')."),
        "firm_id": st.column_config.TextColumn(
            "Firm", width="small",
            help="Optional: give two or more rows the same Firm to roll them up as one "
                 "diversified company (business lines) — see the firm view on Results. Blank = "
                 "the entity is its own firm."),
    },
)

b1, b2, b3, b4 = st.columns([1, 1, 1, 3])
with b1:
    if st.button("💾 Save portfolio", type="primary"):
        clean = edited.dropna(subset=["id", "name"]).copy()
        # blank priced_pct means fully priced (100), not 0
        if "priced_pct" in clean:
            clean["priced_pct"] = clean["priced_pct"].fillna(100)
        if "attribution_pct" in clean:
            clean["attribution_pct"] = clean["attribution_pct"].fillna(100)
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
# Low-disclosure estimation — fill missing Scope 1+2 from sector × revenue
# ---------------------------------------------------------------------------
st.session_state.setdefault("tr_estimate_missing", False)
st.session_state["tr_estimate_missing"] = st.checkbox(
    "Estimate missing emissions from sector × revenue (screening)",
    value=st.session_state["tr_estimate_missing"],
    help="For low-disclosure entities: any row with no Scope 1+2 but a sector and revenue gets a "
         "screening estimate = sector emission intensity (tCO₂/M$) × revenue. Reported figures are "
         "never overwritten. Flagged as a screening approximation, not firm data.")
if st.session_state["tr_estimate_missing"]:
    est_ids = T.estimated_emission_entities()
    if est_ids:
        st.caption(f"🔎 Emissions **estimated** for: {', '.join(est_ids)} — screening only "
                   "(EEIO/EXIOBASE sector averages). Enter reported figures to override.")
    else:
        st.caption("No rows need estimation — every entity with a sector and revenue reports Scope 1+2.")

# ---------------------------------------------------------------------------
# Validation feedback
# ---------------------------------------------------------------------------
saved = T.get_portfolio()
if saved:
    errors, warnings = T.validate_portfolio(saved)
    if warnings:
        st.warning("**Warnings (results may be incomplete):**\n\n"
                   + "\n\n".join(f"- {w}" for w in warnings))
    if errors:
        st.error("**Fix before analysing:**\n\n" + "\n\n".join(f"- {e}" for e in errors))
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
            # taxonomy-check sectors: blank unknown keys so the grid selectbox stays valid
            valid = set(T.sector_options())
            bad = set()
            for r in recs:
                s = str(r.get("sector", "")).strip().lower()
                if s and s not in valid:
                    bad.add(s)
                    r["sector"] = ""
                else:
                    r["sector"] = s
            T.set_portfolio(recs)
            if bad:
                st.warning(f"Imported {len(recs)} rows. Cleared {len(bad)} unrecognised "
                           f"sector(s) — reassign from the taxonomy: {', '.join(sorted(bad))}")
            else:
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
