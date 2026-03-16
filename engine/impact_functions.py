"""
Vulnerability curve registry with monotonic cubic spline interpolation.
Sources: HAZUS 6.0, JRC Global DDFs, Syphard et al. 2012, IEA/IPCC, ILO.
"""

import json
import os
import numpy as np
from scipy.interpolate import PchipInterpolator
from typing import Optional

_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "vulnerability_curves"))


def _load(filename: str) -> dict:
    with open(os.path.join(_DATA_DIR, filename)) as f:
        return json.load(f)


# Alias map: new/extended asset types → existing curve keys in JSON files.
# Allows asset_types.json to grow without duplicating curve data.
_CURVE_ALIAS: dict[str, str] = {
    "residential_high_rise": "residential_concrete",
    "commercial_office":     "commercial_steel",
    "commercial_retail":     "commercial_steel",
    "commercial_warehouse":  "industrial_steel",
    "industrial_heavy":      "industrial_steel",
    "healthcare_hospital":   "commercial_concrete",
    "education_school":      "residential_masonry",
    "data_center":           "commercial_concrete",
    "hotel_resort":          "commercial_concrete",
    "mixed_use":             "commercial_concrete",
    "infrastructure_bridge": "infrastructure_road",
    "infrastructure_port":   "infrastructure_utility",
}


def _resolve_curve_key(asset_type: str) -> str:
    """Resolve an asset_type to its curve key, following alias chain."""
    return _CURVE_ALIAS.get(asset_type, asset_type)


_FLOOD_CURVES: Optional[dict] = None
_WIND_CURVES: Optional[dict] = None
_WILDFIRE_CURVES: Optional[dict] = None
_HEAT_CURVES: Optional[dict] = None
_COASTAL_FLOOD_CURVES: Optional[dict] = None


def _flood() -> dict:
    global _FLOOD_CURVES
    if _FLOOD_CURVES is None:
        _FLOOD_CURVES = _load("flood_curves.json")
    return _FLOOD_CURVES


def _wind() -> dict:
    global _WIND_CURVES
    if _WIND_CURVES is None:
        _WIND_CURVES = _load("wind_curves.json")
    return _WIND_CURVES


def _wildfire() -> dict:
    global _WILDFIRE_CURVES
    if _WILDFIRE_CURVES is None:
        _WILDFIRE_CURVES = _load("wildfire_curves.json")
    return _WILDFIRE_CURVES


def _heat() -> dict:
    global _HEAT_CURVES
    if _HEAT_CURVES is None:
        _HEAT_CURVES = _load("heat_curves.json")
    return _HEAT_CURVES


def _coastal_flood() -> dict:
    global _COASTAL_FLOOD_CURVES
    if _COASTAL_FLOOD_CURVES is None:
        _COASTAL_FLOOD_CURVES = _load("coastal_flood_curves.json")
    return _COASTAL_FLOOD_CURVES


def _interpolate(xs: list, ys: list, x_query: float) -> float:
    """Monotonic cubic spline interpolation, clamped to [0, 1]."""
    xs_arr = np.array(xs, dtype=float)
    ys_arr = np.array(ys, dtype=float)
    if x_query <= xs_arr[0]:
        return float(ys_arr[0])
    if x_query >= xs_arr[-1]:
        return float(ys_arr[-1])
    interp = PchipInterpolator(xs_arr, ys_arr)
    return float(np.clip(interp(x_query), 0.0, 1.0))


def get_damage_fraction(hazard: str, asset_type: str, intensity: float) -> float:
    """
    Return the damage fraction [0,1] for a given hazard, asset type, and intensity.

    Parameters
    ----------
    hazard     : 'flood' | 'wind' | 'wildfire' | 'heat' | 'cyclone'
    asset_type : asset type string matching catalog (e.g. 'residential_masonry')
    intensity  : hazard intensity in native units
                 flood → inundation depth (m)
                 wind / cyclone → 3-s gust (m/s)
                 wildfire → flame length (m)
                 heat → max temperature (°C)
    """
    key = _resolve_curve_key(asset_type)

    if hazard == "flood":
        curves = _flood()
        curve = curves.get(key, curves.get(asset_type, curves["_default"]))
        return _interpolate(curve["depth_m"], curve["damage_fraction"], intensity)

    elif hazard in ("wind", "cyclone"):
        curves = _wind()
        curve = curves.get(key, curves.get(asset_type, curves["_default"]))
        return _interpolate(curve["speed_ms"], curve["damage_fraction"], intensity)

    elif hazard == "wildfire":
        curves = _wildfire()
        curve = curves.get(key, curves.get(asset_type, curves["_default"]))
        return _interpolate(curve["flame_length_m"], curve["damage_fraction"], intensity)

    elif hazard == "heat":
        curves = _heat()
        cooling = curves["cooling_cost"]
        curve = cooling.get(key, cooling.get(asset_type, cooling["_default"]))
        return _interpolate(curve["temp_c"], curve["damage_fraction"], intensity)

    elif hazard == "coastal_flood":
        curves = _coastal_flood()
        curve = curves.get(key, curves.get(asset_type, curves["_default"]))
        return _interpolate(curve["depth_m"], curve["damage_fraction"], intensity)

    elif hazard == "water_stress":
        # Water stress pipeline (water_stress.py / hazard_fetcher.py) returns
        # pre-computed damage fractions as "intensities". Pass through directly,
        # clamped to [0, 1].
        return float(np.clip(intensity, 0.0, 1.0))

    return 0.0


