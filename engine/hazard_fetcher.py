"""
Hazard data fetcher — priority cascade:
  1. ISIMIP3b REST API v2  (https://www.isimip.org/)
  2. NASA NEX-GDDP-CMIP6  (https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6)
  3. CHELSA CMIP6          (https://chelsa-climate.org/)
  4. LOCA2                 (https://loca.ucsd.edu/loca2/)
  5. ClimateNA/AdaptWest   (https://adaptwest.databasin.org/)
  6. Built-in regional baseline (compiled; see data/ngfs_hazard_baseline.json)

Built-in fallback values are compiled from:
  • IPCC AR6 WG1 regional hazard assessments
    https://www.ipcc.ch/report/ar6/wg1/
  • ISIMIP3b global flood medians (Sauer et al. 2021)
    https://doi.org/10.1029/2020EF001901
  • HAZUS regional wind speed data (FEMA, 2022)
    https://www.fema.gov/flood-maps/products-tools/hazus
  • EFFIS fire danger climatology (JRC, 2021)
    https://effis.jrc.ec.europa.eu/
  • Copernicus C3S ERA5-Land temperature climatology
    https://cds.climate.copernicus.eu/
"""

import json
import logging
import os
from functools import lru_cache
from threading import Lock
import requests
import numpy as np
from typing import Dict, List, Optional, Tuple

from engine.data_sources import DATA_SOURCE_REGISTRY

logger = logging.getLogger(__name__)

BASE_URL = "https://api.isimip.org/v2"
REQUEST_TIMEOUT = 10
DEFAULT_FETCH_MODE = "balanced"
FETCH_MODE_MAX_GCMS = {
    "fast": 1,
    "balanced": 2,
    "full": 4,
}
_GRID_CELL_HAZARDS = {"flood", "heat", "wind", "wildfire"}
_FETCH_KEY_LOCKS: dict[tuple, Lock] = {}
_FETCH_KEY_LOCKS_GUARD = Lock()

_BASELINE: Optional[dict] = None


def _normalize_fetch_mode(fetch_mode: str) -> str:
    mode = str(fetch_mode or DEFAULT_FETCH_MODE).strip().lower()
    if mode not in FETCH_MODE_MAX_GCMS:
        return DEFAULT_FETCH_MODE
    return mode


def _grid_cell_coord(value: float) -> float:
    return round(round(float(value) * 2.0) / 2.0, 2)


def build_fetch_signature(
    lat: float,
    lon: float,
    region_iso3: str,
    hazards: list,
    terrain_elevation_asl_m: float = 0.0,
    asset_type: str = "default",
    fetch_mode: str = DEFAULT_FETCH_MODE,
) -> tuple:
    return (
        round(float(lat), 5),
        round(float(lon), 5),
        str(region_iso3).upper().strip(),
        tuple(dict.fromkeys(str(hazard) for hazard in hazards)),
        round(float(terrain_elevation_asl_m), 2),
        str(asset_type or "default"),
        _normalize_fetch_mode(fetch_mode),
    )


def _normalized_cache_args(
    lat: float,
    lon: float,
    hazard: str,
    region_iso3: str,
    terrain_elevation_asl_m: float,
    asset_type: str,
    fetch_mode: str,
) -> tuple:
    hazard_key = str(hazard or "").strip()
    if hazard_key in _GRID_CELL_HAZARDS:
        lat_key = _grid_cell_coord(lat)
        lon_key = _grid_cell_coord(lon)
        terrain_key = 0.0
        asset_key = "default"
    else:
        lat_key = round(float(lat), 5)
        lon_key = round(float(lon), 5)
        terrain_key = round(float(terrain_elevation_asl_m), 2)
        asset_key = str(asset_type or "default")
    return (
        lat_key,
        lon_key,
        hazard_key,
        str(region_iso3).upper().strip(),
        "baseline",
        "historical",
        terrain_key,
        asset_key,
        _normalize_fetch_mode(fetch_mode),
    )


def _get_cache_lock(cache_key: tuple) -> Lock:
    with _FETCH_KEY_LOCKS_GUARD:
        lock = _FETCH_KEY_LOCKS.get(cache_key)
        if lock is None:
            lock = Lock()
            _FETCH_KEY_LOCKS[cache_key] = lock
        return lock


def _load_baseline() -> dict:
    global _BASELINE
    if _BASELINE is None:
        path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "data", "ngfs_hazard_baseline.json")
        )
        with open(path) as f:
            _BASELINE = json.load(f)
    return _BASELINE


