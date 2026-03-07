"""
Climate scenario definitions: NGFS Phase V (2023), IEA WEO 2023, IPCC AR6 SSPs.

Sources
-------
NGFS Phase V Technical Note (Nov 2023):
  https://www.ngfs.net/sites/default/files/medias/documents/ngfs_climate_scenarios_phase_v.pdf
NGFS Scenarios Portal:
  https://www.ngfs.net/ngfs-scenarios-portal/

IEA World Energy Outlook 2023:
  https://www.iea.org/reports/world-energy-outlook-2023

IPCC AR6 WG1 SPM Table 1 (temperature ranges by SSP):
  https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/
IPCC AR6 WG1 Chapter 11 (weather extremes):
  https://www.ipcc.ch/report/ar6/wg1/chapter/chapter-11/
IPCC AR6 WG1 Chapter 12 (regional climates):
  https://www.ipcc.ch/report/ar6/wg1/chapter/chapter-12/

Hazard scaling factors derived from:
  Tabari (2020), Science of The Total Environment — flood frequency scaling
    https://doi.org/10.1016/j.scitotenv.2020.140612
  Knutson et al. (2020) — tropical cyclone intensity changes
    https://doi.org/10.1175/BAMS-D-18-0194.1
  Jolly et al. (2015) — fire weather index trends
    https://doi.org/10.1038/ncomms8537
  Zhao et al. (2021) — heat stress economic impacts
    https://doi.org/10.1038/s41586-021-03305-z
"""

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# NGFS Phase V scenarios (November 2023, updated GCAM 6.0 / REMIND-MAgPIE 3.2)
# Warming = global mean surface temperature above 1850–1900 pre-industrial baseline
# Source: https://www.ngfs.net/ngfs-scenarios-portal/
# ---------------------------------------------------------------------------
NGFS_V_SCENARIOS: Dict[str, dict] = {
    "net_zero_2050": {
        "label": "Net Zero 2050",
        "provider": "NGFS Phase V",
        "ssp": "SSP1-1.9",
        "category": "orderly",
        "description": (
            "Immediate, globally co-ordinated action achieves net-zero CO₂ by 2050. "
            "Warming limited to 1.5 °C. Requires rapid, deep decarbonisation across all sectors."
        ),
        "warming": {2025: 1.2, 2030: 1.3, 2040: 1.4, 2050: 1.5, 2060: 1.5, 2080: 1.5, 2100: 1.4},
        "color": "#1a9641",
        "source_url": "https://www.ngfs.net/ngfs-scenarios-portal/",
    },
    "below_2c": {
        "label": "Below 2 °C",
        "provider": "NGFS Phase V",
        "ssp": "SSP1-2.6",
        "category": "orderly",
        "description": (
            "Strong climate policies limit warming well below 2 °C with high probability. "
            "Orderly transition with co-ordinated policy action."
        ),
        "warming": {2025: 1.2, 2030: 1.4, 2040: 1.55, 2050: 1.7, 2060: 1.75, 2080: 1.8, 2100: 1.8},
        "color": "#78c679",
        "source_url": "https://www.ngfs.net/ngfs-scenarios-portal/",
    },
    "divergent_net_zero": {
        "label": "Divergent Net Zero",
        "provider": "NGFS Phase V",
        "ssp": "SSP1-1.9",
        "category": "disorderly",
        "description": (
            "NEW in Phase V. Net-zero achieved by 2050 but via divergent sectoral pathways — "
            "faster action in some regions/sectors offset by slower progress elsewhere. "
            "Higher near-term transition risk than 'Net Zero 2050'."
        ),
        "warming": {2025: 1.2, 2030: 1.35, 2040: 1.5, 2050: 1.6, 2060: 1.55, 2080: 1.5, 2100: 1.4},
        "color": "#addd8e",
        "source_url": "https://www.ngfs.net/ngfs-scenarios-portal/",
    },
    "delayed_transition": {
        "label": "Delayed Transition",
        "provider": "NGFS Phase V",
        "ssp": "SSP2-4.5",
        "category": "disorderly",
        "description": (
            "Policies delayed until 2030, then sharp transition. "
            "Higher physical risk in near term; stranded-asset risk from sudden late action."
        ),
        "warming": {2025: 1.2, 2030: 1.7, 2040: 1.9, 2050: 2.0, 2060: 2.2, 2080: 2.3, 2100: 2.4},
        "color": "#fd8d3c",
        "source_url": "https://www.ngfs.net/ngfs-scenarios-portal/",
    },
    "ndcs_only": {
        "label": "NDCs Only",
        "provider": "NGFS Phase V",
        "ssp": "SSP2-4.5",
        "category": "hot_house",
        "description": (
            "Countries implement current Nationally Determined Contributions only. "
            "No additional policy beyond stated pledges. Moderate overshoot of Paris targets."
        ),
        "warming": {2025: 1.2, 2030: 1.8, 2040: 2.1, 2050: 2.5, 2060: 2.7, 2080: 3.0, 2100: 3.0},
        "color": "#f03b20",
        "source_url": "https://www.ngfs.net/ngfs-scenarios-portal/",
    },
    "current_policies": {
        "label": "Current Policies",
        "provider": "NGFS Phase V",
        "ssp": "SSP5-8.5",
        "category": "hot_house",
        "description": (
            "Business as usual — no new climate policies beyond those already enacted. "
            "Highest physical risk trajectory."
        ),
        "warming": {2025: 1.2, 2030: 1.9, 2040: 2.4, 2050: 3.0, 2060: 3.5, 2080: 4.3, 2100: 4.3},
        "color": "#bd0026",
        "source_url": "https://www.ngfs.net/ngfs-scenarios-portal/",
    },
}

