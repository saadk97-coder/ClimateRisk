"""
Climate data source registry with traceable citations.

Supports:
  • ISIMIP3b   — https://www.isimip.org/  (existing, already in hazard_fetcher.py)
  • NASA NEX-GDDP-CMIP6 — https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6
  • CHELSA CMIP6 — https://chelsa-climate.org/
  • LOCA2 — https://loca.ucsd.edu/loca2/  (CONUS focus)
  • ClimateNA / AdaptWest — https://adaptwest.databasin.org/
  • Built-in regional baseline — compiled from IPCC AR6 / ISIMIP medians

All fetchers fall back to the built-in regional baseline on failure.
"""

import json
import os
import requests
import numpy as np
from typing import Dict, Optional, Tuple

_TIMEOUT = 12  # seconds

# ---------------------------------------------------------------------------
# Source registry — all citations in one place
# ---------------------------------------------------------------------------
DATA_SOURCE_REGISTRY = {
    "isimip3b": {
        "name": "ISIMIP3b (Flood + Heat + Wind)",
        "description": (
            "Inter-Sectoral Impact Model Intercomparison Project Phase 3b. "
            "Flood: flooded area fraction (fldfrc) from CaMa-Flood multi-GHM ensemble at 0.25°, "
            "GEV-fitted to annual maxima to derive return period depths. "
            "Heat/Wind: bias-adjusted tasmax and sfcWind at 0.5° from CMIP6 GCMs (GFDL-ESM4, "
            "MPI-ESM1-2-HR, IPSL-CM6A-LR, MRI-ESM2-0), GEV-fitted annual maxima. "
            "Point extraction via isimip-client (async, ~60 s per asset)."
        ),
        "citation": (
            "Sauer et al. (2021) Earth's Future 9(2) [flood]; "
            "Lange (2019) Earth Syst. Dynam. 10, 1321–1336 [bias-adjustment]"
        ),
        "url": "https://www.isimip.org/",
        "doi": "https://doi.org/10.1029/2020EF001901",
        "resolution": "0.25–0.5° (~28–55 km)",
        "variables": ["fldfrc", "tasmax", "sfcWind"],
        "hazards": ["flood", "heat", "wind"],
    },
    "nasa_nex_gddp_cmip6": {
        "name": "NASA NEX-GDDP-CMIP6",
        "description": "Global Daily Downscaled Projections at 0.25° (~25 km) from 35 CMIP6 models, statistically downscaled via BCSD.",
        "citation": "Thrasher et al. (2022) Scientific Data 9, 262",
        "url": "https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6",
        "doi": "https://doi.org/10.1038/s41597-022-01393-4",
        "aws_bucket": "s3://nex-gddp-cmip6/NEX-GDDP-CMIP6/",
        "resolution": "0.25°",
        "variables": ["pr", "tasmax", "tasmin", "hurs", "sfcWind"],
        "hazards": ["flood", "heat", "wind"],
    },
    "chelsa_cmip6": {
        "name": "CHELSA CMIP6 Bioclimate",
        "description": "Climatologies at High resolution for the Earth's Land Surface Areas. High-resolution (30 arc-sec ≈ 1 km) bioclimatic variables from CMIP6.",
        "citation": "Karger et al. (2017) Scientific Data 4, 170122; Karger et al. (2023)",
        "url": "https://chelsa-climate.org/",
        "doi": "https://doi.org/10.1038/sdata.2017.122",
        "api_base": "https://os.zhdk.cloud.switch.ch/envicloud/chelsa/chelsa_V2/GLOBAL/",
        "resolution": "30 arc-sec (~1 km)",
        "variables": ["tas", "tasmax", "tasmin", "pr", "bio1", "bio12"],
        "hazards": ["heat", "flood"],
    },
    "loca2": {
        "name": "LOCA2 Statistical Downscaling",
        "description": "Localized Constructed Analogs v2. Downscaled CMIP6 daily data at 1/16° (~6 km) for North America (CONUS + Canada + Mexico).",
        "citation": "Pierce et al. (2023) Journal of Geophysical Research: Atmospheres",
        "url": "https://loca.ucsd.edu/loca2/",
        "doi": "https://doi.org/10.1029/2022JD038080",
        "data_url": "https://cirrus.ucsd.edu/~pierce/LOCA2/",
        "resolution": "1/16° (~6 km)",
        "variables": ["tasmax", "tasmin", "pr"],
        "hazards": ["heat", "flood"],
        "coverage": "North America",
    },
    "climatena_adaptwest": {
        "name": "ClimateNA / AdaptWest",
        "description": "High-resolution climate projections for North America based on CMIP6. Includes bioclimatic variables from AdaptWest portal.",
        "citation": "Wang et al. (2016) PLOS ONE 11(4)",
        "url": "https://adaptwest.databasin.org/",
        "doi": "https://doi.org/10.1371/journal.pone.0156720",
        "api_url": "https://climatena.ca/",
        "resolution": "~1 km",
        "variables": ["MAT", "MAP", "MWMT", "CMI", "DD5", "PAS"],
        "hazards": ["heat", "flood"],
        "coverage": "North America",
    },
    "fallback_baseline": {
        "name": "Built-in Regional Baseline",
        "description": "Compiled regional median hazard intensities from IPCC AR6 / ISIMIP medians. Used when all API sources are unavailable.",
        "citation": "Compiled from IPCC AR6 WG1 (2021); ISIMIP3b medians; HAZUS regional data",
        "url": "https://www.ipcc.ch/report/ar6/wg1/",
        "doi": "https://doi.org/10.1017/9781009157896",
        "resolution": "Regional (7 global zones)",
        "variables": ["flood_depth", "wind_speed", "flame_length", "max_temp"],
        "hazards": ["flood", "wind", "wildfire", "heat"],
    },
}


