"""
Page 3 – Hazard Data: source transparency, data provenance, intensity tables,
damage function explainer, manual overrides, and multi-source optionality.
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from engine.asset_model import Asset as _Asset, load_asset_types
from engine.fmt import fmt as _fmt_cur
from engine.hazard_fetcher import (
    DEFAULT_FETCH_MODE, build_fetch_signature, fetch_all_hazards, get_region_zone, get_fallback_detail, _load_baseline
)
from engine.data_sources import DATA_SOURCE_REGISTRY
from engine.impact_functions import get_damage_curve, get_damage_fraction, HAZARD_UNITS
from engine.governance import current_operator, utc_now_iso
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

FETCH_MODE_LABELS = {
    "fast": "Fast - screening speed",
    "balanced": "Balanced - 2-GCM baseline",
    "full": "Full - deepest fetch",
}
FETCH_MODE_NOTES = {
    "fast": "Fast uses one ISIMIP GCM for acute hazards and keeps wildfire on the fallback baseline. Best for larger screening portfolios.",
    "balanced": "Balanced uses two ISIMIP GCMs for acute hazards and keeps wildfire on the fallback baseline. Good default trade-off.",
    "full": "Full uses four ISIMIP GCMs and enables the full ISIMIP wildfire pipeline. It is the highest-fidelity baseline and is reused across pages once loaded.",
}
MAX_FETCH_WORKERS = max(1, min(8, os.cpu_count() or 4))

if "hazard_fetch_mode" not in st.session_state:
    st.session_state.hazard_fetch_mode = DEFAULT_FETCH_MODE
if "hazard_fetch_workers" not in st.session_state:
    st.session_state.hazard_fetch_workers = max(1, min(4, MAX_FETCH_WORKERS))
if "hazard_data_meta" not in st.session_state:
    st.session_state.hazard_data_meta = {}


def _hazards_for_asset(asset: _Asset) -> list[str]:
    hazards = list(asset_types_catalog.get(asset.asset_type, {}).get(
        "hazards", ["flood", "wind", "wildfire", "heat"]
    ))
    if "coastal_flood" not in hazards:
        try:
            from engine.coastal import is_coastal
            if is_coastal(asset.lat, asset.lon):
                hazards.append("coastal_flood")
        except Exception:
            pass
    return hazards


def _effective_region(asset: _Asset, overrides: dict) -> str:
    region = overrides.get(asset.id, asset.region)
    return asset.region if region == "AUTO" else region


def _fetch_asset_hazard_data(asset: _Asset, region: str, fetch_mode: str) -> tuple[str, str, dict]:
    kwargs = {
        "terrain_elevation_asl_m": getattr(asset, "terrain_elevation_asl_m", 0.0),
        "asset_type": asset.asset_type,
    }
    try:
        data = fetch_all_hazards(
            asset.lat,
            asset.lon,
            region,
            _hazards_for_asset(asset),
            fetch_mode=fetch_mode,
            **kwargs,
        )
    except TypeError as exc:
        if "fetch_mode" not in str(exc):
            raise
        data = fetch_all_hazards(
            asset.lat,
            asset.lon,
            region,
            _hazards_for_asset(asset),
            **kwargs,
        )
    return asset.id, asset.name, data


def _asset_fetch_signature(asset: _Asset, region: str, fetch_mode: str) -> tuple:
    return build_fetch_signature(
        asset.lat,
        asset.lon,
        region,
        _hazards_for_asset(asset),
        terrain_elevation_asl_m=getattr(asset, "terrain_elevation_asl_m", 0.0),
        asset_type=asset.asset_type,
        fetch_mode=fetch_mode,
    )

# ── Source Registry ────────────────────────────────────────────────────────
st.divider()
st.subheader("Available Data Sources")
st.caption(
    "Active baseline pathways in this release are ISIMIP3b historical extraction, "
    "WRI Aqueduct for water stress, the coastal flood baseline for coastal assets, "
    "IBTrACS tropical-cyclone wind amplification, and the built-in regional fallback. "
    "NASA NEX-GDDP, CHELSA, LOCA2, and ClimateNA remain catalogued for future extensions "
    "but are not used in the automatic baseline path."
)

SOURCE_STATUS = {
    "isimip3b": {
        "status": "active",
        "badge": "🟢 Active baseline source",
        "note": (
            "Point-extraction at asset coordinates (0.5° grid cell). "
            "Wildfire: multi-variable FWI pipeline (tasmax + pr + hurs + sfcWind → "
            "Canadian FWI system → GEV → flame length). ~90s per asset for wildfire."
        ),
    },
    "aqueduct": {
        "status": "active",
        "badge": "🟢 Active baseline source",
        "note": "Primary chronic water-stress pathway in this release via WRI Aqueduct 4.0.",
    },
    "nasa_nex_gddp_cmip6": {
        "status": "catalogued",
        "badge": "🟠 Catalogued only",
        "note": "Retained in the source registry, but inactive in the historical baseline path for this release.",
    },
    "chelsa_cmip6": {
        "status": "catalogued",
        "badge": "🟠 Catalogued only",
        "note": "Retained in the source registry, but inactive in the historical baseline path for this release.",
    },
    "loca2": {
        "status": "catalogued",
        "badge": "🟠 Catalogued only",
        "note": "Regional source retained for future extensions, not used automatically in this release.",
    },
    "climatena_adaptwest": {
        "status": "catalogued",
        "badge": "🟠 Catalogued only",
        "note": "Regional source retained for future extensions, not used automatically in this release.",
    },
    "coastal_slr_baseline": {
        "status": "active",
        "badge": "🟢 Active baseline source",
        "note": "Auto-enabled for assets within 10 km of coast; storm surge + IPCC AR6 SLR projections",
    },
    "ibtracs_cyclone": {
        "status": "active",
        "badge": "🟢 Active baseline modifier",
        "note": "Auto-enabled for assets within tropical cyclone basins; amplifies wind intensities at high return periods using Holland (1980) wind profile model",
    },
    "fallback_baseline": {
        "status": "active",
        "badge": "🟢 Active fallback source",
        "note": "Always available; 7 continental-scale zones; coarsest resolution",
    },
}

PRIORITY_ORDER = [
    "isimip3b", "aqueduct", "coastal_slr_baseline",
    "ibtracs_cyclone", "fallback_baseline", "nasa_nex_gddp_cmip6",
    "chelsa_cmip6", "loca2", "climatena_adaptwest",
]

HAZARD_UNIT_LABELS = {
    "flood": "Inundation depth (m)",
    "wind": "3-s gust wind speed (m/s)",
    "wildfire": "Flame length (m)",
    "heat": "Max daily temperature (°C)",
    "coastal_flood": "Storm surge depth (m)",
    "water_stress": "Damage fraction (chronic)",
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
    st.info(
        "This table compares the full source registry. In the automatic baseline flow for this release, "
        "ISIMIP3b, Aqueduct, the coastal baseline, and the built-in fallback are the active pathways.",
        icon="ℹ️",
    )
    st.markdown("""