# ---------------------------------------------------------------------------
# IEA World Energy Outlook 2023 scenarios
# Source: https://www.iea.org/reports/world-energy-outlook-2023
# ---------------------------------------------------------------------------
IEA_WEO_2023_SCENARIOS: Dict[str, dict] = {
    "iea_nze": {
        "label": "Net Zero Emissions (NZE)",
        "provider": "IEA WEO 2023",
        "ssp": "SSP1-1.9",
        "category": "orderly",
        "description": (
            "The energy sector reaches net-zero CO₂ by 2050. "
            "Consistent with keeping the rise in global mean temperatures to 1.5 °C."
        ),
        "warming": {2025: 1.2, 2030: 1.3, 2040: 1.4, 2050: 1.5, 2060: 1.5, 2080: 1.5, 2100: 1.5},
        "color": "#1a9641",
        "source_url": "https://www.iea.org/reports/world-energy-outlook-2023",
    },
    "iea_aps": {
        "label": "Announced Pledges (APS)",
        "provider": "IEA WEO 2023",
        "ssp": "SSP1-2.6",
        "category": "orderly",
        "description": (
            "All climate commitments (NDCs + net-zero pledges) are met in full and on time. "
            "Limits warming to ~1.7 °C by 2100."
        ),
        "warming": {2025: 1.2, 2030: 1.45, 2040: 1.6, 2050: 1.7, 2060: 1.75, 2080: 1.8, 2100: 1.8},
        "color": "#74c476",
        "source_url": "https://www.iea.org/reports/world-energy-outlook-2023",
    },
    "iea_steps": {
        "label": "Stated Policies (STEPS)",
        "provider": "IEA WEO 2023",
        "ssp": "SSP2-4.5",
        "category": "hot_house",
        "description": (
            "Only policies enacted as of mid-2023 are implemented. "
            "Warming of ~2.4 °C by 2100."
        ),
        "warming": {2025: 1.2, 2030: 1.6, 2040: 1.95, 2050: 2.4, 2060: 2.6, 2080: 2.8, 2100: 2.9},
        "color": "#fd8d3c",
        "source_url": "https://www.iea.org/reports/world-energy-outlook-2023",
    },
}

