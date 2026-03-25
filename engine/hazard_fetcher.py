"""
Hazard data fetcher for the live screening baseline path.

Active baseline path:
  1. ISIMIP3b historical baseline for flood, heat, wind, and full-mode wildfire
  2. WRI Aqueduct 4.0 for water stress
  3. Coastal baseline screening pathway for coastal flood
  4. Built-in regional fallback when provider refresh fails
"""

import inspect
import json
import logging
import os
import hashlib
from functools import lru_cache
from threading import Lock
import requests
import numpy as np
from typing import Callable, Dict, List, Optional, Tuple

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
_DEFERRED_UNCERTAINTY_HAZARDS = {"flood", "heat", "wind", "wildfire"}
_UNCERTAINTY_STATUSES = {"deferred", "generated", "unavailable", "failed"}
_PREFERRED_SOURCES = {
    "flood": "isimip3b",
    "heat": "isimip3b",
    "wind": "isimip3b",
    "coastal_flood": "coastal_slr_baseline",
}
_FETCH_KEY_LOCKS: dict[tuple, Lock] = {}
_FETCH_KEY_LOCKS_GUARD = Lock()
_DISK_CACHE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", ".hazard_cache")
)
_DISK_CACHE_VERSION = 1

_BASELINE: Optional[dict] = None


def _normalize_fetch_mode(fetch_mode: str) -> str:
    mode = str(fetch_mode or DEFAULT_FETCH_MODE).strip().lower()
    if mode not in FETCH_MODE_MAX_GCMS:
        return DEFAULT_FETCH_MODE
    return mode


def _grid_cell_coord(value: float) -> float:
    return round(round(float(value) * 2.0) / 2.0, 2)


def preferred_source_for_hazard(hazard: str, fetch_mode: str = DEFAULT_FETCH_MODE) -> str | None:
    mode = _normalize_fetch_mode(fetch_mode)
    hazard_key = str(hazard or "").strip()
    if hazard_key == "wildfire":
        return "isimip3b" if mode == "full" else None
    return _PREFERRED_SOURCES.get(hazard_key)


def asset_requires_provider_refresh(
    hazard_data: Optional[dict],
    hazards: list,
    fetch_mode: str = DEFAULT_FETCH_MODE,
) -> bool:
    """Return True when cached data should be refreshed for the requested source path.

    This prevents a transient degraded cache (for example, fallback_baseline from an
    earlier provider failure) from being reused indefinitely after the upstream issue
    has been fixed.
    """
    if not isinstance(hazard_data, dict):
        return True

    ordered_hazards = list(dict.fromkeys(str(hazard) for hazard in hazards))
    for hazard in ordered_hazards:
        preferred_source = preferred_source_for_hazard(hazard, fetch_mode)
        if preferred_source is None:
            continue
        entry = hazard_data.get(hazard)
        if not isinstance(entry, dict):
            return True
        source = str(entry.get("source", "")).strip()
        if source == "manual_override":
            continue
        if source != preferred_source:
            return True
    return False


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


def _finalize_uncertainty_diagnostics(hazard: str, source: str, diagnostics: Optional[dict]) -> dict:
    final = dict(diagnostics or {})
    uncertainty = dict(final.get("uncertainty", {}) or {})
    explicit_status = str(final.get("uncertainty_status", "")).strip().lower()
    if (
        hazard not in _DEFERRED_UNCERTAINTY_HAZARDS
        and not uncertainty
        and explicit_status not in _UNCERTAINTY_STATUSES
    ):
        return final

    if uncertainty.get("type") == "gev_parameter_uncertainty":
        status = "generated"
    elif explicit_status in _UNCERTAINTY_STATUSES:
        status = explicit_status
    elif source == "isimip3b" and hazard in _DEFERRED_UNCERTAINTY_HAZARDS and final.get("gev_basis"):
        status = "deferred"
    else:
        status = "unavailable"

    final["uncertainty_status"] = status
    if status == "generated":
        final.setdefault(
            "uncertainty_detail",
            "Conditional GEV parameter bands have been generated for this asset-hazard pair.",
        )
    elif status == "deferred":
        final.setdefault(
            "uncertainty_detail",
            "Conditional GEV parameter bands are available on demand and were not generated in the standard run.",
        )
    elif status == "failed":
        final.setdefault(
            "uncertainty_detail",
            final.get("uncertainty_error")
            or "Conditional GEV parameter bands could not be generated from cached basis.",
        )
    else:
        final.setdefault(
            "uncertainty_detail",
            "Conditional GEV parameter bands are unavailable for this hazard-source path.",
        )
    return final