### Data Source Comparison

| Source | Resolution | Coverage | Hazards | Temporal Range | Best For |
|--------|-----------|----------|---------|----------------|----------|
| **ISIMIP3b** | 0.5° (~55 km) | Global | Flood, Heat, Wind, Wildfire | Historical (1991–2014) | **Default choice** — scenario-agnostic baseline with GEV-fitted return periods from 4-GCM ensemble |
| **NASA NEX-GDDP-CMIP6** | 0.25° (~25 km) | Global | Heat, Wind, (Flood via precip) | 1950–2100 | Higher spatial resolution than ISIMIP; 35 CMIP6 models; good for heat/wind analysis |
| **CHELSA CMIP6** | 30 arc-sec (~1 km) | Global (land) | Heat, Precipitation | Climatologies (30-yr means) | **Highest resolution** for temperature-based hazards; ideal for topographically complex terrain |
| **LOCA2** | 1/16° (~6 km) | N. America | Heat, Flood | 1950–2100 | Best resolution for North American assets; daily data enables extreme event analysis |
| **ClimateNA / AdaptWest** | ~1 km | N. America | Heat | Bioclimatic periods | High-res North American temperature and bioclimatic variables |
| **Coastal Flood Baseline** | Regional + distance decay | Global (coastal) | Coastal Flood | IPCC AR6 SLR projections | Auto-enabled for assets ≤10 km from coast; storm surge + sea-level rise |
| **Built-in Regional Baseline** | Continental (~7 zones) | Global | All four | 1981–2010 climatology | Instant fallback; no API calls needed; very coarse |

### Key Trade-offs

**Resolution vs. Coverage:** CHELSA offers ~1 km resolution but only climatological means (no daily extremes for GEV fitting). ISIMIP3b has daily data enabling proper extreme-value statistics but at coarser 0.5° resolution.

