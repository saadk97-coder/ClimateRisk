"""
Page 8 – Calculation Audit Trail
Full step-by-step trace: hazard source → warming → multiplier → intensity → damage fraction → EAD → PV
"""

import streamlit as st
import pandas as pd
import numpy as np

from engine.asset_model import Asset as _Asset, normalize_asset_state
from engine.hazard_math import (
    DEFAULT_DISPLAY_RETURN_PERIOD_MAX,
    compute_effective_intensities,
    display_return_period_mask,
)
import engine.scenario_model as _scenario_model
import engine.hazard_fetcher as _hazard_fetcher
from engine.impact_functions import get_damage_fraction, HAZARD_UNITS
from engine.ead_calculator import calc_ead
from engine.data_sources import DATA_SOURCE_REGISTRY
from engine.export_engine import export_audit_xlsx, df_to_xlsx
from engine.fmt import currency_symbol as _currency_symbol
from engine.governance import build_run_manifest, override_records as build_override_records

SCENARIOS = getattr(_scenario_model, "SCENARIOS", {})
get_warming = getattr(_scenario_model, "get_warming", None)
get_hazard_multiplier = getattr(_scenario_model, "get_hazard_multiplier", None)
get_scenario_multipliers = getattr(_scenario_model, "get_scenario_multipliers", None)
get_slr_additive = getattr(_scenario_model, "get_slr_additive", None)
HAZARD_SCALING_SOURCES = getattr(_scenario_model, "HAZARD_SCALING_SOURCES", {})
get_region_zone = getattr(_hazard_fetcher, "get_region_zone")
generate_conditional_gev_bands = getattr(_hazard_fetcher, "generate_conditional_gev_bands", None)
uncertainty_status_for_entry = getattr(
    _hazard_fetcher,
    "uncertainty_status_for_entry",
    lambda hazard, entry: "generated" if (entry or {}).get("uncertainty", {}).get("type") == "gev_parameter_uncertainty" else "unavailable",
)
entry_supports_gev_bands = getattr(
    _hazard_fetcher,
    "entry_supports_gev_bands",
    lambda hazard, entry: False,
)

st.set_page_config(page_title="Audit Trail", page_icon="🔍", layout="wide")

assets = normalize_asset_state(st.session_state)

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(assets)
    st.metric("Assets", n)

st.title("Calculation Audit Trail")
st.markdown(
    "Full transparency into every number. Select any asset / scenario / year / hazard to see the "
    "complete step-by-step calculation, with source citations for every input."
)

missing_scenario_helpers = [
    name for name, value in {
        "SCENARIOS": SCENARIOS,
        "get_warming": get_warming,
        "get_hazard_multiplier": get_hazard_multiplier,
        "get_scenario_multipliers": get_scenario_multipliers,
        "get_slr_additive": get_slr_additive,
        "HAZARD_SCALING_SOURCES": HAZARD_SCALING_SOURCES,
    }.items()
    if value is None or value == {}
]
if missing_scenario_helpers:
    st.error(
        "This deployment is missing scenario helpers required by the Audit page: "
        + ", ".join(missing_scenario_helpers)
        + ". The rest of the platform can still be used while this page is restored."
    )
    st.stop()

annual_df = st.session_state.get("annual_damages", pd.DataFrame())
hazard_data_all = st.session_state.get("hazard_data", {})
hazard_data_by_scenario = st.session_state.get("hazard_data_by_scenario", {})
hazard_overrides = st.session_state.get("hazard_overrides", {})
selected_scenarios = st.session_state.get("selected_scenarios") or list(SCENARIOS.keys())[:1]
discount_rate = st.session_state.get("discount_rate", 0.035)
_sym = _currency_symbol(st.session_state.get("currency_code", "GBP"))
all_override_rows = build_override_records(hazard_overrides, assets)


