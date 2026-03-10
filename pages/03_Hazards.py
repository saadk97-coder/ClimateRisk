"""
Page 3 – Hazard Data: source transparency, data provenance, intensity tables,
damage function explainer, manual overrides, and multi-source optionality.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from engine.asset_model import Asset as _Asset, load_asset_types
from engine.fmt import fmt as _fmt_cur
from engine.hazard_fetcher import (
    fetch_all_hazards, get_region_zone, get_fallback_detail, _load_baseline
)
from engine.data_sources import DATA_SOURCE_REGISTRY
from engine.impact_functions import get_damage_curve, get_damage_fraction, HAZARD_UNITS
from engine.scenario_model import SCENARIOS

st.set_page_config(page_title="Hazard Data", page_icon="🌊", layout="wide")

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    total_val = sum(a.replacement_value for a in st.session_state.get("assets", []))
    st.metric("Assets", n)
    st.metric("Total Value", _fmt_cur(total_val, st.session_state.get("currency_code", "GBP")))

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
    "Sources are tried in priority order: ISIMIP3b → NASA NEX-GDDP → CHELSA → Regional Baseline. "
    "ISIMIP3b is active for **all four hazards** (Flood, Heat, Wind, Wildfire) and extracts "
    "point data at the exact asset coordinate. "
    "Wildfire uses the full Canadian FWI system (Van Wagner 1987) from multi-variable extraction."
)

SOURCE_STATUS = {
    "isimip3b": {
        "status": "active",
        "badge": "🟢 Active — Flood, Heat, Wind, Wildfire",
        "note": (
            "Point-extraction at asset coordinates (0.5° grid cell). "
            "Wildfire: multi-variable FWI pipeline (tasmax + pr + hurs + sfcWind → "
            "Canadian FWI system → GEV → flame length). ~90s per asset for wildfire."
        ),
    },
    "nasa_nex_gddp_cmip6": {
        "status": "active",
        "badge": "🟢 Available",
        "note": "25 km global; statistically downscaled CMIP6; public AWS S3 access",
    },
    "chelsa_cmip6": {
        "status": "active",
        "badge": "🟢 Available",
        "note": "1 km global bioclimatic climatologies; public cloud-hosted GeoTIFF",
    },
    "loca2": {
        "status": "regional",
        "badge": "🔵 N. America only",
        "note": "6 km CONUS+Canada+Mexico; daily downscaled CMIP6",
    },
    "climatena_adaptwest": {
        "status": "regional",
        "badge": "🔵 N. America only",
        "note": "1 km N. America; REST API available",
    },
    "fallback_baseline": {
        "status": "active",
        "badge": "🟢 Active (fallback)",
        "note": "Always available; 7 continental-scale zones; coarsest resolution",
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

# ── Source cards ───────────────────────────────────────────────────────────
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

# ── Comparative Source Explainer ──────────────────────────────────────────
with st.expander("📊 Comparative Source Guide — which source should you use?"):
    st.markdown("""
### Data Source Comparison

| Source | Resolution | Coverage | Hazards | Temporal Range | Best For |
|--------|-----------|----------|---------|----------------|----------|
| **ISIMIP3b** | 0.5° (~55 km) | Global | Flood, Heat, Wind, Wildfire | 2021–2050 (SSP projections) | **Default choice** — covers all hazards with GEV-fitted return periods from bias-adjusted GCM output |
| **NASA NEX-GDDP-CMIP6** | 0.25° (~25 km) | Global | Heat, Wind, (Flood via precip) | 1950–2100 | Higher spatial resolution than ISIMIP; 35 CMIP6 models; good for heat/wind analysis |
| **CHELSA CMIP6** | 30 arc-sec (~1 km) | Global (land) | Heat, Precipitation | Climatologies (30-yr means) | **Highest resolution** for temperature-based hazards; ideal for topographically complex terrain |
| **LOCA2** | 1/16° (~6 km) | N. America | Heat, Flood | 1950–2100 | Best resolution for North American assets; daily data enables extreme event analysis |
| **ClimateNA / AdaptWest** | ~1 km | N. America | Heat | Bioclimatic periods | High-res North American temperature and bioclimatic variables |
| **Built-in Regional Baseline** | Continental (~7 zones) | Global | All four | 1981–2010 climatology | Instant fallback; no API calls needed; very coarse |

### Key Trade-offs

**Resolution vs. Coverage:** CHELSA offers ~1 km resolution but only climatological means (no daily extremes for GEV fitting). ISIMIP3b has daily data enabling proper extreme-value statistics but at coarser 0.5° resolution.

**Gridded vs. Point:** ISIMIP3b and NASA NEX-GDDP extract the value from the grid cell containing your asset's coordinates. The grid cell centre may be up to ~25–28 km from the actual site. For assets near coastlines, elevation transitions, or urban heat islands, this can introduce bias.