def uncertainty_status_for_entry(hazard: str, entry: Optional[dict]) -> str:
    if not isinstance(entry, dict):
        return "unavailable"
    diagnostics = _finalize_uncertainty_diagnostics(
        str(hazard or "").strip(),
        str(entry.get("source", "")).strip(),
        entry,
    )
    return str(diagnostics.get("uncertainty_status", "unavailable"))


def entry_supports_gev_bands(hazard: str, entry: Optional[dict]) -> bool:
    return uncertainty_status_for_entry(hazard, entry) in {"deferred", "generated", "failed"}


@lru_cache(maxsize=32)
def _fetch_callable_profile(fetch_callable: Callable) -> tuple[frozenset[str], bool]:
    """Return supported parameter names and whether the callable accepts **kwargs."""
    try:
        signature = inspect.signature(fetch_callable)
    except (TypeError, ValueError):
        return frozenset(), False

    supported = set()
    accepts_var_kwargs = False
    for name, parameter in signature.parameters.items():
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            accepts_var_kwargs = True
            continue
        supported.add(name)
    return frozenset(supported), accepts_var_kwargs


def call_fetch_all_hazards_compat(
    fetch_callable: Callable[..., Dict[str, dict]],
    lat: float,
    lon: float,
    region_iso3: str,
    hazards: list,
    **kwargs,
) -> Dict[str, dict]:
    """Call a hazard fetcher while filtering kwargs to the supported signature."""
    supported, accepts_var_kwargs = _fetch_callable_profile(fetch_callable)
    filtered_kwargs = kwargs if accepts_var_kwargs else {
        key: value for key, value in kwargs.items() if key in supported
    }
    return fetch_callable(lat, lon, region_iso3, hazards, **filtered_kwargs)


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