def _run_manifest_years() -> list[int]:
    if not annual_df.empty and "year" in annual_df.columns:
        try:
            return sorted(int(year) for year in annual_df["year"].dropna().astype(int).unique().tolist())
        except Exception:
            pass
    return list(range(2025, 2051))


def _rebuild_run_manifest() -> dict:
    manifest = build_run_manifest(
        annual_damages_df=annual_df,
        selected_scenarios=selected_scenarios,
        years=_run_manifest_years(),
        currency_code=st.session_state.get("currency_code", "GBP"),
        currency_symbol=_sym,
        discount_rate=discount_rate,
        fetch_profile=st.session_state.get("hazard_fetch_mode", getattr(_hazard_fetcher, "DEFAULT_FETCH_MODE", "balanced")),
        override_records=build_override_records(st.session_state.get("hazard_overrides", {}), assets),
        fetch_failures=st.session_state.get("hazard_fetch_failures", []),
        reused_assets=int(st.session_state.get("hazard_run_reused_assets", 0) or 0),
        refreshed_assets=int(st.session_state.get("hazard_run_refreshed_assets", 0) or 0),
        zone_overrides=st.session_state.get("zone_overrides", {}),
        hazard_data_all=st.session_state.get("hazard_data", {}),
    )
    st.session_state.run_manifest = manifest
    return manifest


def _store_generated_gev_entry(asset: _Asset, hazard: str, scenario_id: str | None = None) -> dict | None:
    if generate_conditional_gev_bands is None:
        return None
    refreshed_entry = generate_conditional_gev_bands(
        asset.lat,
        asset.lon,
        hazard,
        asset.region,
        terrain_elevation_asl_m=getattr(asset, "terrain_elevation_asl_m", 0.0),
        asset_type=asset.asset_type,
        fetch_mode=st.session_state.get("hazard_fetch_mode", getattr(_hazard_fetcher, "DEFAULT_FETCH_MODE", "balanced")),
    )
    hazard_data = dict(st.session_state.get("hazard_data", {}))
    asset_hazards = dict(hazard_data.get(asset.id, {}))
    asset_hazards[hazard] = refreshed_entry
    hazard_data[asset.id] = asset_hazards
    st.session_state.hazard_data = hazard_data
    if scenario_id and st.session_state.get("hazard_data_by_scenario"):
        hazard_data_by_scenario = dict(st.session_state.get("hazard_data_by_scenario", {}))
        scenario_hazards = dict(hazard_data_by_scenario.get(scenario_id, {}))
        scenario_asset_hazards = dict(scenario_hazards.get(asset.id, {}))
        scenario_asset_hazards[hazard] = refreshed_entry
        scenario_hazards[asset.id] = scenario_asset_hazards
        hazard_data_by_scenario[scenario_id] = scenario_hazards
        st.session_state.hazard_data_by_scenario = hazard_data_by_scenario
    _rebuild_run_manifest()
    return refreshed_entry

if not assets:
    st.warning("No assets defined.")
    st.stop()

if annual_df is not None and not annual_df.empty and not st.session_state.get("run_manifest"):
    _rebuild_run_manifest()

# ── Selector ───────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
with col1:
    sel_asset = st.selectbox("Asset", assets,
                             format_func=lambda a: a.name if hasattr(a, "name") else str(a))
with col2:
    sel_scenario = st.selectbox("Scenario", selected_scenarios,
                                format_func=lambda s: SCENARIOS.get(s, {}).get("label", s))
with col3:
    sel_year = st.selectbox("Year", list(range(2025, 2051)), index=25)
with col4:
    available_hazards = list(hazard_data_all.get(sel_asset.id if sel_asset else "", {}).keys()) or ["flood", "wind", "wildfire", "heat"]
    sel_hazard = st.selectbox("Hazard", available_hazards)

if not sel_asset:
    st.stop()

# ── Step-by-step audit ────────────────────────────────────────────────────
# Use scenario-specific hazard data if available (matches engine behavior)
if hazard_data_by_scenario and sel_scenario in hazard_data_by_scenario:
    hdata = hazard_data_by_scenario[sel_scenario].get(sel_asset.id, {}).get(sel_hazard)