**Regional Baseline (fallback):** Uses continental-zone medians — all assets in the same zone (e.g. all of Europe) receive identical hazard intensities. Only appropriate as a last resort or for portfolio-level screening.
    """)

    st.markdown("### Recommended Additional Sources")
    st.markdown("""
The following high-quality databases are used in professional climate risk work and could enhance this tool:

| Database | Resolution | Coverage | Strengths | Access |
|----------|-----------|----------|-----------|--------|
| **Copernicus CDS ERA5/ERA5-Land** | 9–31 km | Global | Gold-standard reanalysis; hourly/daily; 1950–present | Free (CDS API, registration required) |
| **JRC Global Flood Maps (GloFAS/GLOFRIS)** | 1 km flood maps, 0.1° hydrology | Global | Direct inundation depth maps at return periods; used by EU Taxonomy | Free (JRC data portal) |
| **Fathom Global Flood Maps** | 30 m (coastal+fluvial+pluvial) | Global | Industry standard for asset-level flood risk; used by Moody's, S&P, MSCI | Commercial (academic access available) |
| **Swiss Re CatNet** | Varies (often <1 km) | Global | Multi-peril; used in (re)insurance pricing | Commercial |
| **Munich Re NATHAN** | Varies | Global | Multi-peril risk scores; used in insurance underwriting | Commercial |
| **FIRMS / MODIS Active Fire** | 375 m–1 km | Global | Satellite-observed fire data; good for wildfire exposure validation | Free (NASA FIRMS) |
| **Global Wind Atlas (DTU)** | 250 m | Global | Wind resource/hazard at very high resolution | Free |
| **Aqueduct 4.0 (WRI)** | Sub-catchment | Global | Water stress (already integrated); 3 SSP scenarios to 2080 | Free (CC BY 4.0) |
    """)

# ── Source Preference ──────────────────────────────────────────────────────
st.divider()
st.subheader("Source Settings")

col_pref, col_zone = st.columns(2)
with col_pref:
    source_pref = st.selectbox(
        "Preferred source",
        options=PRIORITY_ORDER,
        index=PRIORITY_ORDER.index(st.session_state.get("preferred_source", "isimip3b")),
        format_func=lambda k: f"{DATA_SOURCE_REGISTRY[k]['name']} — {SOURCE_STATUS[k]['badge']}",
        help=(
            "When the preferred source is unavailable for a given hazard, the next available "
            "source in the priority chain is used automatically. All sources ultimately fall back "
            "to the Built-in Regional Baseline."
        ),
    )
    st.session_state.preferred_source = source_pref
    if source_pref != "fallback_baseline":
        if SOURCE_STATUS[source_pref]["status"] in ("deps", "partial", "regional"):
            st.info(
                f"⚠️ **{DATA_SOURCE_REGISTRY[source_pref]['name']}** is not currently active "
                f"({SOURCE_STATUS[source_pref]['note']}). "
                f"Data will fall back through the priority chain until an active source is found.",
                icon="ℹ️",
            )

with col_zone:
    st.markdown("**Regional Zone Overrides** *(fallback baseline only)*")
    st.caption(
        "Zones only apply when data falls back to the Built-in Regional Baseline. "
        "When ISIMIP3b or other gridded sources are active, data is extracted directly "
        "at the asset's coordinates — zones are not used."
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
        "Flood, Wind, Wildfire, and Heat hazards. The system tries ISIMIP3b first "
        "(point extraction at the asset's lat/lon), then falls through the priority chain."
    )

if fetch_btn:
    progress = st.progress(0, text="Fetching hazard data...")
    scenario_id = selected_scenarios[0] if selected_scenarios else "current_policies"
    ssp = SCENARIOS.get(scenario_id, {}).get("ssp", "SSP2-4.5")
    for i, asset in enumerate(assets):
        hazards = asset_types_catalog.get(asset.asset_type, {}).get(
            "hazards", ["flood", "wind", "wildfire", "heat"]
        )
        # Apply zone override if set (only affects fallback baseline)
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
            "Lat": round(asset.lat, 4),
            "Lon": round(asset.lon, 4),
            "Country": asset.region.upper(),
        }
        for hazard in ["flood", "wind", "wildfire", "heat"]:
            if hazard in hdata:
                src = hdata[hazard]["source"]
                if src == "fallback_baseline":
                    row[hazard.capitalize()] = f"Baseline ({zone} zone)"
                elif src == "isimip3b":
                    # Show the grid cell reference
                    grid_lat = round(round(asset.lat * 2) / 2, 1)
                    grid_lon = round(round(asset.lon * 2) / 2, 1)
                    row[hazard.capitalize()] = f"ISIMIP3b ({grid_lat}°, {grid_lon}°)"
                else:
                    src_name = DATA_SOURCE_REGISTRY.get(src, {}).get("name", src)
                    row[hazard.capitalize()] = src_name
            else:
                row[hazard.capitalize()] = "-- N/A"
        rows.append(row)

    status_df = pd.DataFrame(rows)
    st.dataframe(status_df, use_container_width=True)

    # Explain spatial reference
    with st.expander("📍 How spatial referencing works"):
        st.markdown("""
