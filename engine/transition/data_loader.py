"""
Data loaders for the transition risk layer. All paths resolve relative to the
repo's data/transition/ directory. Loaders are cached at module level.
"""

from __future__ import annotations
import json
import logging
import os
from functools import lru_cache
from typing import Dict, List

_log = logging.getLogger(__name__)
_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "transition"))


def _load(name: str) -> dict:
    path = os.path.join(_DATA_DIR, name)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_carbon_prices() -> dict:
    return _load("carbon_prices_ngfs.json")


@lru_cache(maxsize=1)
def load_sector_pass_through() -> dict:
    return _load("sector_pass_through.json")


@lru_cache(maxsize=1)
def load_learning_curves() -> dict:
    return _load("learning_curves.json")


@lru_cache(maxsize=1)
def load_sector_pathways() -> dict:
    return _load("sector_pathways.json")


@lru_cache(maxsize=1)
def load_cc_exposure() -> dict:
    return _load("cc_exposure_proxy.json")


@lru_cache(maxsize=1)
def load_io_matrix() -> dict:
    return _load("io_matrix.json")


@lru_cache(maxsize=1)
def load_sector_taxonomy() -> dict:
    return _load("sector_taxonomy.json")


@lru_cache(maxsize=1)
def load_lever_library() -> dict:
    return _load("lever_library.json")


@lru_cache(maxsize=1)
def load_jurisdiction_carbon() -> dict:
    return _load("jurisdiction_carbon.json")


@lru_cache(maxsize=1)
def load_adaptive_capacity() -> dict:
    return _load("adaptive_capacity.json")


@lru_cache(maxsize=1)
def load_region_factors() -> dict:
    return _load("region_factors.json")


def get_ngfs_region(iso3: str) -> str:
    """Map ISO3 country code to NGFS region (advanced / emerging / rest_of_world)."""
    if not iso3:
        return "rest_of_world"
    iso3 = country_iso3(iso3)   # strip any sub-national suffix (e.g. USA-TX → USA)
    classification = load_carbon_prices().get("region_classification", {})
    if iso3 in classification.get("advanced", []):
        return "advanced"
    if iso3 in classification.get("emerging", []):
        return "emerging"
    return "rest_of_world"


def country_iso3(code: str) -> str:
    """Country ISO3 from a possibly sub-national region code (USA-TX → USA)."""
    if not code:
        return ""
    return code.strip().upper().split("-")[0]


def resource_zone(code: str) -> str:
    """Resolve a region code to a resource zone (region_factors.json). Precedence:
    exact sub-national code (USA-TX) → country ISO3 (USA) → global default."""
    rf = load_region_factors()
    c = (code or "").strip().upper()
    sub = rf.get("subnational_to_zone", {})
    if c in sub:
        return sub[c]
    return rf.get("iso3_to_zone", {}).get(country_iso3(c), rf["_meta"]["default_zone"])


def map_scenario_to_ngfs(scenario_id: str) -> str:
    """
    Map any scenario ID to one with carbon-price data. NGFS / IEA scenarios pass
    through unchanged; IPCC SSPs fall back to the closest NGFS analog.
    """
    scenarios = load_carbon_prices().get("scenarios", {})
    if scenario_id in scenarios:
        return scenario_id
    fallback = load_carbon_prices().get("ipcc_fallback_map", {})
    if scenario_id in fallback:
        _log.warning("Scenario '%s' has no NGFS carbon-price data; using analog '%s'.",
                     scenario_id, fallback[scenario_id])
        return fallback[scenario_id]
    _log.warning("Unknown scenario '%s' (no NGFS data, no fallback map entry); "
                 "defaulting to 'current_policies' — results are a DEGRADED proxy.", scenario_id)
    return "current_policies"


def list_sectors() -> List[str]:
    return list(load_sector_taxonomy()["sectors"].keys())


def get_sector_meta(sector: str) -> dict:
    """Return sector taxonomy entry; falls back to 'services' if unmatched."""
    sectors = load_sector_taxonomy()["sectors"]
    return sectors.get(sector, sectors["services"])