# ---------------------------------------------------------------------------
# IPCC AR6 SSP scenarios (best estimate / median warming)
# Source: IPCC AR6 WG1 SPM Table 1
# https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/
# ---------------------------------------------------------------------------
IPCC_AR6_SCENARIOS: Dict[str, dict] = {
    "ssp1_19": {
        "label": "SSP1-1.9",
        "provider": "IPCC AR6",
        "ssp": "SSP1-1.9",
        "category": "orderly",
        "description": "Very low emissions; ~1.0 °C median by 2100 (range 0.3–1.8 °C).",
        "warming": {2025: 1.1, 2030: 1.1, 2040: 1.2, 2050: 1.4, 2060: 1.4, 2080: 1.3, 2100: 1.0},
        "color": "#1a9641",
        "source_url": "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/",
    },
    "ssp1_26": {
        "label": "SSP1-2.6",
        "provider": "IPCC AR6",
        "ssp": "SSP1-2.6",
        "category": "orderly",
        "description": "Low emissions; ~1.8 °C median by 2100 (range 1.0–2.6 °C).",
        "warming": {2025: 1.2, 2030: 1.3, 2040: 1.5, 2050: 1.7, 2060: 1.8, 2080: 1.8, 2100: 1.8},
        "color": "#78c679",
        "source_url": "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/",
    },
    "ssp2_45": {
        "label": "SSP2-4.5",
        "provider": "IPCC AR6",
        "ssp": "SSP2-4.5",
        "category": "intermediate",
        "description": "Intermediate emissions; ~2.7 °C median by 2100 (range 1.7–3.7 °C).",
        "warming": {2025: 1.2, 2030: 1.4, 2040: 1.8, 2050: 2.1, 2060: 2.3, 2080: 2.6, 2100: 2.7},
        "color": "#fecc5c",
        "source_url": "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/",
    },
    "ssp3_70": {
        "label": "SSP3-7.0",
        "provider": "IPCC AR6",
        "ssp": "SSP3-7.0",
        "category": "hot_house",
        "description": "High emissions; ~3.6 °C median by 2100 (range 2.3–5.0 °C).",
        "warming": {2025: 1.2, 2030: 1.5, 2040: 2.0, 2050: 2.4, 2060: 2.7, 2080: 3.3, 2100: 3.6},
        "color": "#f03b20",
        "source_url": "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/",
    },
    "ssp5_85": {
        "label": "SSP5-8.5",
        "provider": "IPCC AR6",
        "ssp": "SSP5-8.5",
        "category": "hot_house",
        "description": "Very high emissions; ~4.4 °C median by 2100 (range 3.3–5.7 °C).",
        "warming": {2025: 1.2, 2030: 1.6, 2040: 2.2, 2050: 2.8, 2060: 3.3, 2080: 4.0, 2100: 4.4},
        "color": "#bd0026",
        "source_url": "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/",
    },
}

# Master dict (backward-compatible — NGFS Phase V is the default set)
SCENARIOS: Dict[str, dict] = {**NGFS_V_SCENARIOS, **IEA_WEO_2023_SCENARIOS, **IPCC_AR6_SCENARIOS}

SCENARIO_PROVIDERS = {
    "NGFS Phase V": NGFS_V_SCENARIOS,
    "IEA WEO 2023": IEA_WEO_2023_SCENARIOS,
    "IPCC AR6": IPCC_AR6_SCENARIOS,
}

PROVIDER_SOURCES = {
    "NGFS Phase V": "https://www.ngfs.net/ngfs-scenarios-portal/",
    "IEA WEO 2023": "https://www.iea.org/reports/world-energy-outlook-2023",
    "IPCC AR6": "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/",
}