**Gridded vs. Point:** ISIMIP3b and NASA NEX-GDDP extract the value from the grid cell containing your asset's coordinates. The grid cell centre may be up to ~25–28 km from the actual site. For assets near coastlines, elevation transitions, or urban heat islands, this can introduce bias.

**Regional Baseline (fallback):** Uses continental-zone medians — all assets in the same zone (e.g. all of Europe) receive identical hazard intensities. Only appropriate as a last resort or for portfolio-level screening.
    """)


# ── Source Settings ──────────────────────────────────────────────────────
st.divider()
st.subheader("Source Settings")

st.info(
    "**Data source selection is automatic in this release.** "
    "The system tries ISIMIP3b historical baseline extraction first for acute hazards; "
    "water stress uses WRI Aqueduct; coastal flood uses the coastal baseline path for coastal assets; "
    "and any remaining gaps fall back to the Built-in Regional Baseline. "
    "NASA NEX-GDDP, CHELSA, LOCA2, and ClimateNA are disabled in the automatic baseline path "
    "because they are future-conditioned sources that would conflict with the "
    "baseline-plus-multipliers architecture.",
    icon="ℹ️",
)

st.markdown("**Regional Zone Overrides** *(fallback baseline only — preview on this page)*")
st.caption(
    "Zone overrides affect **this page's preview** and the manual override reference values. "
    "The Results page always uses the asset's country code for zone mapping. "
    "Zones only apply when data falls back to the Built-in Regional Baseline."
)
zone_overrides = st.session_state.get("zone_overrides", {})
zones = ["AUTO", "EUR", "USA", "CHN", "IND", "AUS", "BRA", "MEA", "global"]
zone_desc = {
    "AUTO": "Auto-detect from country code",
    "EUR": "Europe (GBR, FRA, DEU, ITA, ESP...)",
    "USA": "North America (USA, CAN, MEX)",
    "CHN": "East Asia (CHN, JPN, KOR, TWN)",
    "IND": "South Asia (IND, PAK, BGD, LKA)",
    "AUS": "Oceania (AUS, NZL)",
    "BRA": "South America (BRA, ARG, COL, PER)",
    "MEA": "Middle East & Africa (SAU, ARE, QAT, ZAF...)",
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

worker_limit = max(1, min(MAX_FETCH_WORKERS, len(assets)))
st.session_state.hazard_fetch_workers = max(
    1,
    min(int(st.session_state.hazard_fetch_workers), worker_limit),
)

perf_col1, perf_col2 = st.columns([3, 2])
with perf_col1:
    fetch_mode = st.selectbox(
        "Performance profile",
        options=list(FETCH_MODE_LABELS.keys()),
        index=list(FETCH_MODE_LABELS.keys()).index(st.session_state.hazard_fetch_mode),
        format_func=lambda mode: FETCH_MODE_LABELS[mode],
        key="hazard_fetch_mode",
        help="Controls how much external hazard data is pulled before the fallback baseline is used.",
    )
with perf_col2:
    st.number_input(
        "Parallel asset workers",
        min_value=1,
        max_value=worker_limit,
        value=int(st.session_state.hazard_fetch_workers),
        step=1,
        key="hazard_fetch_workers",
        help="Fetch different assets concurrently. Keep this modest to avoid API contention.",
    )
st.caption(FETCH_MODE_NOTES[fetch_mode])
force_refresh = st.checkbox(
    "Force refresh cached assets",
    value=False,
    help="By default, unchanged assets reuse the cached baseline already loaded in this session.",
)

col_btn, col_info = st.columns([2, 5])
with col_btn:
    fetch_btn = st.button("🔄 Fetch / Refresh Changed Assets", type="primary", use_container_width=True)
with col_info:
    st.caption(
        f"Fetches baseline intensity profiles for all {len(assets)} asset(s) across "
        "Flood, Wind, Wildfire, Heat, Water Stress, and coastal hazards where relevant. "
        "The automatic baseline flow uses ISIMIP3b, Aqueduct, coastal baseline logic, "
        "and the built-in regional fallback."
    )

if fetch_btn:
    fetched_data = dict(st.session_state.get("hazard_data", {}))
    hazard_data_meta = dict(st.session_state.get("hazard_data_meta", {}))
    requested_signatures = {
        asset.id: _asset_fetch_signature(
            asset,
            _effective_region(asset, zone_overrides),
            st.session_state.hazard_fetch_mode,
        )
        for asset in assets
    }
    assets_to_fetch = [
        asset
        for asset in assets
        if force_refresh
        or hazard_data_meta.get(asset.id) != requested_signatures[asset.id]
        or asset.id not in fetched_data
    ]
    reused_assets = len(assets) - len(assets_to_fetch)
    failures = []
    max_workers = max(1, min(int(st.session_state.hazard_fetch_workers), max(1, len(assets_to_fetch))))

    if assets_to_fetch:
        progress = st.progress(0, text="Fetching hazard data...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    _fetch_asset_hazard_data,
                    asset,
                    _effective_region(asset, zone_overrides),
                    st.session_state.hazard_fetch_mode,
                ): asset
                for asset in assets_to_fetch
            }

            completed = 0
            for future in as_completed(futures):
                asset = futures[future]
                completed += 1
                try:
                    asset_id, asset_name, data = future.result()
                    fetched_data[asset_id] = data
                    hazard_data_meta[asset_id] = requested_signatures[asset_id]
                    label = f"[{completed}/{len(assets_to_fetch)}] {asset_name}"
                except Exception as exc:
                    failures.append(f"{asset.name}: {exc}")
                    label = f"[{completed}/{len(assets_to_fetch)}] {asset.name} failed"
                progress.progress(completed / len(assets_to_fetch), text=label)
        progress.empty()

    st.session_state.hazard_data = fetched_data
    st.session_state.hazard_data_meta = hazard_data_meta
    loaded_assets = len(assets) - len(failures)
    if False and failures:
        st.warning(
            "Some assets failed to refresh and kept their previous hazard data: "
            + "; ".join(failures[:5])
            + ("; ..." if len(failures) > 5 else ""),
            icon="âš ï¸",
        )
    if failures:
        st.warning(
            "Some assets failed to refresh and kept their previous hazard data: "
            + "; ".join(failures[:5])
            + ("; ..." if len(failures) > 5 else "")
        )
    invalid_assets = [
        asset.name
        for asset in assets
        if st.session_state.hazard_data_meta.get(asset.id) != requested_signatures[asset.id]
    ]
    if invalid_assets:
        st.warning(
            "The preview for some assets is still showing an older baseline because the requested "
            "refresh did not complete: "
            + "; ".join(invalid_assets[:5])
            + ("; ..." if len(invalid_assets) > 5 else "")
        )
    if reused_assets and assets_to_fetch:
        st.info(
            f"Reused cached baseline data for {reused_assets} unchanged asset(s) and refreshed "
            f"{len(assets_to_fetch)} asset(s)."
        )
    elif reused_assets and not assets_to_fetch:
        st.info(
            f"Reused cached baseline data for all {reused_assets} asset(s). "
            "No hazard refresh was needed."
        )
    st.success(
        f"Loaded scenario-agnostic baseline hazard data for {loaded_assets}/{len(assets)} asset(s) "
        f"using the {FETCH_MODE_LABELS[st.session_state.hazard_fetch_mode]} profile "
        f"with {max_workers} worker(s)."
    )
    st.caption(
        "Note: These are scenario-agnostic baseline intensities (historical reference). "
        "The Results page applies IPCC AR6 hazard multipliers per scenario/year "
        "to model temporal evolution from 2025â€“2050."
    )

if False and fetch_btn:
    progress = st.progress(0, text="Fetching hazard data...")
    # Fetch scenario-agnostic baseline hazard data for preview on this page.
    # The Results page fetches its own baseline independently; this is for inspection only.
    for i, asset in enumerate(assets):
        hazards = list(asset_types_catalog.get(asset.asset_type, {}).get(
            "hazards", ["flood", "wind", "wildfire", "heat"]
        ))
        # Dynamically add coastal_flood for assets near the coast
        if "coastal_flood" not in hazards:
            try:
                from engine.coastal import is_coastal
                if is_coastal(asset.lat, asset.lon):
                    hazards.append("coastal_flood")
            except Exception:
                pass
        # Apply zone override if set (only affects fallback baseline)
        region = zone_overrides.get(asset.id, asset.region)
        if region == "AUTO":
            region = asset.region
        data = fetch_all_hazards(
            asset.lat, asset.lon, region, hazards,
            terrain_elevation_asl_m=getattr(asset, "terrain_elevation_asl_m", 0.0),
            asset_type=asset.asset_type,
        )
        st.session_state.hazard_data[asset.id] = data
        progress.progress((i + 1) / len(assets), text=f"✅ {asset.name}")
    st.success(f"Loaded scenario-agnostic baseline hazard data for {len(assets)} asset(s).")
    st.caption(
        "Note: These are scenario-agnostic baseline intensities (historical reference). "
        "The Results page applies IPCC AR6 hazard multipliers per scenario/year "
        "to model temporal evolution from 2025–2050."
    )
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
        _HAZ_LABELS = {"flood": "Flood", "wind": "Wind", "wildfire": "Wildfire",
                       "heat": "Heat", "coastal_flood": "Coastal Flood",
                       "water_stress": "Water Stress"}
        for hazard in ["flood", "wind", "wildfire", "heat", "coastal_flood", "water_stress"]:
            col_name = _HAZ_LABELS[hazard]
            if hazard in hdata:
                src = hdata[hazard]["source"]
                if src == "fallback_baseline":
                    row[col_name] = f"Baseline ({zone} zone)"
                elif src == "isimip3b":
                    grid_lat = round(round(asset.lat * 2) / 2, 1)
                    grid_lon = round(round(asset.lon * 2) / 2, 1)
                    row[col_name] = f"ISIMIP3b ({grid_lat}°, {grid_lon}°)"
                elif src == "coastal_slr_baseline":
                    row[col_name] = "Coastal SLR Baseline"
                else:
                    src_name = DATA_SOURCE_REGISTRY.get(src, {}).get("name", src)
                    row[col_name] = src_name
            else:
                row[col_name] = "-- N/A"
        rows.append(row)

    status_df = pd.DataFrame(rows)
    st.dataframe(status_df, use_container_width=True)

    # Explain spatial reference
    with st.expander("📍 How spatial referencing works"):
        st.markdown("""
