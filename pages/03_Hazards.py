"""
Page 3 – Hazard Data: source transparency, data provenance, intensity tables,
manual overrides, and multi-source optionality.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from engine.asset_model import Asset as _Asset, load_asset_types
from engine.hazard_fetcher import (
    fetch_all_hazards, get_region_zone, get_fallback_detail, _load_baseline
)
from engine.data_sources import DATA_SOURCE_REGISTRY
from engine.impact_functions import get_damage_curve, HAZARD_UNITS
from engine.scenario_model import SCENARIOS

st.set_page_config(page_title="Hazard Data", page_icon="🌊", layout="wide")

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    total_val = sum(a.replacement_value for a in st.session_state.get("assets", []))
    st.metric("Assets", n)
    st.metric("Total Value", f"£{total_val:,.0f}")

st.title("Hazard Data")
st.markdown(
    "Baseline hazard intensity profiles (return-period curves) for every asset. "
    "All sources are fully cited — click **ℹ️** on any source card for resolution, "
    "coverage, and methodology details."
)

assets = [_Asset.from_dict(a) if isinstance(a, dict) else a
          for a in st.session_state.get("assets", [])]
if not assets:
    st.warning("No assets defined. Go to the Portfolio page first.")
    st.stop()

selected_scenarios = st.session_state.get("selected_scenarios", ["current_policies"])
asset_types_catalog = load_asset_types()

# ── Source Registry ────────────────────────────────────────────────────────
st.divider()
st.subheader("Available Data Sources")
st.caption(
    "Sources are tried in priority order. Currently all assets use the **Built-in Regional Baseline** "
    "(see status below). Higher-resolution sources require optional Python dependencies "
    "(xarray, rasterio) or are region-specific."
)

def _has_dep(mod):
    import importlib.util
    return importlib.util.find_spec(mod) is not None

_has_xarray   = _has_dep("xarray")
_has_rasterio = _has_dep("rasterio")

SOURCE_STATUS = {
    "isimip3b": {
        "status": "active",
        "badge": "🟢 Active — Flood, Heat, Wind",
        "note": "isimip-client installed ✅; async point-extraction at 0.25–0.5°; ~60s per asset",
    },
    "nasa_nex_gddp_cmip6": {
        "status": "active" if _has_xarray else "deps",
        "badge": "🟢 Available" if _has_xarray else "🟡 Requires xarray",
        "note": "25km global; xarray installed ✅" if _has_xarray else "Install xarray to enable (pip install xarray)",
    },
    "chelsa_cmip6": {
        "status": "active" if _has_rasterio else "deps",
        "badge": "🟢 Available" if _has_rasterio else "🟡 Requires rasterio",
        "note": "1km global; rasterio installed ✅" if _has_rasterio else "Install rasterio to enable (pip install rasterio)",
    },
    "loca2": {
        "status": "regional",
        "badge": "🔵 N. America only",
        "note": "6km CONUS+Canada+Mexico; requires NetCDF file access",
    },
    "climatena_adaptwest": {
        "status": "regional",
        "badge": "🔵 N. America only",
        "note": "1km N. America; REST API available",
    },
    "fallback_baseline": {
        "status": "active",
        "badge": "🟢 Active",
        "note": "Always available; 7 global zones; ~continental resolution",
    },
}

PRIORITY_ORDER = [
    "isimip3b", "nasa_nex_gddp_cmip6", "chelsa_cmip6",
    "loca2", "climatena_adaptwest", "fallback_baseline"
]

HAZARD_UNIT_LABELS = {
    "flood": "Inundation depth (m)",
    "wind": "3-s gust wind speed (m/s)",
    "wildfire": "Flame length (m)",
    "heat": "Max daily temperature (°C)",
}

cols = st.columns(3)
for idx, src_key in enumerate(PRIORITY_ORDER):
    info = DATA_SOURCE_REGISTRY[src_key]
    status = SOURCE_STATUS[src_key]
    with cols[idx % 3]:
        with st.container(border=True):
            header_col, btn_col = st.columns([4, 1])
            with header_col:
                st.markdown(f"**{info['name']}**")
                st.caption(status["badge"])
            with btn_col:
                with st.popover("ℹ️"):
                    st.markdown(f"### {info['name']}")
                    st.markdown(f"**Description:** {info['description']}")
                    st.markdown(f"**Resolution:** {info['resolution']}")
                    st.markdown(f"**Hazards:** {', '.join(h.capitalize() for h in info['hazards'])}")
                    if info.get("coverage"):
                        st.markdown(f"**Coverage:** {info['coverage']}")
                    st.markdown(f"**Citation:** *{info['citation']}*")
                    st.markdown(f"**URL:** [{info['url']}]({info['url']})")
                    if info.get("doi"):
                        st.markdown(f"**DOI:** [{info['doi']}]({info['doi']})")
                    st.divider()
                    st.caption(f"⚙️ {status['note']}")
            st.caption(f"↳ {status['note']}")

# ── Source Preference ──────────────────────────────────────────────────────
st.divider()
st.subheader("Source Settings")

col_pref, col_zone = st.columns(2)
with col_pref:
    source_pref = st.selectbox(
        "Preferred source",
        options=PRIORITY_ORDER,
        index=PRIORITY_ORDER.index(st.session_state.get("preferred_source", "fallback_baseline")),
        format_func=lambda k: f"{DATA_SOURCE_REGISTRY[k]['name']} — {SOURCE_STATUS[k]['badge']}",
        help=(
            "When the preferred source is unavailable, the next available source in "
            "the priority chain is used automatically. All sources ultimately fall back "
            "to the Built-in Regional Baseline."
        ),
    )
    st.session_state.preferred_source = source_pref
    if source_pref != "fallback_baseline":
        if SOURCE_STATUS[source_pref]["status"] in ("deps", "partial", "regional"):
            st.info(
                f"⚠️ **{DATA_SOURCE_REGISTRY[source_pref]['name']}** is not currently active "
                f"({SOURCE_STATUS[source_pref]['note']}). "
                f"Data will fall back to **Built-in Regional Baseline** until the dependency is resolved.",
                icon="ℹ️",
            )

with col_zone:
    st.markdown("**Regional Zone Overrides**")
    st.caption(
        "The auto-detected zone for each asset is shown in the table below. "
        "Override here if your asset is in an atypical climate microzone."
    )
    zone_overrides = st.session_state.get("zone_overrides", {})
    zones = ["AUTO", "EUR", "USA", "CHN", "IND", "AUS", "BRA", "global"]
    zone_desc = {
        "AUTO": "Auto-detect from country code",
        "EUR": "Europe (GBR, FRA, DEU, ITA, ESP...)",
        "USA": "North America (USA, CAN, MEX)",
        "CHN": "East Asia (CHN, JPN, KOR, TWN)",
        "IND": "South Asia (IND, PAK, BGD, LKA)",
        "AUS": "Oceania (AUS, NZL)",
        "BRA": "South America (BRA, ARG, COL, PER)",
        "global": "Global median (conservative)",
    }
    sel_asset_for_zone = st.selectbox(
        "Asset to override zone",
        options=[a.id for a in assets],
        format_func=lambda i: next((a.name for a in assets if a.id == i), i),
        key="zone_override_asset",
    )
    current_zone = zone_overrides.get(sel_asset_for_zone, "AUTO")
    new_zone = st.selectbox(
        "Zone",
        options=zones,
        index=zones.index(current_zone) if current_zone in zones else 0,
        format_func=lambda z: f"{z} — {zone_desc.get(z, z)}",
        key="zone_override_val",
    )
    if new_zone == "AUTO":
        zone_overrides.pop(sel_asset_for_zone, None)
    else:
        zone_overrides[sel_asset_for_zone] = new_zone
    st.session_state.zone_overrides = zone_overrides

# ── Fetch ──────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Fetch Hazard Data")

if "hazard_data" not in st.session_state:
    st.session_state.hazard_data = {}

col_btn, col_info = st.columns([2, 5])
with col_btn:
    fetch_btn = st.button("🔄 Fetch / Refresh All Assets", type="primary", use_container_width=True)
with col_info:
    st.caption(
        f"Fetches baseline intensity profiles for all {len(assets)} asset(s) across "
        "Flood, Wind, Wildfire, and Heat hazards. Uses the highest-priority "
        "available source (currently: Built-in Regional Baseline for all hazards)."
    )

if fetch_btn:
    progress = st.progress(0, text="Fetching hazard data...")
    scenario_id = selected_scenarios[0] if selected_scenarios else "current_policies"
    ssp = SCENARIOS.get(scenario_id, {}).get("ssp", "SSP2-4.5")
    for i, asset in enumerate(assets):
        hazards = asset_types_catalog.get(asset.asset_type, {}).get(
            "hazards", ["flood", "wind", "wildfire", "heat"]
        )
        # Apply zone override if set
        region = zone_overrides.get(asset.id, asset.region)
        if region == "AUTO":
            region = asset.region
        data = fetch_all_hazards(asset.lat, asset.lon, region, hazards, ssp, "2041_2060")
        st.session_state.hazard_data[asset.id] = data
        progress.progress((i + 1) / len(assets), text=f"✅ {asset.name}")
    st.success(f"Loaded hazard data for {len(assets)} asset(s).")
    progress.empty()

# ── Data Status Table ──────────────────────────────────────────────────────
st.divider()
st.subheader("Data Status by Asset")

if st.session_state.hazard_data:
    bl = _load_baseline()
    iso_zone_map = bl.get("region_iso3_map", {})

    rows = []
    for asset in assets:
        hdata = st.session_state.hazard_data.get(asset.id, {})
        zone_override = zone_overrides.get(asset.id)
        effective_region = zone_override if (zone_override and zone_override != "AUTO") else asset.region
        zone = get_region_zone(effective_region)

        row = {
            "Asset": asset.name,
            "Country (ISO3)": asset.region.upper(),
            "Zone Applied": zone,
            "Zone Override": zone_override if (zone_override and zone_override != "AUTO") else "—",
        }
        for hazard in ["flood", "wind", "wildfire", "heat"]:
            if hazard in hdata:
                src = hdata[hazard]["source"]
                src_name = DATA_SOURCE_REGISTRY.get(src, {}).get("name", src)
                src_res = DATA_SOURCE_REGISTRY.get(src, {}).get("resolution", "—")
                if src == "fallback_baseline":
                    row[hazard.capitalize()] = f"Regional Baseline ({zone})"
                elif src == "isimip3b":
                    row[hazard.capitalize()] = "ISIMIP3b API"
                else:
                    row[hazard.capitalize()] = src_name
            else:
                row[hazard.capitalize()] = "➖ N/A"
        rows.append(row)

    status_df = pd.DataFrame(rows)
    st.dataframe(status_df, use_container_width=True)

    # Explain regional zones
    with st.expander("📍 How regional zones work"):
        st.markdown("""