else:
    hdata = hazard_data_all.get(sel_asset.id, {}).get(sel_hazard)

if not hdata:
    st.info("No hazard data fetched yet. Go to the Hazards page first.")
    st.stop()

rp = np.array(hdata["return_periods"], dtype=float)
base_intens = np.array(hdata["intensities"], dtype=float)
source_key = hdata.get("source", "fallback_baseline")
src_info = DATA_SOURCE_REGISTRY.get(source_key, {})
selected_override_rows = [
    row for row in all_override_rows
    if row["Asset ID"] == sel_asset.id and row["Hazard"] == sel_hazard
]
selected_override = selected_override_rows[0] if selected_override_rows else None

warming_c = get_warming(sel_scenario, sel_year)

# Match engine logic: multiplier applied uniformly to ALL sources.
# Fetched data is treated as a near-term baseline; IPCC AR6 scaling
# provides temporal evolution for the annual curve.
region_zone = get_region_zone(sel_asset.region)
mult = get_scenario_multipliers(sel_scenario, sel_year, sel_hazard, region_zone)
mult_note = f"Region zone: {region_zone} (from {sel_asset.region})"

scaled_intens, adjustment_ctx = compute_effective_intensities(
    sel_hazard,
    base_intens,
    mult,
    sel_asset,
    scenario_id=sel_scenario,
    year=sel_year,
    region_zone=region_zone,
)
elev_adj = adjustment_ctx.freeboard_m
slr_m = adjustment_ctx.slr_additive_m
terrain_adj = adjustment_ctx.terrain_elevation_asl_m
visible_mask = display_return_period_mask(rp)
if not np.any(visible_mask):
    visible_mask = np.ones(len(rp), dtype=bool)
uncertainty = (hdata or {}).get("uncertainty", {})
uncertainty_status = uncertainty_status_for_entry(sel_hazard, hdata)
uncertainty_detail = str((hdata or {}).get("uncertainty_detail", "")).strip()

damage_fracs = np.array([get_damage_fraction(sel_hazard, sel_asset.asset_type, i) for i in scaled_intens])

# Use the same pathway as the engine: chronic hazards (water_stress) use
# median damage fraction × value, not trapezoidal EP-curve integration.
from engine.ead_calculator import CHRONIC_HAZARDS
if sel_hazard in CHRONIC_HAZARDS:
    rp50_idx = int(np.argmin(np.abs(rp - 50)))
    median_frac = float(damage_fracs[rp50_idx])
    ead = median_frac * sel_asset.replacement_value
else:
    ead = calc_ead(rp, damage_fracs, sel_asset.replacement_value)
pv = ead / (1.0 + discount_rate) ** (sel_year - 2025)

hazard_src = HAZARD_SCALING_SOURCES.get(sel_hazard, {})
unit = HAZARD_UNITS.get(sel_hazard, "")

if selected_override:
    st.warning(
        "This calculation uses a manual hazard override. Review the recorded evidence source, "
        "preparer, and timestamp before relying on the result.",
        icon="⚠️",
    )

# ── Display ────────────────────────────────────────────────────────────────
st.divider()
st.subheader(f"Audit: {sel_asset.name} | {SCENARIOS.get(sel_scenario, {}).get('label', sel_scenario)} | {sel_year} | {sel_hazard.capitalize()}")

source_text = (
    f"**Source:** {src_info.get('name', source_key)}\n\n"
    f"**Citation:** {src_info.get('citation', '')}\n\n"
    f"**URL:** [{src_info.get('url', '')}]({src_info.get('url', '')})\n\n"
    f"**Resolution:** {src_info.get('resolution', 'Regional')}"
)
if selected_override:
    source_text = (
        f"**Source:** Manual override\n\n"
        f"**Replaces source:** {selected_override.get('Replaces source', '')}\n\n"
        f"**Override basis:** {selected_override.get('Override basis', '')}\n\n"
        f"**Source / justification:** {selected_override.get('Source / justification', '')}\n\n"
        f"**Prepared by:** {selected_override.get('Prepared by', '')}\n\n"
        f"**Prepared at (UTC):** {selected_override.get('Prepared at (UTC)', '')}"
    )