def get_source_info(source_key: str) -> dict:
    return DATA_SOURCE_REGISTRY.get(source_key, {})


# ---------------------------------------------------------------------------
# NASA NEX-GDDP-CMIP6 fetcher (public AWS S3 — no auth required)
# ---------------------------------------------------------------------------
_NASA_BASE = "https://nex-gddp-cmip6.s3.us-west-2.amazonaws.com"
_NASA_CATALOG = "https://nex-gddp-cmip6.s3.us-west-2.amazonaws.com/catalog.json"

_NASA_SSP_MAP = {
    "SSP1-1.9": "ssp119", "SSP1-2.6": "ssp126",
    "SSP2-4.5": "ssp245", "SSP3-7.0": "ssp370", "SSP5-8.5": "ssp585",
}


def fetch_nasa_nex(
    lat: float,
    lon: float,
    variable: str = "tasmax",
    ssp: str = "SSP2-4.5",
    year: int = 2050,
    model: str = "ACCESS-CM2",
) -> Optional[float]:
    """
    Fetch annual percentile statistics from NASA NEX-GDDP-CMIP6 via public AWS S3.

    Downloads a single year's NetCDF file (~100 MB) for the chosen model and
    extracts the nearest-grid-cell value to (lat, lon).

    Source: https://www.nccs.nasa.gov/services/data-collections/land-based-products/nex-gddp-cmip6
    Citation: Thrasher et al. (2022) Scientific Data 9, 262
    """
    try:
        import xarray as xr
        ssp_key = _NASA_SSP_MAP.get(ssp, "ssp245")
        # Public S3 path (no auth required)
        path = (
            f"https://nex-gddp-cmip6.s3.us-west-2.amazonaws.com/NEX-GDDP-CMIP6/"
            f"{model}/{ssp_key}/r1i1p1f1/{variable}/"
            f"{variable}_day_{model}_{ssp_key}_r1i1p1f1_gn_{year}.nc"
        )
        ds = xr.open_dataset(path, engine="scipy" if _has_scipy() else "netcdf4",
                             chunks=None)
        da = ds[variable]
        # Select nearest grid cell
        val = da.sel(lat=lat, lon=lon % 360, method="nearest")
        # Return annual maximum (for tasmax) or annual mean
        annual = float(val.max().values) if "max" in variable else float(val.mean().values)
        # Convert Kelvin → °C if needed
        if annual > 200:
            annual -= 273.15
        return annual
    except Exception:
        return None


def _has_scipy() -> bool:
    import importlib.util
    return importlib.util.find_spec("scipy") is not None


# ---------------------------------------------------------------------------
# CHELSA CMIP6 fetcher
# ---------------------------------------------------------------------------
_CHELSA_BASE = "https://os.zhdk.cloud.switch.ch/envicloud/chelsa/chelsa_V2/GLOBAL/climatologies"

_CHELSA_SSP_MAP = {
    "SSP1-2.6": "ssp126", "SSP2-4.5": "ssp370",
    "SSP5-8.5": "ssp585", "SSP1-1.9": "ssp126",
}