**Gridded sources (ISIMIP3b, NASA NEX-GDDP, CHELSA):** Data is extracted from the grid cell
containing the asset's exact latitude/longitude coordinates. The table above shows the grid cell
centre coordinate for each hazard.

- **ISIMIP3b** uses a 0.5° grid (~55 km at the equator). The nearest grid cell centre is shown.
- **NASA NEX-GDDP** uses a 0.25° grid (~25 km). Higher spatial precision than ISIMIP3b.
- **CHELSA** uses a 30 arc-second grid (~1 km). Near-site-level precision for temperature.

**Built-in Regional Baseline (fallback):** When gridded sources are unavailable, data falls back to
continental-zone medians. All assets in the same zone receive identical intensities. The zone
is auto-detected from the asset's ISO3 country code:

| Zone | Countries | Hazard basis |
|------|-----------|-------------|
| **EUR** | GBR, FRA, DEU, ITA, ESP + EU/EEA | ISIMIP3b EU medians, EFFIS, ERA5-Land |
| **USA** | USA, CAN, MEX | ISIMIP3b N. America, HAZUS wind |
| **CHN** | CHN, JPN, KOR, TWN | ISIMIP3b E. Asia |
| **IND** | IND, PAK, BGD, LKA | ISIMIP3b S. Asia, high-heat ERA5 |
| **AUS** | AUS, NZL | ISIMIP3b Oceania |
| **BRA** | BRA, ARG, COL, PER | ISIMIP3b S. America |
| **global** | All others | ISIMIP3b global median (conservative) |

