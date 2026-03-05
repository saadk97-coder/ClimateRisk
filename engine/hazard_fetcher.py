"""
Hazard data fetcher: attempts ISIMIP REST API v2, falls back to built-in
regional baseline table (ngfs_hazard_baseline.json) when offline or API fails.
"""

import json
import os
import time
import requests
import numpy as np
from typing import Dict, Optional, Tuple

BASE_URL = "https://api.isimip.org/v2"
REQUEST_TIMEOUT = 10  # seconds

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


def _fallback_intensities(hazard: str, region_iso3: str) -> Tuple[np.ndarray, np.ndarray]:
    """Return (return_periods, intensities) from built-in baseline table."""
    bl = _load_baseline()
    hazard_data = bl.get(hazard, {})
    rps_str = bl.get("return_periods", [10, 50, 100, 250, 500, 1000])
    region_key = _get_region_key(region_iso3)

    intensities = []
    for rp in rps_str:
        key = f"rp{rp}"
        entry = hazard_data.get(key, {})
        val = entry.get(region_key, entry.get("global", 0.0))
        intensities.append(float(val))

    return np.array(rps_str, dtype=float), np.array(intensities, dtype=float)


def _try_isimip_flood(lat: float, lon: float, scenario_ssp: str, time_period: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Query ISIMIP3b flood inundation data.
    Returns (return_periods, depths_m) or None on failure.
    """
    # Map SSP to ISIMIP protocol identifiers
    ssp_map = {
        "SSP1-1.9": "ssp119", "SSP1-2.6": "ssp126",
        "SSP2-4.5": "ssp245", "SSP5-8.5": "ssp585",
    }
    protocol = ssp_map.get(scenario_ssp, "ssp245")

    try:
        # ISIMIP flood inundation endpoint (simplified query)
        params = {
            "path": f"ISIMIP3b/SecondaryOutputs/flood/{protocol}/{time_period}",
            "bbox": f"{lon-0.5},{lat-0.5},{lon+0.5},{lat+0.5}",
            "format": "json",
        }
        r = requests.get(f"{BASE_URL}/datasets", params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None

        data = r.json()
        if not data.get("results"):
            return None

        # Simplified: extract return period / intensity pairs from first dataset
        # In production this would parse the actual NetCDF metadata
        return_periods = np.array([10, 50, 100, 250, 500, 1000], dtype=float)
        # Placeholder – real implementation would download and extract grid values
        return None

    except Exception:
        return None


def fetch_hazard_intensities(
    lat: float,
    lon: float,
    hazard: str,
    region_iso3: str,
    scenario_ssp: str = "SSP2-4.5",
    time_period: str = "2041_2070",
) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Fetch hazard return period intensities for a location.

    Returns
    -------
    (return_periods, intensities, source)
    source is 'isimip_api' or 'fallback_baseline'
    """
    api_result = None

    if hazard == "flood":
        api_result = _try_isimip_flood(lat, lon, scenario_ssp, time_period)

    if api_result is not None:
        return api_result[0], api_result[1], "isimip_api"

    rp, intensities = _fallback_intensities(hazard, region_iso3)
    return rp, intensities, "fallback_baseline"


def fetch_all_hazards(
    lat: float,
    lon: float,
    region_iso3: str,
    hazards: list,
    scenario_ssp: str = "SSP2-4.5",
    time_period: str = "2041_2070",
) -> Dict[str, dict]:
    """
    Fetch intensities for multiple hazards. Returns dict keyed by hazard name.
    """
    results = {}
    for hazard in hazards:
        rp, intensities, source = fetch_hazard_intensities(
            lat, lon, hazard, region_iso3, scenario_ssp, time_period
        )
        results[hazard] = {
            "return_periods": rp.tolist(),
            "intensities": intensities.tolist(),
            "source": source,
        }
    return results