if sel_hazard in CHRONIC_HAZARDS:
    integration_text = (
        f"**Method:** Chronic hazard pathway using the median damage fraction at RP50\n\n"
        f"**Formula:** EAD = damage_fraction(RP50) × replacement_value\n\n"
        f"**Result:** EAD = **{_sym}{ead:,.2f}** ({ead/sel_asset.replacement_value*100:.4f}% of replacement value)\n\n"
        f"**Reference:** WRI Aqueduct pathway as implemented in the engine for chronic water stress."
    )
else:
    integration_text = (
        f"**Method:** Trapezoidal integration under the exceedance probability (EP) curve\n\n"
        f"**Formula:** EAD = ∫ damage(AEP) d(AEP) ≈ Σ (damage_i + damage_{{i+1}}) × |AEP_{{i+1}} − AEP_i| / 2\n\n"
        f"**Result:** EAD = **{_sym}{ead:,.2f}** ({ead/sel_asset.replacement_value*100:.4f}% of replacement value)\n\n"
        f"**Reference:** Standard catastrophe modelling style EP-curve integration."
    )

steps = [
    ("1", "Hazard data source",
     source_text),

    ("2", "Baseline hazard intensities at return periods",
     "Baseline intensities before any climate adjustment:"),

    ("3", "Scenario warming trajectory",
     f"**Scenario:** {SCENARIOS.get(sel_scenario, {}).get('label', sel_scenario)} "
     f"({SCENARIOS.get(sel_scenario, {}).get('ssp', '')})\n\n"
     f"**Warming at {sel_year}:** **{warming_c:.2f} °C** above pre-industrial (1850–1900 baseline)\n\n"
     f"**Source:** {SCENARIOS.get(sel_scenario, {}).get('provider', 'NGFS Phase V')} | "
     f"[{SCENARIOS.get(sel_scenario, {}).get('source_url', '')}]({SCENARIOS.get(sel_scenario, {}).get('source_url', '')})"),

    ("4", "Hazard intensity multiplier",
     f"**Multiplier:** {mult:.4f}× (baseline intensities scaled by this factor)\n\n"
     f"**Derivation:** {warming_c:.2f} °C warming → {mult:.4f}× {sel_hazard} intensity\n\n"
     f"**{mult_note}**\n\n"
     f"**Citation:** {hazard_src.get('citation', '')}\n\n"
     f"**URL:** [{hazard_src.get('url', '')}]({hazard_src.get('url', '')})\n\n"
     f"**Method:** Linear interpolation between IPCC AR6 benchmark warming levels "
     f"([Ch.11]({hazard_src.get('ar6_url', 'https://www.ipcc.ch/report/ar6/wg1/chapter/chapter-11/')}))"),

    ("5", "Asset-specific adjustments",
     f"**Hazard:** {sel_hazard}\n\n" +
     (f"**First-floor height above ground:** {elev_adj:.2f} m → subtracted AFTER multiplier scaling (not multiplied)\n\n"
      if sel_hazard in ("flood", "coastal_flood") else "") +
     (f"**Terrain elevation above sea level:** {terrain_adj:.2f} m → subtracted from coastal effective depth after storm scaling and SLR\n\n"
      if sel_hazard == "coastal_flood" else "") +
     (f"**Applied formula:** `{adjustment_ctx.formula_label}`\n\n"
      if sel_hazard in ("flood", "coastal_flood") else "No physical offset adjustments applied for this hazard type.\n\n") +
     f"**Asset type:** {sel_asset.asset_type} | **Material:** {sel_asset.construction_material}"),

    ("6", "Vulnerability curve applied",
     f"**Curve:** {sel_asset.asset_type} × {sel_hazard}\n\n"
     f"**Interpolation:** Monotonic cubic spline (PCHIP) — preserves shape, no negative slopes\n\n"
     f"**Source:** See Vulnerability page for full curve with citations"),

    ("7", "EAD integration",
     integration_text),

    ("8", "Present value discounting",
     f"**Formula:** PV = EAD / (1 + r)^(year − 2025)\n\n"
     f"**Discount rate:** {discount_rate*100:.1f}% "
     f"([HM Treasury Green Book](https://www.gov.uk/government/publications/the-green-book-appraisal-and-evaluation-in-central-government))\n\n"
     f"**Calculation:** {_sym}{ead:,.2f} / (1 + {discount_rate:.3f})^{sel_year - 2025} = **{_sym}{pv:,.2f}**"),
]