def get_damage_curve(hazard: str, asset_type: str, n_points: int = 100) -> tuple:
    """Return (intensities, damage_fractions) arrays for plotting the vulnerability curve."""
    key = _resolve_curve_key(asset_type)
    if hazard == "flood":
        curves = _flood()
        curve = curves.get(key, curves.get(asset_type, curves["_default"]))
        x_min, x_max = 0.0, curve["depth_m"][-1]
    elif hazard in ("wind", "cyclone"):
        curves = _wind()
        curve = curves.get(key, curves.get(asset_type, curves["_default"]))
        x_min, x_max = 0.0, curve["speed_ms"][-1]
    elif hazard == "wildfire":
        curves = _wildfire()
        curve = curves.get(key, curves.get(asset_type, curves["_default"]))
        x_min, x_max = 0.0, curve["flame_length_m"][-1]
    elif hazard == "heat":
        curves = _heat()
        curve = curves["cooling_cost"].get(key, curves["cooling_cost"].get(asset_type, curves["cooling_cost"]["_default"]))
        x_min, x_max = curve["temp_c"][0], curve["temp_c"][-1]
    elif hazard == "coastal_flood":
        curves = _coastal_flood()
        curve = curves.get(key, curves.get(asset_type, curves["_default"]))
        x_min, x_max = 0.0, curve["depth_m"][-1]
    else:
        return np.array([]), np.array([])

    xs = np.linspace(x_min, x_max, n_points)
    ys = np.array([get_damage_fraction(hazard, asset_type, x) for x in xs])
    return xs, ys


def get_curve_control_points(hazard: str, asset_type: str) -> tuple:
    """Return alias-resolved control points used by the engine for a curve."""
    key = _resolve_curve_key(asset_type)
    if hazard == "flood":
        curves = _flood()
        curve = curves.get(key, curves.get(asset_type, curves["_default"]))
        return (
            np.array(curve["depth_m"], dtype=float),
            np.array(curve["damage_fraction"], dtype=float),
            "depth_m",
            key,
        )
    if hazard in ("wind", "cyclone"):
        curves = _wind()
        curve = curves.get(key, curves.get(asset_type, curves["_default"]))
        return (
            np.array(curve["speed_ms"], dtype=float),
            np.array(curve["damage_fraction"], dtype=float),
            "speed_ms",
            key,
        )
    if hazard == "wildfire":
        curves = _wildfire()
        curve = curves.get(key, curves.get(asset_type, curves["_default"]))
        return (
            np.array(curve["flame_length_m"], dtype=float),
            np.array(curve["damage_fraction"], dtype=float),
            "flame_length_m",
            key,
        )
    if hazard == "heat":
        curves = _heat()
        cooling = curves["cooling_cost"]
        curve = cooling.get(key, cooling.get(asset_type, cooling["_default"]))
        return (
            np.array(curve["temp_c"], dtype=float),
            np.array(curve["damage_fraction"], dtype=float),
            "temp_c",
            key,
        )
    if hazard == "coastal_flood":
        curves = _coastal_flood()
        curve = curves.get(key, curves.get(asset_type, curves["_default"]))
        return (
            np.array(curve["depth_m"], dtype=float),
            np.array(curve["damage_fraction"], dtype=float),
            "depth_m",
            key,
        )
    return np.array([]), np.array([]), "", key


HAZARD_UNITS = {
    "flood": "Inundation depth (m)",
    "wind": "3-s gust wind speed (m/s)",
    "cyclone": "3-s gust wind speed (m/s)",
    "wildfire": "Flame length (m)",
    "heat": "Max temperature (°C)",
    "coastal_flood": "Storm surge depth (m)",
    "water_stress": "Damage fraction (0–1)",
}
