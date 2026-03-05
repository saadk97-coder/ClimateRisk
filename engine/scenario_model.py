"""
NGFS Phase 4 scenarios mapped to SSP/RCP equivalents with hazard intensity
scaling factors derived from IPCC AR6 findings.
"""

from dataclasses import dataclass, field
from typing import Dict, List
import json
import os

# ---------------------------------------------------------------------------
# NGFS scenario definitions
# ---------------------------------------------------------------------------

SCENARIOS = {
    "net_zero_2050": {
        "label": "Net Zero 2050",
        "ssp": "SSP1-1.9",
        "description": "Immediate, coordinated global action limits warming to 1.5°C.",
        "warming": {2030: 1.3, 2040: 1.4, 2050: 1.5, 2080: 1.5},
        "color": "#1a9641",
    },
    "below_2c": {
        "label": "Below 2°C",
        "ssp": "SSP1-2.6",
        "description": "Strong policies keep warming below 2°C with high confidence.",
        "warming": {2030: 1.4, 2040: 1.55, 2050: 1.7, 2080: 1.8},
        "color": "#a6d96a",
    },
    "delayed_transition": {
        "label": "Delayed Transition",
        "ssp": "SSP2-4.5",
        "description": "Late-acting policies avoid worst outcomes but with higher transition risk.",
        "warming": {2030: 1.7, 2040: 1.85, 2050: 2.0, 2080: 2.4},
        "color": "#ffffbf",
    },
    "ndcs_only": {
        "label": "NDCs Only",
        "ssp": "SSP2-4.5",
        "description": "Countries implement current pledges; moderate overshoot.",
        "warming": {2030: 1.8, 2040: 2.1, 2050: 2.5, 2080: 3.0},
        "color": "#fdae61",
    },
    "current_policies": {
        "label": "Current Policies",
        "ssp": "SSP5-8.5",
        "description": "No new climate policies; business-as-usual emissions trajectory.",
        "warming": {2030: 1.9, 2040: 2.4, 2050: 3.0, 2080: 4.3},
        "color": "#d7191c",
    },
}

# ---------------------------------------------------------------------------
# Hazard intensity scaling factors per ΔT
# Based on IPCC AR6 WG1 Ch.11–12 and WG2 Ch.4
# Values are multipliers on baseline (1990–2020) hazard intensity
# ---------------------------------------------------------------------------

# Scaling function: linear interpolation between benchmark temperatures
HAZARD_SCALING = {
    "flood": {
        # Percent increase in 100yr flood return level per °C warming
        # AR6: ~5–7% per degree in many regions
        1.5: 1.10,
        2.0: 1.18,
        3.0: 1.35,
        4.3: 1.60,
    },
    "wind": {
        # Tropical cyclone intensity increases ~5% per 2°C; extratropical modest
        1.5: 1.04,
        2.0: 1.07,
        3.0: 1.13,
        4.3: 1.22,
    },
    "wildfire": {
        # Fire weather days / FWI: steep non-linear increase
        1.5: 1.20,
        2.0: 1.45,
        3.0: 1.90,
        4.3: 2.60,
    },
    "heat": {
        # Cooling degree days / heat stress: super-linear
        1.5: 1.30,
        2.0: 1.65,
        3.0: 2.40,
        4.3: 3.80,
    },
    "cyclone": {
        1.5: 1.06,
        2.0: 1.10,
        3.0: 1.20,
        4.3: 1.35,
    },
}

_BENCHMARK_TEMPS = sorted(list(next(iter(HAZARD_SCALING.values())).keys()))


def get_hazard_multiplier(hazard: str, warming_delta_c: float) -> float:
    """Linearly interpolate hazard intensity multiplier for a given warming level."""
    factors = HAZARD_SCALING.get(hazard, {})
    if not factors:
        return 1.0
    temps = sorted(factors.keys())
    if warming_delta_c <= temps[0]:
        return factors[temps[0]]
    if warming_delta_c >= temps[-1]:
        return factors[temps[-1]]
    for i in range(len(temps) - 1):
        t_lo, t_hi = temps[i], temps[i + 1]
        if t_lo <= warming_delta_c <= t_hi:
            frac = (warming_delta_c - t_lo) / (t_hi - t_lo)
            return factors[t_lo] + frac * (factors[t_hi] - factors[t_lo])
    return 1.0


def get_scenario_multipliers(scenario_id: str, year: int, hazard: str) -> float:
    """Return hazard intensity multiplier for a given scenario, year, and hazard."""
    scenario = SCENARIOS.get(scenario_id)
    if not scenario:
        return 1.0
    warming = scenario["warming"]
    years = sorted(warming.keys())
    if year <= years[0]:
        delta_t = warming[years[0]]
    elif year >= years[-1]:
        delta_t = warming[years[-1]]
    else:
        for i in range(len(years) - 1):
            y0, y1 = years[i], years[i + 1]
            if y0 <= year <= y1:
                frac = (year - y0) / (y1 - y0)
                delta_t = warming[y0] + frac * (warming[y1] - warming[y0])
                break
    return get_hazard_multiplier(hazard, delta_t)


def list_scenarios() -> List[dict]:
    return [{"id": k, **v} for k, v in SCENARIOS.items()]


def list_horizons() -> List[int]:
    return [2030, 2040, 2050, 2080]
