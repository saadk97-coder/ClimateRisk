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
import requests
import numpy as np
from typing import Dict, List, Optional, Tuple

from engine.data_sources import fetch_best_available, DATA_SOURCE_REGISTRY

logger = logging.getLogger(__name__)

BASE_URL = "https://api.isimip.org/v2"
REQUEST_TIMEOUT = 10

_BASELINE: Optional[dict] = None


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
            "description": "Median inundation depth (m) at each return period, derived from ensemble of ISIMIP3b global hydrological models (CaMa-Flood, ORCHIDEE, PCR-GLOBWB). Calibrated to observed flood records.",
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


def fetch_hazard_intensities(
    lat: float,
    lon: float,
    hazard: str,
    region_iso3: str,
    scenario_ssp: str = "SSP2-4.5",
    time_period: str = "2021_2040",
    terrain_elevation_asl_m: float = 0.0,
    asset_type: str = "default",
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
            result = fetch_isimip3b_flood(lat, lon)
            if result is not None:
                return result[0], result[1], "isimip3b"
        elif hazard == "heat":
            result = fetch_isimip3b_heat(lat, lon)
            if result is not None:
                return result[0], result[1], "isimip3b"
        elif hazard == "wind":
            result = fetch_isimip3b_wind(lat, lon)
            if result is not None:
                rp_w, int_w = result[0], result[1]
                try:
                    from engine.tropical_cyclone import get_cyclone_wind_intensities
                    rp_w, int_w, _basin = get_cyclone_wind_intensities(lat, lon, rp_w, int_w)
                except Exception as e:
                    logger.debug(f"Cyclone amplification skipped: {e}")
                return rp_w, int_w, "isimip3b"
        elif hazard == "wildfire":
            result = fetch_isimip3b_wildfire(lat, lon)
            if result is not None:
                return result[0], result[1], "isimip3b"
    except Exception as e:
        logger.warning(f"ISIMIP3b {hazard} fetch failed ({lat},{lon}): {e}")

    # ── 2. NASA NEX-GDDP-CMIP6 (heat, wind) ───────────────────────────────
    if hazard in ("heat", "wind"):
        try:
            from engine.data_sources import fetch_best_available
            src_key, val = fetch_best_available(lat, lon, hazard, region_iso3, scenario_ssp)
            if src_key not in ("fallback_baseline",) and val is not None:
                rp_base, base_intens = _fallback_intensities(hazard, region_iso3)
                rp100_idx = 2
                scale_factor = val / base_intens[rp100_idx] if base_intens[rp100_idx] > 0 else 1.0
                rp_out, int_out = rp_base, base_intens * scale_factor
                if hazard == "wind":
                    try:
                        from engine.tropical_cyclone import get_cyclone_wind_intensities
                        rp_out, int_out, _basin = get_cyclone_wind_intensities(lat, lon, rp_out, int_out)
                    except Exception as e:
                        logger.debug(f"Cyclone amplification skipped: {e}")
                return rp_out, int_out, src_key
        except Exception as e:
            logger.warning(f"NEX-GDDP {hazard} fetch failed ({lat},{lon}): {e}")

    # ── 3. Built-in regional baseline (always available) ───────────────────
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


def fetch_all_hazards(
    lat: float,
    lon: float,
    region_iso3: str,
    hazards: list,
    scenario_ssp: str = "SSP2-4.5",
    time_period: str = "2021_2040",
    terrain_elevation_asl_m: float = 0.0,
    asset_type: str = "default",
) -> Dict[str, dict]:
    """Fetch intensity profiles for multiple hazards. Returns {hazard: {return_periods, intensities, source, citation}}.

    All fetched data is scenario-agnostic (historical baseline). The scenario_ssp
    parameter is accepted for backward compatibility but does NOT condition the data.
    Logs a per-location provenance summary showing which source was used for each hazard.
    """
    results = {}
    source_summary: List[str] = []
    for hazard in hazards:
        rp, intensities, source = fetch_hazard_intensities(
            lat, lon, hazard, region_iso3, scenario_ssp, time_period,
            terrain_elevation_asl_m=terrain_elevation_asl_m,
            asset_type=asset_type,
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
        # Attach cyclone basin info to wind hazard for UI display
        if hazard == "wind":
            try:
                from engine.tropical_cyclone import get_cyclone_exposure_summary
                tc_info = get_cyclone_exposure_summary(lat, lon)
                if tc_info is not None:
                    entry["cyclone_basin"] = tc_info
            except Exception:
                pass
        results[hazard] = entry
        source_summary.append(f"{hazard}={source}")

    # Log provenance summary per location
    logger.info(f"Hazard sources ({lat:.2f},{lon:.2f} {region_iso3}): {', '.join(source_summary)}")
    fallback_count = sum(1 for h, d in results.items() if d["source"] == "fallback_baseline")
    if fallback_count > 0:
        logger.warning(f"  {fallback_count}/{len(results)} hazards used fallback baseline")

    return results