for step_num, step_title, step_text in steps:
    with st.expander(f"Step {step_num}: {step_title}", expanded=(step_num in ("2", "7", "8"))):
        st.markdown(step_text)
        if step_num == "2":
            after_mult = base_intens * mult
            df_intens = pd.DataFrame({
                "Return Period (yr)": rp[visible_mask].astype(int),
                f"Baseline Intensity ({unit})": np.round(base_intens[visible_mask], 4),
                f"After Multiplier ({unit})": np.round(after_mult[visible_mask], 4),
                f"Effective ({unit})": np.round(scaled_intens[visible_mask], 4),
            })
            st.dataframe(df_intens, use_container_width=True)
            if np.any(rp > DEFAULT_DISPLAY_RETURN_PERIOD_MAX):
                st.caption(
                    f"Standard audit view stops at RP{int(DEFAULT_DISPLAY_RETURN_PERIOD_MAX)}. "
                    "Longer-tail points remain high-uncertainty screening outputs."
                )
            if uncertainty.get("type") == "gev_parameter_uncertainty":
                df_unc = pd.DataFrame({
                    "Return Period (yr)": np.asarray(uncertainty.get("return_periods", []), dtype=float)[visible_mask].astype(int),
                    f"Lower band ({unit})": np.round(np.asarray(uncertainty.get("lower", []), dtype=float)[visible_mask], 4),
                    f"Central ({unit})": np.round(np.asarray(uncertainty.get("central", []), dtype=float)[visible_mask], 4),
                    f"Upper band ({unit})": np.round(np.asarray(uncertainty.get("upper", []), dtype=float)[visible_mask], 4),
                })
                st.caption(
                    f"{uncertainty.get('band_label', 'Conditional parameter band')} shown below. "
                    f"{uncertainty.get('limitation', '')}"
                )
                st.dataframe(df_unc, use_container_width=True)
            elif uncertainty_status == "deferred":
                st.info(
                    uncertainty_detail
                    or "Conditional GEV parameter bands are available on demand and were not generated in the standard run."
                )
            elif uncertainty_status == "failed":
                st.warning(
                    uncertainty_detail
                    or "Conditional GEV parameter bands could not be generated from cached basis."
                )
            elif uncertainty_status == "unavailable":
                st.caption(
                    uncertainty_detail
                    or "Conditional GEV parameter bands are unavailable for this hazard-source path."
                )
            if uncertainty_status in {"deferred", "failed"} and entry_supports_gev_bands(sel_hazard, hdata):
                if st.button(
                    "Generate conditional GEV bands",
                    key=f"audit-generate-gev-{sel_asset.id}-{sel_hazard}",
                ):
                    with st.spinner("Generating conditional GEV parameter bands from cached basis..."):
                        refreshed_entry = _store_generated_gev_entry(sel_asset, sel_hazard, sel_scenario)
                    if refreshed_entry is not None:
                        st.rerun()
        elif step_num == "6":
            df_vul = pd.DataFrame({
                "Return Period (yr)": rp[visible_mask].astype(int),
                f"Adjusted Intensity ({unit})": np.round(scaled_intens[visible_mask], 4),
                "Damage Fraction": np.round(damage_fracs[visible_mask], 6),
                f"Loss ({_sym})": np.round((damage_fracs * sel_asset.replacement_value)[visible_mask], 2),
            })
            st.dataframe(df_vul, use_container_width=True)
        elif step_num == "7":
            aep = 1.0 / rp
            df_ead = pd.DataFrame({
                "Return Period (yr)": rp[visible_mask].astype(int),
                "AEP": np.round(aep[visible_mask], 6),
                "Damage Fraction": np.round(damage_fracs[visible_mask], 6),
                f"Loss ({_sym})": np.round((damage_fracs * sel_asset.replacement_value)[visible_mask], 2),
            })
            st.dataframe(df_ead, use_container_width=True)
            if sel_hazard in CHRONIC_HAZARDS:
                st.caption("For chronic water stress, the engine uses the RP50 damage fraction as the representative annual chronic loss state.")
            st.success(f"**EAD = {_sym}{ead:,.2f}** | EAD% = {ead/sel_asset.replacement_value*100:.4f}%")