# Zone keys that are first-class identifiers (not ISO3 codes).
# If the input is already one of these, return it directly.
_VALID_ZONE_KEYS = {"EUR", "USA", "CHN", "IND", "AUS", "BRA", "MEA", "global"}


def _get_region_key(iso3: str) -> str:
    key = iso3.upper().strip()
    # If the input is already a valid zone key, return it directly.
    # This ensures zone overrides (e.g. "EUR", "MEA") work without
    # being mapped through ISO3 → zone lookup.
    if key in _VALID_ZONE_KEYS:
        return key
    bl = _load_baseline()
    mapping = bl.get("region_iso3_map", {})
    return mapping.get(key, "global")


def get_region_zone(region_iso3: str) -> str:
    """Return the zone key used by the baseline for this ISO3 country code.

    Accepts either an ISO3 country code (e.g. "GBR" → "EUR") or a zone key
    directly (e.g. "EUR" → "EUR", "MEA" → "MEA").
    """
    return _get_region_key(region_iso3)


def get_fallback_detail(hazard: str, region_iso3: str) -> dict:
    """
    Return full provenance detail for the fallback baseline at a given region.
    Used by the Hazards page to display transparent source information.
    """
    bl = _load_baseline()
    zone = _get_region_key(region_iso3)
    rps = bl.get("return_periods", [10, 50, 100, 250, 500, 1000])
    hazard_data = bl.get(hazard, {})
    values = {}
    for rp in rps:
        key = f"rp{rp}"
        entry = hazard_data.get(key, {})
        val = entry.get(zone, entry.get("global", 0.0))
        values[rp] = float(val)

    HAZARD_SOURCES = {
        "coastal_flood": {
            "source": "IPCC AR6 WG1 Ch.9 SLR + Vousdoukas et al. (2018) storm surge",
            "citation": "Fox-Kemper et al. (2021) AR6 WG1 Ch.9; Vousdoukas et al. (2018) Nature Commun. 9, 2360; Muis et al. (2020) Nature Commun. 11, 3806",
            "doi": "https://doi.org/10.1038/s41467-018-04692-w",
            "description": "Storm surge depth (m above MHWS) at return periods, derived from GTSM global tide/surge reanalysis (Muis et al. 2020) regional medians. Distance-to-coast attenuation applied. SLR amplification via IPCC AR6 scenario multipliers.",
        },
        "flood": {
            "source": "ISIMIP3b global flood medians",
            "citation": "Sauer et al. (2021) Earth's Future 9(2)",
            "doi": "https://doi.org/10.1029/2020EF001901",
            "description": "Regional median indicative flood depth (m) at each return period, compiled from ISIMIP3b global hydrological model ensemble. Screening-level proxy — NOT site-level hydraulic modelling.",
        },
        "wind": {
            "source": "FEMA HAZUS regional wind speed data",
            "citation": "FEMA (2022) HAZUS 6.0 Technical Manual",
            "doi": "https://www.fema.gov/flood-maps/products-tools/hazus",
            "description": "3-second gust wind speed (m/s) at return periods, derived from HAZUS MH regional wind climatology and ASCE 7 wind speed maps, adapted to global zones.",
        },
        "wildfire": {
            "source": "EFFIS fire danger climatology (regional baseline fallback)",
            "citation": "JRC (2021) EFFIS Annual Report; San-Miguel-Ayanz et al.; Van Wagner (1987) [FWI]",
            "doi": "https://effis.jrc.ec.europa.eu/",
            "description": (
                "Regional baseline: flame length (m) proxied from EFFIS fire weather index (FWI) "
                "percentiles, converted to flame length using Byram (1959) fireline intensity relationships. "
                "When ISIMIP3b data is available, the full Canadian FWI system (Van Wagner 1987) is used "
                "instead: daily tasmax + pr + hurs + sfcWind → FFMC/DMC/DC/ISI/BUI/FWI sequential algorithm "
                "→ GEV-fitted annual maxima → Simard (1970) + Byram (1959) flame length. "
                "This is the same FWI algorithm used by EFFIS, GWIS, and the Canadian CWFIS."
            ),
        },
        "heat": {
            "source": "ERA5-Land temperature percentiles",
            "citation": "Copernicus C3S ERA5-Land (2023); Muñoz-Sabater et al. (2021) ESSD",
            "doi": "https://cds.climate.copernicus.eu/",
            "description": "Maximum daily temperature (°C) at return periods from ERA5-Land reanalysis 1981–2010 climatology. ERA5-Land is a reanalysis at 9 km resolution; regional medians compiled per zone.",
        },
    }
    src = HAZARD_SOURCES.get(hazard, {})

    ZONE_DESCRIPTIONS = {
        "EUR": "Europe (GBR, FRA, DEU, ITA, ESP, NLD, BEL, POL, SWE, NOR and other EU/EEA)",
        "USA": "North America (USA, CAN, MEX)",
        "CHN": "East Asia (CHN, JPN, KOR, TWN)",
        "IND": "South Asia (IND, PAK, BGD, LKA)",
        "AUS": "Oceania (AUS, NZL)",
        "BRA": "South America (BRA, ARG, COL, PER)",
        "global": "Global median (fallback for unmapped countries)",
    }

    return {
        "zone": zone,
        "zone_description": ZONE_DESCRIPTIONS.get(zone, zone),
        "iso3": region_iso3.upper(),
        "return_periods": rps,
        "values": values,
        "hazard_source": src.get("source", ""),
        "citation": src.get("citation", ""),
        "doi": src.get("doi", ""),
        "description": src.get("description", ""),
        "resolution": "Regional (7 global zones; ~continental scale)",
        "temporal_basis": "1981–2010 historical climatology (pre-industrial to present)",
        "climate_adjustment": "Hazard multipliers applied per scenario/year via IPCC AR6 scaling (see Scenarios page)",
    }