# ---------------------------------------------------------------------------
# Hazard intensity scaling factors per ΔT (multipliers on 1995–2014 baseline)
# All values are median estimates; see source studies above.
# ---------------------------------------------------------------------------
HAZARD_SCALING = {
    "flood": {
        # ~5–8 % per °C from Tabari 2020; AR6 WG1 Ch.11 Box 11.1
        # https://doi.org/10.1016/j.scitotenv.2020.140612
        1.0: 1.05, 1.5: 1.10, 2.0: 1.18, 2.5: 1.28, 3.0: 1.40, 4.0: 1.65, 4.4: 1.80,
    },
    "wind": {
        # Tropical cyclone max intensity +5 % per 2 °C; Knutson et al. 2020
        # https://doi.org/10.1175/BAMS-D-18-0194.1
        1.0: 1.02, 1.5: 1.04, 2.0: 1.07, 2.5: 1.10, 3.0: 1.13, 4.0: 1.20, 4.4: 1.25,
    },
    "wildfire": {
        # Fire Weather Index steep increase; Jolly et al. 2015
        # https://doi.org/10.1038/ncomms8537
        1.0: 1.10, 1.5: 1.20, 2.0: 1.45, 2.5: 1.70, 3.0: 1.90, 4.0: 2.40, 4.4: 2.70,
    },
    "heat": {
        # Cooling degree-day / productivity loss super-linear; Zhao et al. 2021
        # https://doi.org/10.1038/s41586-021-03305-z
        1.0: 1.15, 1.5: 1.30, 2.0: 1.65, 2.5: 2.00, 3.0: 2.40, 4.0: 3.30, 4.4: 3.90,
    },
    "cyclone": {
        # Same as wind but slightly amplified for storm surge component
        1.0: 1.03, 1.5: 1.06, 2.0: 1.10, 2.5: 1.15, 3.0: 1.20, 4.0: 1.32, 4.4: 1.40,
    },
}

HAZARD_SCALING_SOURCES = {
    "flood": {
        "citation": "Tabari (2020), Science of the Total Environment. AR6 WG1 Ch.11 Box 11.1.",
        "url": "https://doi.org/10.1016/j.scitotenv.2020.140612",
        "ar6_url": "https://www.ipcc.ch/report/ar6/wg1/chapter/chapter-11/",
    },
    "wind": {
        "citation": "Knutson et al. (2020), Bulletin of the American Meteorological Society.",
        "url": "https://doi.org/10.1175/BAMS-D-18-0194.1",
    },
    "wildfire": {
        "citation": "Jolly et al. (2015), Nature Communications — global fire weather trends.",
        "url": "https://doi.org/10.1038/ncomms8537",
    },
    "heat": {
        "citation": "Zhao et al. (2021), Nature — global labour productivity & heat stress.",
        "url": "https://doi.org/10.1038/s41586-021-03305-z",
    },
    "cyclone": {
        "citation": "Knutson et al. (2020) — tropical cyclone intensity scaling.",
        "url": "https://doi.org/10.1175/BAMS-D-18-0194.1",
    },
}


def _interp(mapping: dict, x: float) -> float:
    keys = sorted(mapping.keys())
    if x <= keys[0]:
        return mapping[keys[0]]
    if x >= keys[-1]:
        return mapping[keys[-1]]
    for i in range(len(keys) - 1):
        lo, hi = keys[i], keys[i + 1]
        if lo <= x <= hi:
            frac = (x - lo) / (hi - lo)
            return mapping[lo] + frac * (mapping[hi] - mapping[lo])
    return 1.0


def get_hazard_multiplier(hazard: str, warming_delta_c: float) -> float:
    """Return hazard intensity multiplier for a given warming level (°C above pre-industrial)."""
    return _interp(HAZARD_SCALING.get(hazard, {}), warming_delta_c)


def get_warming(scenario_id: str, year: int) -> float:
    """Interpolate warming (°C above pre-industrial) for scenario and year."""
    sc = SCENARIOS.get(scenario_id, {})
    w = sc.get("warming", {})
    if not w:
        return 1.2
    return _interp(w, year)


def get_scenario_multipliers(scenario_id: str, year: int, hazard: str) -> float:
    """Return hazard intensity multiplier for a given scenario, year, and hazard."""
    delta_t = get_warming(scenario_id, year)
    return get_hazard_multiplier(hazard, delta_t)


def list_scenarios(provider: Optional[str] = None) -> List[dict]:
    if provider and provider in SCENARIO_PROVIDERS:
        src = SCENARIO_PROVIDERS[provider]
    else:
        src = NGFS_V_SCENARIOS  # default
    return [{"id": k, **v} for k, v in src.items()]


def list_horizons() -> List[int]:
    return list(range(2025, 2051))


def list_default_horizons() -> List[int]:
    """Coarse horizons for backward-compat scenario comparison charts."""
    return [2030, 2040, 2050]