**Climate adjustment**: Baseline intensities are scaled year-by-year by IPCC AR6 hazard multipliers
on the Results page — so a 2050 EAD under Current Policies will be higher than a 2025 EAD.
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

    # Asset header with coordinate reference
    header_parts = [
        f"**Asset:** {sel_asset_obj.name}",
        f"**Coordinates:** ({sel_asset_obj.lat:.4f}°, {sel_asset_obj.lon:.4f}°)",
        f"**Country:** {sel_asset_obj.region.upper()}",
    ]
    st.markdown(" | ".join(header_parts))

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

                # Source provenance banner with spatial reference
                prov_col, info_col = st.columns([5, 1])
                with prov_col:
                    if src_key == "fallback_baseline":
                        st.info(
                            f"**Source:** Built-in Regional Baseline | "
                            f"**Spatial ref:** {zone} zone (continental median) | "
                            f"**Resolution:** ~continental | "
                            f"**Basis:** {detail['hazard_source']}",
                            icon="⚠️",
                        )
                    elif src_key == "isimip3b":
                        grid_lat = round(round(sel_asset_obj.lat * 2) / 2, 1)
                        grid_lon = round(round(sel_asset_obj.lon * 2) / 2, 1)
                        st.success(
                            f"**Source:** {src_info.get('name', src_key)} | "
                            f"**Spatial ref:** Grid cell ({grid_lat}°, {grid_lon}°) containing asset coordinate | "
                            f"**Resolution:** {src_info.get('resolution', '—')}",
                            icon="✅",
                        )
                    else:
                        st.success(
                            f"**Source:** {src_info.get('name', src_key)} | "
                            f"**Spatial ref:** Nearest grid cell to ({sel_asset_obj.lat:.4f}°, {sel_asset_obj.lon:.4f}°) | "
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
                        if src_key == "fallback_baseline":
                            st.markdown(f"**Zone applied:** {zone} — {detail['zone_description']}")
                        else:
                            st.markdown(
                                f"**Grid cell:** Data extracted at the 0.5° grid cell containing "
                                f"({sel_asset_obj.lat:.4f}°, {sel_asset_obj.lon:.4f}°)"
                            )
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

                # Build spatial reference label for table
                if src_key == "fallback_baseline":
                    spatial_ref = f"{zone} zone"
                elif src_key == "isimip3b":
                    grid_lat = round(round(sel_asset_obj.lat * 2) / 2, 1)
                    grid_lon = round(round(sel_asset_obj.lon * 2) / 2, 1)
                    spatial_ref = f"({grid_lat}°, {grid_lon}°)"
                else:
                    spatial_ref = f"({sel_asset_obj.lat:.4f}°, {sel_asset_obj.lon:.4f}°)"

                int_df = pd.DataFrame({
                    "Return Period (yr)": [int(r) for r in rp_vals],
                    "Annual Exceedance Prob.": [f"1-in-{int(r)}-yr = {1/r*100:.2f}%/yr" for r in rp_vals],
                    f"Baseline Intensity ({unit})": [round(v, 3) for v in int_vals],
                    "Source": [DATA_SOURCE_REGISTRY.get(src_key, {}).get("name", src_key)] * len(rp_vals),
                    "Spatial Reference": [spatial_ref] * len(rp_vals),
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

                if src_key == "fallback_baseline":
                    st.caption(
                        f"**Granularity note:** The {zone} zone represents continental-scale median values. "
                        f"Actual site-level intensity may vary significantly. "
                        f"Use the override panel below to enter site-specific data, or set "
                        f"ISIMIP3b as the preferred source for 0.5° gridded extraction."
                    )
else:
    if not st.session_state.hazard_data:
        st.info("Fetch hazard data first to inspect intensity values.")
    else:
        st.info("Select an asset above to view its intensity profile.")

# ── Damage Function Explainer ─────────────────────────────────────────────
st.divider()
st.subheader("How Hazard Data Feeds Into Damage Calculations")
st.markdown("""
The numbers shown above are **baseline hazard intensities** — the physical severity of each
hazard at different return periods (exceedance frequencies). Here is exactly how they flow
into the damage and risk calculations on the Results page:
""")

with st.container(border=True):
    st.markdown("""
**Step 1 — Hazard Intensity (this page)**
Each asset gets a return-period curve: intensity values at RP10, RP50, RP100, RP250, RP500, RP1000.
These represent "a 1-in-10-year event produces X intensity" through "a 1-in-1000-year event produces Y intensity".

**Step 2 — Scenario Scaling (Scenarios page)**
Each intensity is multiplied by a **hazard multiplier** for the selected scenario and year.
For example, under SSP5-8.5 in 2050, flood intensities might be scaled by 1.3× relative to baseline.

**Step 3 — Vulnerability Curve (shown below)**
The scaled intensity is mapped through a **damage function** (vulnerability curve) to get a
**damage fraction** (0–100% of replacement value). Different asset types have different curves
— e.g. masonry buildings are more vulnerable to flooding than steel-framed buildings.

**Step 4 — Expected Annual Damage (EAD)**
The damage fractions across all return periods define an **exceedance probability (EP) curve**.
The area under this curve (trapezoidal integration of damage × annual exceedance probability)
gives the **Expected Annual Damage** — the average annual loss accounting for both frequent
low-severity events and rare catastrophic events.

> **EAD = ∫ Damage(AEP) dAEP** where AEP = 1 / Return Period
    """)

# Show worked example if data is available
if sel_asset_obj and st.session_state.hazard_data.get(sel_asset_detail):
    hdata_ex = st.session_state.hazard_data[sel_asset_detail]
    example_hazard = next((h for h in ["flood", "wind", "wildfire", "heat"] if h in hdata_ex), None)
    if example_hazard:
        with st.expander(f"📐 Worked example: {sel_asset_obj.name} — {example_hazard.capitalize()}"):
            hd_ex = hdata_ex[example_hazard]
            rp_ex = np.array(hd_ex["return_periods"], dtype=float)
            int_ex = np.array(hd_ex["intensities"], dtype=float)
            unit_ex = HAZARD_UNIT_LABELS.get(example_hazard, "")

            # Compute damage fractions
            dmg_fracs = np.array([
                get_damage_fraction(example_hazard, sel_asset_obj.asset_type, i)
                for i in int_ex
            ])
            aep = 1.0 / rp_ex
            losses = dmg_fracs * sel_asset_obj.replacement_value
            _trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz")
            order = np.argsort(aep)
            ead = float(_trapz(losses[order], aep[order]))

            ccy = st.session_state.get("currency_code", "GBP")
            worked_df = pd.DataFrame({
                "Return Period (yr)": [int(r) for r in rp_ex],
                "AEP (1/RP)": [f"{1/r:.4f}" for r in rp_ex],
                f"Intensity ({unit_ex})": [round(v, 3) for v in int_ex],
                "Damage Fraction": [f"{d*100:.2f}%" for d in dmg_fracs],
                f"Loss ({ccy})": [_fmt_cur(l, ccy) for l in losses],
            })
            st.dataframe(worked_df, use_container_width=True)
            st.metric(
                "Expected Annual Damage (EAD)",
                _fmt_cur(max(ead, 0), ccy),
                help="Trapezoidal integration of Loss × AEP across all return periods",
            )

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