The **Built-in Regional Baseline** groups the world into 7 zones based on ISO3 country code:

| Zone | Countries included | Hazard basis |
|------|--------------------|-------------|
| **EUR** | GBR, FRA, DEU, ITA, ESP, NLD, BEL, POL, SWE, NOR + EU/EEA | ISIMIP3b EU medians, EFFIS fire climatology, ERA5-Land |
| **USA** | USA, CAN, MEX | ISIMIP3b N. America, HAZUS wind, ERA5-Land |
| **CHN** | CHN, JPN, KOR, TWN | ISIMIP3b E. Asia, HAZUS-adapted, ERA5-Land |
| **IND** | IND, PAK, BGD, LKA | ISIMIP3b S. Asia, high-heat ERA5 percentiles |
| **AUS** | AUS, NZL | ISIMIP3b Oceania, high wildfire intensity |
| **BRA** | BRA, ARG, COL, PER | ISIMIP3b S. America |
| **global** | All others | ISIMIP3b global median (conservative) |

**Limitation**: The baseline does not capture sub-regional variation within zones (e.g. coastal vs inland flood risk within Europe). For higher spatial precision, enable ISIMIP3b API extraction (requires xarray) or use site-specific data via the manual override panel below.

**Climate adjustment**: These baseline intensities are scaled year-by-year by IPCC AR6 hazard multipliers on the Results page — so a 2050 EAD under Current Policies will be higher than a 2025 EAD for the same asset.
        """)

else:
    st.info("Click **Fetch / Refresh All Assets** to load hazard data.")

# ── Per-Asset Intensity Detail ─────────────────────────────────────────────
st.divider()
st.subheader("Intensity Values & Source Detail")

sel_asset_detail = st.selectbox(
    "Select asset to inspect",
    options=[a.id for a in assets],
    format_func=lambda i: next((a.name for a in assets if a.id == i), i),
    key="detail_asset",
)
sel_asset_obj = next((a for a in assets if a.id == sel_asset_detail), None)

if sel_asset_obj and st.session_state.hazard_data.get(sel_asset_detail):
    hdata = st.session_state.hazard_data[sel_asset_detail]
    zone_override = zone_overrides.get(sel_asset_detail)
    effective_region = zone_override if (zone_override and zone_override != "AUTO") else sel_asset_obj.region
    zone = get_region_zone(effective_region)

    st.markdown(
        f"**Asset:** {sel_asset_obj.name} | "
        f"**Country:** {sel_asset_obj.region.upper()} | "
        f"**Zone:** {zone}"
        + (f" *(overridden from auto)*" if zone_override and zone_override != "AUTO" else "")
    )

    haz_tabs = [h for h in ["flood", "wind", "wildfire", "heat"] if h in hdata]
    if haz_tabs:
        tabs = st.tabs([f"🌊 Flood" if h == "flood"
                        else f"💨 Wind" if h == "wind"
                        else f"🔥 Wildfire" if h == "wildfire"
                        else f"🌡️ Heat"
                        for h in haz_tabs])

        for tab, hazard in zip(tabs, haz_tabs):
            with tab:
                hd = hdata[hazard]
                src_key = hd.get("source", "fallback_baseline")
                src_info = DATA_SOURCE_REGISTRY.get(src_key, {})
                detail = get_fallback_detail(hazard, effective_region)

                # Source provenance banner
                prov_col, info_col = st.columns([5, 1])
                with prov_col:
                    if src_key == "fallback_baseline":
                        st.info(
                            f"**Source:** Built-in Regional Baseline — **{zone} zone** | "
                            f"**Resolution:** Continental (7 global zones) | "
                            f"**Basis:** {detail['hazard_source']}",
                            icon="⚠️",
                        )
                    else:
                        st.success(
                            f"**Source:** {src_info.get('name', src_key)} | "
                            f"**Resolution:** {src_info.get('resolution', '—')}",
                            icon="✅",
                        )
                with info_col:
                    with st.popover("ℹ️ Full source info"):
                        st.markdown(f"### Source: {src_info.get('name', src_key)}")
                        st.markdown(f"**{detail['description']}**")
                        st.divider()
                        st.markdown(f"**Data basis:** {detail['hazard_source']}")
                        st.markdown(f"**Citation:** *{detail['citation']}*")
                        st.markdown(f"**URL/DOI:** [{detail['doi']}]({detail['doi']})")
                        st.markdown(f"**Resolution:** {detail['resolution']}")
                        st.markdown(f"**Temporal basis:** {detail['temporal_basis']}")
                        st.markdown(f"**Zone applied:** {zone} — {detail['zone_description']}")
                        st.divider()
                        st.markdown(f"**Climate adjustment:** {detail['climate_adjustment']}")
                        st.caption(
                            "These are *baseline* intensities. On the Results page, "
                            "they are multiplied by the scenario hazard multiplier "
                            "for each year 2025–2050."
                        )

                # Intensity table
                rp_vals = hd["return_periods"]
                int_vals = hd["intensities"]
                unit = HAZARD_UNIT_LABELS.get(hazard, "")

                int_df = pd.DataFrame({
                    "Return Period (yr)": [int(r) for r in rp_vals],
                    "Annual Exceedance Probability": [f"1-in-{int(r)}-yr = {1/r*100:.2f}%/yr" for r in rp_vals],
                    f"Baseline Intensity ({unit})": [round(v, 3) for v in int_vals],
                    "Source": [DATA_SOURCE_REGISTRY.get(src_key, {}).get("name", src_key)] * len(rp_vals),
                    "Zone": [zone] * len(rp_vals),
                })
                st.dataframe(int_df, use_container_width=True)

                # Chart
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=[f"RP{int(r)}" for r in rp_vals],
                    y=int_vals,
                    name=f"Baseline intensity",
                    marker_color="#2980b9",
                    hovertemplate=f"RP%{{x}}<br>Intensity: %{{y:.3f}} {unit}<extra></extra>",
                ))
                fig.update_layout(
                    xaxis_title="Return Period",
                    yaxis_title=unit,
                    height=260,
                    margin=dict(l=20, r=20, t=20, b=20),
                    showlegend=False,
                )
                st.plotly_chart(fig, use_container_width=True)

                st.caption(
                    f"🔬 **Granularity note:** The {zone} zone represents ~continental-scale median values. "
                    f"Actual site-level intensity may vary significantly. "
                    f"Use the override panel below to adjust for local conditions, "
                    f"or upgrade to ISIMIP3b API (requires xarray) for 0.5° gridded data."
                )
else:
    if not st.session_state.hazard_data:
        st.info("Fetch hazard data first to inspect intensity values.")
    else:
        st.info("Select an asset above to view its intensity profile.")

# ── Manual Override Panel ──────────────────────────────────────────────────
st.divider()
st.subheader("Manual Intensity Overrides")
st.markdown(
    "Override specific return-period intensities for any asset and hazard. "
    "Use this to enter site-specific survey data, refine the baseline with "
    "local flood risk assessments (e.g. UK Environment Agency flood maps, "
    "FEMA FIRMs), or apply sensitivity scenarios."
)

if "hazard_overrides" not in st.session_state:
    st.session_state.hazard_overrides = {}

override_asset_id = st.selectbox(
    "Asset to override",
    options=[a.id for a in assets],
    format_func=lambda i: next((a.name for a in assets if a.id == i), i),
    key="override_asset",
)
override_asset = next((a for a in assets if a.id == override_asset_id), None)

if override_asset:
    hazards_for_asset = asset_types_catalog.get(override_asset.asset_type, {}).get(
        "hazards", ["flood", "wind", "wildfire", "heat"]
    )
    selected_hazard = st.selectbox("Hazard", hazards_for_asset, key="override_haz")
    base_data = st.session_state.hazard_data.get(override_asset_id, {}).get(selected_hazard)

    if base_data:
        rps = base_data["return_periods"]
        current_intens = base_data["intensities"]
        unit = HAZARD_UNIT_LABELS.get(selected_hazard, "")

        col_ov, col_src = st.columns([3, 2])
        with col_ov:
            st.markdown(f"**Edit intensities ({unit})**")
            override_df = pd.DataFrame({
                "Return Period (yr)": [int(r) for r in rps],
                f"Intensity ({unit})": current_intens,
            })
            edited = st.data_editor(override_df, num_rows="fixed", use_container_width=True)
        with col_src:
            override_source_note = st.text_area(
                "Source / justification for override (optional)",
                placeholder="e.g. 'Environment Agency Flood Map RP100 depth = 0.8m at this postcode' "
                            "or 'Site survey 2024 — elevated 1.2m above local flood plain'",
                height=160,
                key="override_note",
            )

        if st.button("💾 Save Override", type="primary"):
            if override_asset_id not in st.session_state.hazard_overrides:
                st.session_state.hazard_overrides[override_asset_id] = {}
            st.session_state.hazard_overrides[override_asset_id][selected_hazard] = {
                "return_periods": edited["Return Period (yr)"].tolist(),
                "intensities": edited[f"Intensity ({unit})"].tolist(),
                "source": "manual_override",
                "source_note": override_source_note,
            }
            if override_asset_id not in st.session_state.hazard_data:
                st.session_state.hazard_data[override_asset_id] = {}
            st.session_state.hazard_data[override_asset_id][selected_hazard] = (
                st.session_state.hazard_overrides[override_asset_id][selected_hazard]
            )
            st.success(
                f"Override saved for **{override_asset.name}** / **{selected_hazard}**. "
                "This will be used in all subsequent damage calculations."
            )
    else:
        st.info("Fetch hazard data first, then you can override individual values.")

# Show existing overrides
if any(st.session_state.hazard_overrides.values()):
    with st.expander("📋 Current manual overrides"):
        for aid, haz_overrides in st.session_state.hazard_overrides.items():
            aname = next((a.name for a in assets if a.id == aid), aid)
            for haz, od in haz_overrides.items():
                note = od.get("source_note", "")
                st.markdown(
                    f"**{aname}** / {haz} — "
                    + (f"*{note}*" if note else "*No source note*")
                )

# ── Vulnerability Curve Reference ──────────────────────────────────────────
st.divider()
st.subheader("Vulnerability Curve Reference")
st.caption("For full vulnerability curve auditing, editing, and source citations — see the **Vulnerability** page (Page 9).")

col1, col2 = st.columns(2)
with col1:
    curve_hazard = st.selectbox("Hazard", ["flood", "wind", "wildfire", "heat"], key="curve_haz")
with col2:
    at_catalog = load_asset_types()
    curve_atype = st.selectbox(
        "Asset Type",
        list(at_catalog.keys()),
        format_func=lambda k: at_catalog[k]["label"],
        key="curve_atype",
    )

xs, ys = get_damage_curve(curve_hazard, curve_atype)
if len(xs) > 0:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs, y=ys * 100,
        mode="lines",
        name="Damage fraction",
        line=dict(color="#e74c3c", width=2),
        fill="tozeroy",
        fillcolor="rgba(231,76,60,0.1)",
        hovertemplate=f"Intensity: %{{x:.2f}}<br>Damage: %{{y:.1f}}%<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title=HAZARD_UNITS.get(curve_hazard, "Intensity"),
        yaxis_title="Damage Fraction (%)",
        yaxis=dict(range=[0, 105]),
        height=280,
        margin=dict(l=20, r=20, t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Sources: HAZUS 6.0 (FEMA 2022) | JRC Global DDFs (Huizinga et al. 2017) | "
        "Syphard et al. (2012) | IEA Future of Cooling (2018) | ILO (2019)"
    )
