"""
Page 8 – Calculation Audit Trail
Full step-by-step trace: hazard source → warming → multiplier → intensity → damage fraction → EAD → PV
"""

import streamlit as st
import pandas as pd
import numpy as np

from engine.asset_model import Asset as _Asset
from engine.scenario_model import SCENARIOS, get_warming, get_hazard_multiplier, HAZARD_SCALING_SOURCES
from engine.hazard_fetcher import _load_baseline
from engine.impact_functions import get_damage_fraction, HAZARD_UNITS
from engine.ead_calculator import calc_ead
from engine.data_sources import DATA_SOURCE_REGISTRY
from engine.export_engine import export_audit_xlsx, df_to_xlsx

st.set_page_config(page_title="Audit Trail", page_icon="🔍", layout="wide")

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    st.metric("Assets", n)

st.title("Calculation Audit Trail")
st.markdown(
    "Full transparency into every number. Select any asset / scenario / year / hazard to see the "
    "complete step-by-step calculation, with source citations for every input."
)

assets = [_Asset.from_dict(a) if isinstance(a, dict) else a
          for a in st.session_state.get("assets", [])]
annual_df = st.session_state.get("annual_damages", pd.DataFrame())
hazard_data_all = st.session_state.get("hazard_data", {})
selected_scenarios = st.session_state.get("selected_scenarios", list(SCENARIOS.keys())[:1])
discount_rate = st.session_state.get("discount_rate", 0.035)

if not assets:
    st.warning("No assets defined.")
    st.stop()

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
hdata = hazard_data_all.get(sel_asset.id, {}).get(sel_hazard)

if not hdata:
    st.info("No hazard data fetched yet. Go to the Hazards page first.")
    st.stop()

rp = np.array(hdata["return_periods"], dtype=float)
base_intens = np.array(hdata["intensities"], dtype=float)
source_key = hdata.get("source", "fallback_baseline")
src_info = DATA_SOURCE_REGISTRY.get(source_key, {})

warming_c = get_warming(sel_scenario, sel_year)
mult = get_hazard_multiplier(sel_hazard, warming_c)

adj_intens = base_intens.copy()
elev_adj = 0.0
if sel_hazard == "flood":
    elev_adj = sel_asset.elevation_m
    adj_intens = np.clip(base_intens - elev_adj, 0.0, None)

scaled_intens = adj_intens * mult
damage_fracs = np.array([get_damage_fraction(sel_hazard, sel_asset.asset_type, i) for i in scaled_intens])
ead = calc_ead(rp, damage_fracs, sel_asset.replacement_value)
pv = ead / (1.0 + discount_rate) ** (sel_year - 2025)

hazard_src = HAZARD_SCALING_SOURCES.get(sel_hazard, {})
unit = HAZARD_UNITS.get(sel_hazard, "")

# ── Display ────────────────────────────────────────────────────────────────
st.divider()
st.subheader(f"Audit: {sel_asset.name} | {SCENARIOS.get(sel_scenario, {}).get('label', sel_scenario)} | {sel_year} | {sel_hazard.capitalize()}")

steps = [
    ("1", "Hazard data source",
     f"**Source:** {src_info.get('name', source_key)}\n\n"
     f"**Citation:** {src_info.get('citation', '')}\n\n"
     f"**URL:** [{src_info.get('url', '')}]({src_info.get('url', '')})\n\n"
     f"**Resolution:** {src_info.get('resolution', 'Regional')}"),

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
     f"**Citation:** {hazard_src.get('citation', '')}\n\n"
     f"**URL:** [{hazard_src.get('url', '')}]({hazard_src.get('url', '')})\n\n"
     f"**Method:** Linear interpolation between IPCC AR6 benchmark warming levels "
     f"([Ch.11]({hazard_src.get('ar6_url', 'https://www.ipcc.ch/report/ar6/wg1/chapter/chapter-11/')}))"),

    ("5", "Asset-specific adjustments",
     f"**Hazard:** {sel_hazard}\n\n" +
     (f"**Floor elevation above flood plain:** {elev_adj:.2f} m → intensities reduced by {elev_adj:.2f} m before multiplication\n\n"
      if sel_hazard == "flood" and elev_adj > 0 else "No adjustments applied for this hazard type.\n\n") +
     f"**Asset type:** {sel_asset.asset_type} | **Material:** {sel_asset.construction_material}"),

    ("6", "Vulnerability curve applied",
     f"**Curve:** {sel_asset.asset_type} × {sel_hazard}\n\n"
     f"**Interpolation:** Monotonic cubic spline (PCHIP) — preserves shape, no negative slopes\n\n"
     f"**Source:** See Vulnerability page for full curve with citations"),

    ("7", "EAD integration",
     f"**Method:** Trapezoidal integration under the exceedance probability (EP) curve\n\n"
     f"**Formula:** EAD = ∫ damage(AEP) d(AEP) ≈ Σ (damage_i + damage_{'{i+1}'}) × |AEP_{'{i+1}'} − AEP_i| / 2\n\n"
     f"**Result:** EAD = **£{ead:,.2f}** ({ead/sel_asset.replacement_value*100:.4f}% of replacement value)\n\n"
     f"**Reference:** Standard catastrophe modelling methodology (Lloyd's, RMS, AIR Worldwide)"),

    ("8", "Present value discounting",
     f"**Formula:** PV = EAD / (1 + r)^(year − 2025)\n\n"
     f"**Discount rate:** {discount_rate*100:.1f}% "
     f"([HM Treasury Green Book](https://www.gov.uk/government/publications/the-green-book-appraisal-and-evaluation-in-central-government))\n\n"
     f"**Calculation:** £{ead:,.2f} / (1 + {discount_rate:.3f})^{sel_year - 2025} = **£{pv:,.2f}**"),
]

for step_num, step_title, step_text in steps:
    with st.expander(f"Step {step_num}: {step_title}", expanded=(step_num in ("2", "7", "8"))):
        st.markdown(step_text)
        if step_num == "2":
            df_intens = pd.DataFrame({
                "Return Period (yr)": rp.astype(int),
                f"Baseline Intensity ({unit})": np.round(base_intens, 4),
                f"After Elevation Adj. ({unit})": np.round(adj_intens, 4),
                f"After Multiplier ({unit})": np.round(scaled_intens, 4),
            })
            st.dataframe(df_intens, use_container_width=True)
        elif step_num == "6":
            df_vul = pd.DataFrame({
                "Return Period (yr)": rp.astype(int),
                f"Adjusted Intensity ({unit})": np.round(scaled_intens, 4),
                "Damage Fraction": np.round(damage_fracs, 6),
                "Loss (£)": np.round(damage_fracs * sel_asset.replacement_value, 2),
            })
            st.dataframe(df_vul, use_container_width=True)
        elif step_num == "7":
            aep = 1.0 / rp
            df_ead = pd.DataFrame({
                "Return Period (yr)": rp.astype(int),
                "AEP": np.round(aep, 6),
                "Damage Fraction": np.round(damage_fracs, 6),
                "Loss (£)": np.round(damage_fracs * sel_asset.replacement_value, 2),
            })
            st.dataframe(df_ead, use_container_width=True)
            st.success(f"**EAD = £{ead:,.2f}** | EAD% = {ead/sel_asset.replacement_value*100:.4f}%")

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
            "Damage Fraction RP100", "EAD (£)", "PV (£)", "EAD % Value", "Data Source"
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
            },
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
