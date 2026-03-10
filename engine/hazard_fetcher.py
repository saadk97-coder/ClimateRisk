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
import os
import requests
import numpy as np
from typing import Dict, Optional, Tuple

from engine.data_sources import fetch_best_available, DATA_SOURCE_REGISTRY

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


def _get_region_key(iso3: str) -> str:
    bl = _load_baseline()
    mapping = bl.get("region_iso3_map", {})
    return mapping.get(iso3.upper(), "global")


def get_region_zone(region_iso3: str) -> str:
    """Return the zone key used by the baseline for this ISO3 country code."""
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
    time_period: str = "2041_2060",
) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Fetch hazard return-period intensity profile for a location.

    Priority cascade (highest resolution first):
      1. ISIMIP3b — point extraction via isimip-client (flood, heat, wind) [0.25–0.5°]
      2. NASA NEX-GDDP-CMIP6 — S3 NetCDF point extraction (heat, wind) [0.25°]
      3. CHELSA CMIP6 — GeoTIFF point extraction (heat) [30 arc-sec]
      4. Regional baseline — compiled medians from IPCC AR6 / ISIMIP [continental]

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
                    elevation_m=0.0,  # elevation applied in damage_engine
                )
                return rp, intensities, "coastal_slr_baseline"
        except Exception:
            pass
        # Non-coastal or error: return zero intensities
        rps = np.array([10, 50, 100, 250, 500, 1000], dtype=float)
        return rps, np.zeros(len(rps)), "coastal_slr_baseline"

    # ── 0b. Water stress — WRI Aqueduct 4.0 (dedicated pipeline) ───────────
    if hazard == "water_stress":
        try:
            from engine.water_stress import fetch_water_stress_profile
            rp, damages, ws_source = fetch_water_stress_profile(
                lat, lon, region_iso3,
                ngfs_scenario=scenario_ssp,
            )
            # Map source key to DATA_SOURCE_REGISTRY key
            src_key = "aqueduct" if ws_source == "aqueduct" else "fallback_baseline"
            return rp, damages, src_key
        except Exception:
            pass
        # Minimal fallback for water stress if everything fails
        rps = np.array([10, 50, 100, 250, 500, 1000], dtype=float)
        return rps, np.zeros(len(rps)), "fallback_baseline"

    # ── 1. ISIMIP3b (full extraction pipeline) ─────────────────────────────
    try:
        from engine.isimip_fetcher import (
            fetch_isimip3b_flood, fetch_isimip3b_heat,
            fetch_isimip3b_wind, fetch_isimip3b_wildfire,
        )
        if hazard == "flood":
            result = fetch_isimip3b_flood(lat, lon, ssp=scenario_ssp)
            if result is not None:
                return result[0], result[1], "isimip3b"
        elif hazard == "heat":
            result = fetch_isimip3b_heat(lat, lon, ssp=scenario_ssp)
            if result is not None:
                return result[0], result[1], "isimip3b"
        elif hazard == "wind":
            result = fetch_isimip3b_wind(lat, lon, ssp=scenario_ssp)
            if result is not None:
                return result[0], result[1], "isimip3b"
        elif hazard == "wildfire":
            # Multi-variable FWI pipeline: tasmax + pr + hurs + sfcWind → FWI → flame length
            result = fetch_isimip3b_wildfire(lat, lon, ssp=scenario_ssp)
            if result is not None:
                return result[0], result[1], "isimip3b"
    except Exception:
        pass

    # ── 2. NASA NEX-GDDP-CMIP6 (heat, wind) ───────────────────────────────
    if hazard in ("heat", "wind"):
        try:
            from engine.data_sources import fetch_best_available
            src_key, val = fetch_best_available(lat, lon, hazard, region_iso3, scenario_ssp)
            if src_key not in ("fallback_baseline",) and val is not None:
                # Build simple intensities from single value (scaled across return periods)
                rp_base, base_intens = _fallback_intensities(hazard, region_iso3)
                # Scale baseline to match the API value at RP100 (index 2)
                rp100_idx = 2
                scale_factor = val / base_intens[rp100_idx] if base_intens[rp100_idx] > 0 else 1.0
                return rp_base, base_intens * scale_factor, src_key
        except Exception:
            pass

    # ── 3. Built-in regional baseline (always available) ───────────────────
    rp, intensities = _fallback_intensities(hazard, region_iso3)
    return rp, intensities, "fallback_baseline"


def fetch_all_hazards(
    lat: float,
    lon: float,
    region_iso3: str,
    hazards: list,
    scenario_ssp: str = "SSP2-4.5",
    time_period: str = "2041_2060",
) -> Dict[str, dict]:
    """Fetch intensity profiles for multiple hazards. Returns {hazard: {return_periods, intensities, source, citation}}."""
    results = {}
    for hazard in hazards:
        rp, intensities, source = fetch_hazard_intensities(
            lat, lon, hazard, region_iso3, scenario_ssp, time_period
        )
        src_info = DATA_SOURCE_REGISTRY.get(source, {})
        results[hazard] = {
            "return_periods": rp.tolist(),
            "intensities": intensities.tolist(),
            "source": source,
            "source_name": src_info.get("name", source),
            "citation": src_info.get("citation", ""),
            "source_url": src_info.get("url", ""),
        }
    return results