# ── Full audit table ───────────────────────────────────────────────────────
st.divider()
st.subheader("Full Calculation Table")

if not annual_df.empty:
    asset_audit = annual_df[
        (annual_df["asset_id"] == sel_asset.id) &
        (annual_df["scenario_id"] == sel_scenario) &
        (annual_df["hazard"] == sel_hazard)
    ].copy()

    if not asset_audit.empty:
        asset_audit_display = asset_audit[[
            "year", "warming_c", "multiplier",
            "baseline_intensity_rp100", "adjusted_intensity_rp100",
            "damage_fraction_rp100", "ead", "pv", "ead_pct_value", "data_source"
        ]].copy()
        asset_audit_display.columns = [
            "Year", "Warming (°C)", "Hazard Multiplier",
            f"Baseline Intensity RP100 ({unit})", f"Adjusted Intensity RP100 ({unit})",
            "Damage Fraction RP100", f"EAD ({_sym})", f"PV ({_sym})", "EAD % Value", "Data Source"
        ]
        st.dataframe(asset_audit_display, use_container_width=True)

        # Download
        audit_xlsx = export_audit_xlsx(
            asset_audit_display,
            metadata={
                "Asset": sel_asset.name,
                "Scenario": SCENARIOS.get(sel_scenario, {}).get("label", sel_scenario),
                "Hazard": sel_hazard,
                "Data source": source_key,
                "Source citation": src_info.get("citation", ""),
                "Source URL": src_info.get("url", ""),
                "Discount rate": f"{discount_rate*100:.1f}%",
                "Method pathway": "Chronic RP50 x value" if sel_hazard in CHRONIC_HAZARDS else "Acute EP-curve integration",
            },
            run_manifest=st.session_state.get("run_manifest"),
            override_records=selected_override_rows,
        )
        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button(
                "⬇️ Download Audit Trail (.xlsx)", data=audit_xlsx,
                file_name=f"audit_{sel_asset.id}_{sel_scenario}_{sel_hazard}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with col_b:
            csv_bytes = asset_audit.to_csv(index=False).encode()
            st.download_button("⬇️ Download Audit Trail (.csv)", data=csv_bytes,
                               file_name=f"audit_{sel_asset.id}_{sel_scenario}_{sel_hazard}.csv",
                               mime="text/csv")

# ── Data source registry ───────────────────────────────────────────────────
st.divider()
with st.expander("📚 Data Source Registry — all citations"):
    for key, info in DATA_SOURCE_REGISTRY.items():
        st.markdown(
            f"**{info['name']}** — {info['description']}\n\n"
            f"Citation: *{info['citation']}*  |  [{info['url']}]({info['url']})"
        )
        st.divider()