**Active gridded baseline source (ISIMIP3b):** Data is extracted from the grid cell
containing the asset's exact latitude/longitude coordinates. The table above shows the grid cell
centre coordinate for each hazard.

- **ISIMIP3b** uses a 0.5° grid (~55 km at the equator). The nearest grid cell centre is shown.
- **NASA NEX-GDDP / CHELSA / LOCA2 / ClimateNA** remain catalogued in the source registry for
  future extensions, but they are not used in the automatic historical-baseline flow for this release.

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
    st.info("Click **Fetch / Refresh Changed Assets** to load hazard data.")

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

    haz_tabs = [h for h in ["flood", "wind", "wildfire", "heat", "coastal_flood", "water_stress"] if h in hdata]
    if haz_tabs:
        _TAB_LABELS = {"flood": "🌊 Flood", "wind": "💨 Wind", "wildfire": "🔥 Wildfire",
                       "heat": "🌡️ Heat", "coastal_flood": "🌊 Coastal Flood / SLR",
                       "water_stress": "💧 Water Stress"}
        tabs = st.tabs([_TAB_LABELS.get(h, h) for h in haz_tabs])

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
                    elif src_key == "coastal_slr_baseline":
                        try:
                            from engine.coastal import distance_to_coast_km
                            dist = distance_to_coast_km(sel_asset_obj.lat, sel_asset_obj.lon)
                            dist_str = f"{dist:.0f} km from coast"
                        except Exception:
                            dist_str = "coastal zone"
                        st.success(
                            f"**Source:** Coastal Flood Baseline (Storm Surge + SLR) | "
                            f"**Spatial ref:** {dist_str} | "
                            f"**Resolution:** Regional + distance attenuation",
                            icon="✅",
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

                # Cyclone exposure info for wind hazard
                if hazard == "wind":
                    tc_info = hd.get("cyclone_basin")
                    if tc_info is None:
                        try:
                            from engine.tropical_cyclone import get_cyclone_exposure_summary
                            tc_info = get_cyclone_exposure_summary(sel_asset_obj.lat, sel_asset_obj.lon)
                        except Exception:
                            pass
                    if tc_info:
                        with st.container(border=True):
                            st.markdown(f"**Tropical Cyclone Exposure — {tc_info['full_name']}**")
                            tc_cols = st.columns(4)
                            with tc_cols[0]:
                                st.metric("Basin", tc_info["basin_code"])
                            with tc_cols[1]:
                                st.metric("Avg Storms/yr", tc_info["avg_annual_storms"])
                            with tc_cols[2]:
                                st.metric("Avg Hurricanes/yr", tc_info["avg_annual_hurricanes"])
                            with tc_cols[3]:
                                st.metric("Wind Amplification", f"{tc_info['amplification_factor']:.0%}")
                            st.caption(
                                f"**Season:** {tc_info['season']} (peak: {tc_info['peak']}). "
                                f"Wind intensities at RP100+ are amplified by "
                                f"{tc_info['amplification_factor']:.0%} to account for tropical cyclone "
                                f"contribution. Source: IBTrACS (Knapp et al. 2010); "
                                f"Knutson et al. (2020) BAMS."
                            )
                            # Show nearest historical tracks
                            nearest = tc_info.get("nearest_tracks", [])
                            if nearest:
                                st.markdown("**Nearest historical cyclone tracks:**")
                                for t in nearest[:3]:
                                    st.caption(
                                        f"  {t['name']} ({t['year']}) — {t['category']} "
                                        f"(max {t['max_wind_kt']} kt) — "
                                        f"{t['distance_km']:.0f} km from asset"
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
    example_hazard = next((h for h in ["flood", "wind", "wildfire", "heat", "coastal_flood"] if h in hdata_ex), None)
    if example_hazard:
        _haz_label = example_hazard.replace("_", " ").title()
        with st.expander(f"📐 Worked example: {sel_asset_obj.name} — {_haz_label}"):
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
            override_basis = st.selectbox(
                "Override basis",
                [
                    "Site survey / engineering assessment",
                    "Regulatory or public hazard map",
                    "Third-party model output",
                    "Internal sensitivity analysis",
                    "Other documented evidence",
                ],
                key="override_basis",
            )
            override_source_note = st.text_area(
                "Source / justification for override",
                placeholder="e.g. 'Environment Agency Flood Map RP100 depth = 0.8m at this postcode' "
                            "or 'Site survey 2024 — elevated 1.2m above local flood plain'",
                height=160,
                key="override_note",
            )
            override_user = st.text_input(
                "Prepared by",
                value=current_operator(),
                key="override_user",
            )
            st.caption("Timestamp is captured automatically in UTC and exported with the override.")

        if st.button("💾 Save Override", type="primary"):
            cleaned_intensities = pd.to_numeric(
                edited[f"Intensity ({unit})"], errors="coerce"
            ).tolist()
            if not override_source_note.strip():
                st.error("A source / justification is required for every manual override.")
            elif not override_user.strip():
                st.error("Prepared by is required for every manual override.")
            elif any(pd.isna(val) for val in cleaned_intensities):
                st.error("All override intensities must be numeric.")
            elif any(float(val) < 0 for val in cleaned_intensities):
                st.error("Override intensities cannot be negative.")
            else:
                if override_asset_id not in st.session_state.hazard_overrides:
                    st.session_state.hazard_overrides[override_asset_id] = {}
                st.session_state.hazard_overrides[override_asset_id][selected_hazard] = {
                    "return_periods": edited["Return Period (yr)"].tolist(),
                    "intensities": [float(val) for val in cleaned_intensities],
                    "source": "manual_override",
                    "source_note": override_source_note.strip(),
                    "override_basis": override_basis,
                    "override_user": override_user.strip(),
                    "override_timestamp_utc": utc_now_iso(),
                    "replaces_source": base_data.get("source", ""),
                }
                if override_asset_id not in st.session_state.hazard_data:
                    st.session_state.hazard_data[override_asset_id] = {}
                st.session_state.hazard_data[override_asset_id][selected_hazard] = (
                    st.session_state.hazard_overrides[override_asset_id][selected_hazard]
                )
                st.success(
                    f"Override saved for **{override_asset.name}** / **{selected_hazard}**. "
                    "This will be used in all subsequent damage calculations and exported with provenance."
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
                basis = od.get("override_basis", "")
                user = od.get("override_user", "")
                ts = od.get("override_timestamp_utc", "")
                st.markdown(
                    f"**{aname}** / {haz} — {basis} | prepared by `{user}` at `{ts}`\n\n"
                    + (f"*{note}*" if note else "*No source note*")
                )

# ── Vulnerability Curve Reference ──────────────────────────────────────────
st.divider()
st.subheader("Vulnerability Curve Reference")
st.caption("For full vulnerability curve auditing, editing, and source citations — see the **Vulnerability** page (Page 9).")

col1, col2 = st.columns(2)
with col1:
    curve_hazard = st.selectbox("Hazard", ["flood", "wind", "wildfire", "heat", "coastal_flood"],
                                format_func=lambda h: h.replace("_", " ").title(), key="curve_haz")
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
        "Syphard et al. (2012) | IEA Future of Cooling (2018) | ILO (2019) | "
        "Vousdoukas et al. (2018) [coastal flood]"
    )