def fetch_chelsa_temp(
    lat: float,
    lon: float,
    ssp: str = "SSP2-4.5",
    period: str = "2041-2070",
    variable: str = "tas",
) -> Optional[float]:
    """
    Fetch mean temperature from CHELSA CMIP6 climatology GeoTIFF at 30 arc-sec (~1 km).

    Extracts point value from the CHELSA V2.1 climatology hosted on the Swiss
    Data Centre cloud (public access, no auth required).

    Source: https://chelsa-climate.org/
    Citation: Karger et al. (2017) Scientific Data 4, 170122
    """
    try:
        import rasterio
        from rasterio.crs import CRS
        ssp_key = _CHELSA_SSP_MAP.get(ssp, "ssp370")
        # CHELSA V2.1 CMIP6 climatology — example: GFDL-ESM4 tas 2041-2070 ssp370
        # URL pattern: {base}/{period}/GFDL-ESM4/{ssp}/{var}/{var}_GFDL-ESM4_{ssp}_{period}_V.2.1.tif
        model = "GFDL-ESM4"
        url = (
            f"{_CHELSA_BASE}/{period}/{model}/{ssp_key}/{variable}/"
            f"CHELSA_{variable}_{model}_{ssp_key}_{period}_V.2.1.tif"
        )
        with rasterio.open(url) as src:
            # Sample point value (rasterio uses (lon, lat) order)
            vals = list(src.sample([(lon, lat)]))
            if vals and len(vals[0]) > 0:
                raw = float(vals[0][0])
                # CHELSA tas values are scaled (×10, in °C×10) → divide by 10
                return raw / 10.0 if abs(raw) > 1000 else raw
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# LOCA2 fetcher (CONUS + Canada + Mexico)
# ---------------------------------------------------------------------------
_LOCA2_BASE = "https://cirrus.ucsd.edu/~pierce/LOCA2"


def fetch_loca2(
    lat: float,
    lon: float,
    variable: str = "tasmax",
    ssp: str = "ssp245",
    period: str = "2035-2064",
) -> Optional[float]:
    """
    Fetch a LOCA2 climate statistic for a point location.
    Returns value or None on failure.
    Source: https://loca.ucsd.edu/loca2/
    Coverage: North America only (lat 14–57°N, lon -140––53°E)
    """
    # LOCA2 data requires NetCDF extraction; return None for now
    if not (14 <= lat <= 57 and -140 <= lon <= -53):
        return None  # outside coverage
    return None


# ---------------------------------------------------------------------------
# ClimateNA / AdaptWest fetcher
# ---------------------------------------------------------------------------
def fetch_climatena(
    lat: float,
    lon: float,
    variable: str = "MAT",
    period: str = "2041-2060",
    scenario: str = "ssp245",
) -> Optional[float]:
    """
    Query ClimateNA web API for a point location.
    Returns value or None on failure.
    Source: https://adaptwest.databasin.org/
    Coverage: North America
    """
    try:
        if not (14 <= lat <= 83 and -170 <= lon <= -50):
            return None
        params = {
            "lat": lat, "lon": lon,
            "period": period, "scenario": scenario,
            "variable": variable,
        }
        r = requests.get(
            "https://climatena.ca/api/point",
            params=params, timeout=_TIMEOUT
        )
        if r.status_code == 200:
            return float(r.json().get("value", None))
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Priority-ordered fetch cascade
# ---------------------------------------------------------------------------
def fetch_best_available(
    lat: float,
    lon: float,
    hazard: str,
    region_iso3: str,
    ssp: str = "SSP2-4.5",
    year: int = 2050,
) -> Tuple[str, Optional[float]]:
    """
    Try data sources in priority order and return (source_key, value).
    Falls back to regional baseline if all fail.
    """
    # 1. LOCA2 (North America, best resolution)
    if hazard in ("heat", "flood") and fetch_loca2(lat, lon) is not None:
        val = fetch_loca2(lat, lon, ssp=ssp.lower().replace("-", ""))
        if val is not None:
            return "loca2", val

    # 2. NASA NEX-GDDP-CMIP6 (global)
    if hazard == "heat":
        val = fetch_nasa_nex(lat, lon, variable="tasmax", ssp=ssp, year=year)
        if val is not None:
            return "nasa_nex_gddp_cmip6", val

    # 3. CHELSA (global, high-res)
    if hazard == "heat":
        val = fetch_chelsa_temp(lat, lon, ssp=ssp)
        if val is not None:
            return "chelsa_cmip6", val

    # 4. ClimateNA (North America)
    if hazard == "heat" and fetch_climatena(lat, lon) is not None:
        val = fetch_climatena(lat, lon, scenario=ssp.lower().replace("-", ""))
        if val is not None:
            return "climatena_adaptwest", val

    return "fallback_baseline", None