def _fallback_intensities(hazard: str, region_iso3: str) -> Tuple[np.ndarray, np.ndarray]:
    """
    Return (return_periods, intensities) from built-in regional baseline.

    Sources per hazard:
      flood   → ISIMIP3b medians; Sauer et al. (2021) https://doi.org/10.1029/2020EF001901
      wind    → HAZUS regional data; FEMA (2022) https://www.fema.gov/flood-maps/products-tools/hazus
      wildfire → EFFIS fire danger climatology; JRC (2021) https://effis.jrc.ec.europa.eu/
      heat    → ERA5-Land temperature percentiles; Copernicus C3S https://cds.climate.copernicus.eu/
    """
    bl = _load_baseline()
    hazard_data = bl.get(hazard, {})
    rps_list = bl.get("return_periods", [10, 50, 100, 250, 500, 1000])
    region_key = _get_region_key(region_iso3)

    intensities = []
    for rp in rps_list:
        key = f"rp{rp}"
        entry = hazard_data.get(key, {})
        val = entry.get(region_key, entry.get("global", 0.0))
        intensities.append(float(val))

    return np.array(rps_list, dtype=float), np.array(intensities, dtype=float)


def _fetch_hazard_intensities_impl(
    lat: float,
    lon: float,
    hazard: str,
    region_iso3: str,
    scenario_ssp: str = "SSP2-4.5",
    time_period: str = "2021_2040",
    terrain_elevation_asl_m: float = 0.0,
    asset_type: str = "default",
    fetch_mode: str = DEFAULT_FETCH_MODE,
) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Fetch hazard return-period intensity profile for a location.

    Priority cascade (highest resolution first):
      1. ISIMIP3b — point extraction via isimip-client (flood, heat, wind) [0.25–0.5°]
      2. NASA NEX-GDDP-CMIP6 — S3 NetCDF point extraction (heat, wind) [0.25°]
      3. CHELSA CMIP6 — GeoTIFF point extraction (heat) [30 arc-sec]
      4. Regional baseline — compiled medians from IPCC AR6 / ISIMIP [continental]

    The returned intensities represent a SCENARIO-AGNOSTIC baseline (historical
    or present-day reference). Temporal evolution (2025–2050) is handled
    entirely by scenario multipliers in the damage engine. The scenario_ssp
    parameter is accepted for backward compatibility but is NOT used to
    condition the fetched data.

    Returns
    -------
    (return_periods, intensities, source_key)
    source_key maps to DATA_SOURCE_REGISTRY for full citation.
    """
    mode = _normalize_fetch_mode(fetch_mode)
    max_gcms = FETCH_MODE_MAX_GCMS[mode]
    # ── 0a. Coastal flood — storm surge + SLR (dedicated pipeline) ────────
    if hazard == "coastal_flood":
        try:
            from engine.coastal import is_coastal, get_coastal_flood_intensities
            if is_coastal(lat, lon):
                rp, intensities = get_coastal_flood_intensities(
                    lat, lon, region_iso3,
                    elevation_m=0.0,  # first_floor_height applied in damage_engine
                    terrain_elevation_asl_m=terrain_elevation_asl_m,
                )
                return rp, intensities, "coastal_slr_baseline"
        except Exception as e:
            logger.warning(f"Coastal flood fetch failed ({lat},{lon}): {e}")
        # Non-coastal or error: return zero intensities
        rps = np.array([10, 50, 100, 250, 500, 1000], dtype=float)
        return rps, np.zeros(len(rps)), "coastal_slr_baseline"

    # ── 0b. Water stress — WRI Aqueduct 4.0 (dedicated pipeline) ───────────
    if hazard == "water_stress":
        try:
            from engine.water_stress import fetch_water_stress_profile
            rp, damages, ws_source = fetch_water_stress_profile(
                lat, lon, region_iso3,
                asset_type=asset_type,
            )
            # Map source key to DATA_SOURCE_REGISTRY key
            src_key = "aqueduct" if ws_source == "aqueduct" else "fallback_baseline"
            return rp, damages, src_key
        except Exception as e:
            logger.warning(f"Water stress fetch failed ({lat},{lon}): {e}")
        # Minimal fallback for water stress if everything fails
        rps = np.array([10, 50, 100, 250, 500, 1000], dtype=float)
        return rps, np.zeros(len(rps)), "fallback_baseline"

    # ── 1. ISIMIP3b (full extraction pipeline) ─────────────────────────────
    # NOTE: ISIMIP fetchers always use the HISTORICAL experiment (scenario-agnostic).
    # The scenario_ssp parameter is NOT passed — all scenario differentiation
    # comes from IPCC AR6 multipliers applied in the damage engine.
    try:
        from engine.isimip_fetcher import (
            fetch_isimip3b_flood, fetch_isimip3b_heat,
            fetch_isimip3b_wind, fetch_isimip3b_wildfire,
        )
        if hazard == "flood":
            result = fetch_isimip3b_flood(lat, lon, max_gcms=max_gcms)
            if result is not None:
                return result[0], result[1], "isimip3b"
        elif hazard == "heat":
            result = fetch_isimip3b_heat(lat, lon, max_gcms=max_gcms)
            if result is not None:
                return result[0], result[1], "isimip3b"
        elif hazard == "wind":
            result = fetch_isimip3b_wind(lat, lon, max_gcms=max_gcms)
            if result is not None:
                rp_w, int_w = result[0], result[1]
                try:
                    from engine.tropical_cyclone import get_cyclone_wind_intensities
                    rp_w, int_w, _basin = get_cyclone_wind_intensities(lat, lon, rp_w, int_w)
                except Exception as e:
                    logger.debug(f"Cyclone amplification skipped: {e}")
                return rp_w, int_w, "isimip3b"
        elif hazard == "wildfire" and mode == "full":
            result = fetch_isimip3b_wildfire(lat, lon, max_gcms=max_gcms)
            if result is not None:
                return result[0], result[1], "isimip3b"
    except Exception as e:
        logger.warning(f"ISIMIP3b {hazard} fetch failed ({lat},{lon}): {e}")

    # ── 2. Built-in regional baseline (always available) ─────────────────────
    # NOTE: NASA NEX-GDDP, CHELSA, and ClimateNA are future-conditioned sources
    # (they require SSP + year parameters). Under the baseline-plus-multipliers
    # architecture, mixing future-conditioned data into the baseline path would
    # create a hybrid that double-counts scenario signal when engine multipliers
    # are applied. These sources are therefore DISABLED for the baseline path.
    # If they are re-enabled in future, they must be configured to fetch
    # historical/present-day reference data, not SSP projections.
    rp, intensities = _fallback_intensities(hazard, region_iso3)
    source = "fallback_baseline"

    # ── 4. Cyclone amplification for wind hazard ──────────────────────────
    if hazard == "wind":
        try:
            from engine.tropical_cyclone import get_cyclone_wind_intensities
            rp, intensities, basin = get_cyclone_wind_intensities(
                lat, lon, rp, intensities
            )
            if basin is not None:
                source = source  # keep original source, basin info in damage_engine
        except Exception:
            pass

    return rp, intensities, source


@lru_cache(maxsize=2048)
def _fetch_hazard_intensities_cached(
    lat: float,
    lon: float,
    hazard: str,
    region_iso3: str,
    scenario_ssp: str,
    time_period: str,
    terrain_elevation_asl_m: float,
    asset_type: str,
    fetch_mode: str,
) -> tuple:
    rp, intensities, source = _fetch_hazard_intensities_impl(
        lat,
        lon,
        hazard,
        region_iso3,
        scenario_ssp,
        time_period,
        terrain_elevation_asl_m,
        asset_type,
        fetch_mode,
    )
    return tuple(np.asarray(rp, dtype=float).tolist()), tuple(np.asarray(intensities, dtype=float).tolist()), source


def fetch_hazard_intensities(
    lat: float,
    lon: float,
    hazard: str,
    region_iso3: str,
    scenario_ssp: str = "SSP2-4.5",
    time_period: str = "2021_2040",
    terrain_elevation_asl_m: float = 0.0,
    asset_type: str = "default",
    fetch_mode: str = DEFAULT_FETCH_MODE,
) -> Tuple[np.ndarray, np.ndarray, str]:
    cache_key = _normalized_cache_args(
        lat,
        lon,
        hazard,
        region_iso3,
        terrain_elevation_asl_m,
        asset_type,
        fetch_mode,
    )
    with _get_cache_lock(cache_key):
        rp, intensities, source = _fetch_hazard_intensities_cached(*cache_key)
    return np.array(rp, dtype=float), np.array(intensities, dtype=float), source


def _build_hazard_entry(
    hazard: str,
    lat: float,
    lon: float,
    region_iso3: str,
    scenario_ssp: str,
    time_period: str,
    terrain_elevation_asl_m: float,
    asset_type: str,
    fetch_mode: str,
) -> tuple[str, dict]:
    rp, intensities, source = fetch_hazard_intensities(
        lat,
        lon,
        hazard,
        region_iso3,
        scenario_ssp,
        time_period,
        terrain_elevation_asl_m=terrain_elevation_asl_m,
        asset_type=asset_type,
        fetch_mode=fetch_mode,
    )
    src_info = DATA_SOURCE_REGISTRY.get(source, {})
    entry = {
        "return_periods": rp.tolist(),
        "intensities": intensities.tolist(),
        "source": source,
        "source_name": src_info.get("name", source),
        "citation": src_info.get("citation", ""),
        "source_url": src_info.get("url", ""),
    }
    if hazard == "wind":
        try:
            from engine.tropical_cyclone import get_cyclone_exposure_summary
            tc_info = get_cyclone_exposure_summary(lat, lon)
            if tc_info is not None:
                entry["cyclone_basin"] = tc_info
        except Exception:
            pass
    return hazard, entry


def fetch_all_hazards(
    lat: float,
    lon: float,
    region_iso3: str,
    hazards: list,
    scenario_ssp: str = "SSP2-4.5",
    time_period: str = "2021_2040",
    terrain_elevation_asl_m: float = 0.0,
    asset_type: str = "default",
    fetch_mode: str = DEFAULT_FETCH_MODE,
) -> Dict[str, dict]:
    """Fetch intensity profiles for multiple hazards. Returns {hazard: {return_periods, intensities, source, citation}}.

    All fetched data is scenario-agnostic (historical baseline). The scenario_ssp
    parameter is accepted for backward compatibility but does NOT condition the data.
    Logs a per-location provenance summary showing which source was used for each hazard.
    """
    ordered_hazards = list(dict.fromkeys(str(hazard) for hazard in hazards))
    if not ordered_hazards:
        return {}

    results = {}
    for hazard in ordered_hazards:
        _, entry = _build_hazard_entry(
            hazard,
            lat,
            lon,
            region_iso3,
            scenario_ssp,
            time_period,
            terrain_elevation_asl_m,
            asset_type,
            fetch_mode,
        )
        results[hazard] = entry

    source_summary = [f"{hazard}={results[hazard]['source']}" for hazard in ordered_hazards]

    # Log provenance summary per location
    logger.info(f"Hazard sources ({lat:.2f},{lon:.2f} {region_iso3}): {', '.join(source_summary)}")
    fallback_count = sum(1 for h, d in results.items() if d["source"] == "fallback_baseline")
    if fallback_count > 0:
        logger.warning(f"  {fallback_count}/{len(results)} hazards used fallback baseline")

    return results