def _cache_file_path(cache_key: tuple) -> str:
    payload = json.dumps(list(cache_key), sort_keys=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return os.path.join(_DISK_CACHE_DIR, f"{digest}.json")


def _json_safe(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _load_fetch_from_disk(cache_key: tuple) -> tuple | None:
    path = _cache_file_path(cache_key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("version") != _DISK_CACHE_VERSION:
            return None
        return (
            tuple(float(v) for v in payload.get("return_periods", [])),
            tuple(float(v) for v in payload.get("intensities", [])),
            str(payload.get("source", "")),
            dict(payload.get("diagnostics", {}) or {}),
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _save_fetch_to_disk(
    cache_key: tuple,
    rp: tuple,
    intensities: tuple,
    source: str,
    diagnostics: dict,
) -> None:
    try:
        os.makedirs(_DISK_CACHE_DIR, exist_ok=True)
        path = _cache_file_path(cache_key)
        tmp_path = f"{path}.tmp"
        payload = {
            "version": _DISK_CACHE_VERSION,
            "return_periods": list(rp),
            "intensities": list(intensities),
            "source": source,
            "diagnostics": diagnostics or {},
        }
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, default=_json_safe)
        os.replace(tmp_path, path)
    except OSError:
        return


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


def _parse_fetch_result(result: tuple) -> Tuple[np.ndarray, np.ndarray, str, dict]:
    if len(result) == 4:
        rp, intensities, source, diagnostics = result
    elif len(result) == 3:
        rp, intensities, source = result
        diagnostics = {}
    else:
        raise ValueError(f"Unexpected fetch result length: {len(result)}")
    return (
        np.asarray(rp, dtype=float),
        np.asarray(intensities, dtype=float),
        str(source),
        dict(diagnostics or {}),
    )


def _hazard_entry_from_fetch(
    hazard: str,
    lat: float,
    lon: float,
    source: str,
    rp: np.ndarray,
    intensities: np.ndarray,
    diagnostics: Optional[dict],
) -> dict:
    diagnostics = _finalize_uncertainty_diagnostics(hazard, source, diagnostics)
    src_info = DATA_SOURCE_REGISTRY.get(source, {})
    entry = {
        "return_periods": np.asarray(rp, dtype=float).tolist(),
        "intensities": np.asarray(intensities, dtype=float).tolist(),
        "source": source,
        "source_name": src_info.get("name", source),
        "citation": src_info.get("citation", ""),
        "source_url": src_info.get("url", ""),
    }
    if diagnostics:
        entry.update(diagnostics)
    if hazard == "wind":
        try:
            from engine.tropical_cyclone import get_cyclone_exposure_summary
            tc_info = get_cyclone_exposure_summary(lat, lon)
            if tc_info is not None:
                entry["cyclone_basin"] = tc_info
        except Exception:
            pass
    return entry


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
) -> Tuple[np.ndarray, np.ndarray, str, dict]:
    """
    Fetch hazard return-period intensity profile for a location.

    Priority cascade (highest resolution first):
      1. ISIMIP3b — point extraction via isimip-client (flood, heat, wind, full-mode wildfire)
      2. WRI Aqueduct 4.0 — dedicated water stress pathway
      3. Coastal baseline — storm-surge screening pathway for coastal assets
      4. Regional baseline — compiled medians from IPCC AR6 / ISIMIP [continental]

    The returned intensities represent a SCENARIO-AGNOSTIC baseline (historical
    or present-day reference). Temporal evolution (2025–2050) is handled
    entirely by scenario multipliers in the damage engine. The scenario_ssp
    parameter is accepted for backward compatibility but is NOT used to
    condition the fetched data.

    Returns
    -------
    (return_periods, intensities, source_key, diagnostics)
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
                return rp, intensities, "coastal_slr_baseline", {}
        except Exception as e:
            logger.warning(f"Coastal flood fetch failed ({lat},{lon}): {e}")
        # Non-coastal or error: return zero intensities
        rps = np.array([10, 50, 100, 250, 500, 1000], dtype=float)
        return rps, np.zeros(len(rps)), "coastal_slr_baseline", {}

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
            return rp, damages, src_key, {}
        except Exception as e:
            logger.warning(f"Water stress fetch failed ({lat},{lon}): {e}")
        # Minimal fallback for water stress if everything fails
        rps = np.array([10, 50, 100, 250, 500, 1000], dtype=float)
        return rps, np.zeros(len(rps)), "fallback_baseline", {}

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
                rp, intensities, _, diagnostics = _parse_fetch_result(result)
                return rp, intensities, "isimip3b", diagnostics
        elif hazard == "heat":
            result = fetch_isimip3b_heat(lat, lon, max_gcms=max_gcms)
            if result is not None:
                rp, intensities, _, diagnostics = _parse_fetch_result(result)
                return rp, intensities, "isimip3b", diagnostics
        elif hazard == "wind":
            result = fetch_isimip3b_wind(lat, lon, max_gcms=max_gcms)
            if result is not None:
                rp_w, int_w, _, diagnostics = _parse_fetch_result(result)
                try:
                    from engine.tropical_cyclone import get_cyclone_wind_intensities
                    rp_w, int_w, _basin = get_cyclone_wind_intensities(lat, lon, rp_w, int_w)
                except Exception as e:
                    logger.debug(f"Cyclone amplification skipped: {e}")
                return rp_w, int_w, "isimip3b", diagnostics
        elif hazard == "wildfire" and mode == "full":
            result = fetch_isimip3b_wildfire(lat, lon, max_gcms=max_gcms)
            if result is not None:
                rp, intensities, _, diagnostics = _parse_fetch_result(result)
                return rp, intensities, "isimip3b", diagnostics
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

    return rp, intensities, source, {}


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
    disk_cached = _load_fetch_from_disk((
        lat,
        lon,
        hazard,
        region_iso3,
        scenario_ssp,
        time_period,
        terrain_elevation_asl_m,
        asset_type,
        fetch_mode,
    ))
    if disk_cached is not None:
        rp, intensities, source, diagnostics = disk_cached
        diagnostics = _finalize_uncertainty_diagnostics(hazard, source, diagnostics)
        return rp, intensities, source, diagnostics
    rp, intensities, source, diagnostics = _parse_fetch_result(
        _fetch_hazard_intensities_impl(
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
    )
    diagnostics = _finalize_uncertainty_diagnostics(hazard, source, diagnostics)
    result = (
        tuple(np.asarray(rp, dtype=float).tolist()),
        tuple(np.asarray(intensities, dtype=float).tolist()),
        source,
        diagnostics,
    )
    _save_fetch_to_disk((
        lat,
        lon,
        hazard,
        region_iso3,
        scenario_ssp,
        time_period,
        terrain_elevation_asl_m,
        asset_type,
        fetch_mode,
    ), *result)
    return result


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
    include_diagnostics: bool = False,
) -> Tuple[np.ndarray, np.ndarray, str] | Tuple[np.ndarray, np.ndarray, str, dict]:
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
        rp, intensities, source, diagnostics = _fetch_hazard_intensities_cached(*cache_key)
    rp_arr = np.array(rp, dtype=float)
    intens_arr = np.array(intensities, dtype=float)
    if include_diagnostics:
        return rp_arr, intens_arr, source, dict(diagnostics or {})
    return rp_arr, intens_arr, source


def generate_conditional_gev_bands(
    lat: float,
    lon: float,
    hazard: str,
    region_iso3: str,
    *,
    terrain_elevation_asl_m: float = 0.0,
    asset_type: str = "default",
    fetch_mode: str = DEFAULT_FETCH_MODE,
) -> dict:
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
        rp, intensities, source, diagnostics = _fetch_hazard_intensities_cached(*cache_key)
        diagnostics = _finalize_uncertainty_diagnostics(hazard, source, diagnostics)
        status = diagnostics.get("uncertainty_status", "unavailable")
        if status != "generated":
            if source == "isimip3b" and hazard in _DEFERRED_UNCERTAINTY_HAZARDS and diagnostics.get("gev_basis"):
                try:
                    from engine.isimip_fetcher import materialize_gev_uncertainty

                    uncertainty = materialize_gev_uncertainty(diagnostics.get("gev_basis"))
                    if uncertainty is not None:
                        diagnostics["uncertainty"] = uncertainty
                        diagnostics["uncertainty_status"] = "generated"
                        diagnostics["uncertainty_detail"] = (
                            "Conditional GEV parameter bands have been generated for this asset-hazard pair."
                        )
                        diagnostics.pop("uncertainty_error", None)
                    else:
                        diagnostics["uncertainty_status"] = "failed"
                        diagnostics["uncertainty_error"] = (
                            "Conditional GEV parameter bands could not be generated from cached basis."
                        )
                except Exception as exc:
                    diagnostics["uncertainty_status"] = "failed"
                    diagnostics["uncertainty_error"] = (
                        f"Conditional GEV parameter band generation failed: {exc}"
                    )
            else:
                diagnostics["uncertainty_status"] = "unavailable"
        diagnostics = _finalize_uncertainty_diagnostics(hazard, source, diagnostics)
        result = (
            tuple(np.asarray(rp, dtype=float).tolist()),
            tuple(np.asarray(intensities, dtype=float).tolist()),
            source,
            diagnostics,
        )
        _save_fetch_to_disk(cache_key, *result)
        _fetch_hazard_intensities_cached.cache_clear()

    return _hazard_entry_from_fetch(
        hazard,
        lat,
        lon,
        source,
        np.asarray(rp, dtype=float),
        np.asarray(intensities, dtype=float),
        diagnostics,
    )


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
    try:
        fetch_result = fetch_hazard_intensities(
            lat,
            lon,
            hazard,
            region_iso3,
            scenario_ssp,
            time_period,
            terrain_elevation_asl_m=terrain_elevation_asl_m,
            asset_type=asset_type,
            fetch_mode=fetch_mode,
            include_diagnostics=True,
        )
    except TypeError as exc:
        if "include_diagnostics" not in str(exc):
            raise
        fetch_result = fetch_hazard_intensities(
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

    rp, intensities, source, diagnostics = _parse_fetch_result(fetch_result)
    return hazard, _hazard_entry_from_fetch(
        hazard,
        lat,
        lon,
        source,
        rp,
        intensities,
        diagnostics,
    )


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
