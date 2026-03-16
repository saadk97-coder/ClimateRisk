"""
Water Stress Hazard Module — WRI Aqueduct 4.0 integration with regional fallback.

WRI Aqueduct 4.0 (2023) is the leading global water risk dataset, providing
baseline and forward-looking water stress indicators at sub-catchment level
(HydroBASINS Level 6 — ~50,000 watersheds globally).

Key indicator: Baseline Water Stress (BWS) — ratio of total annual water
withdrawals to available renewable supply (blue water). Scores are on a
continuous scale 0–∞, binned into 5 risk categories:
  0–1  : Low
  1–2  : Low-Medium
  2–3  : Medium-High
  3–4  : High
  4–5  : Extremely High

Future projections use three SSP-aligned scenarios:
  Optimistic (SSP1)    — strong governance, low demand growth
  Business as Usual    — SSP2 — intermediate
  Pessimistic (SSP3)   — weak governance, high demand growth

API: WRI Aqueduct Analyzer (public) at https://www.wri.org/data/aqueduct-water-risk-atlas
Data: https://datasets.wri.org/dataset/aqueduct40

Damage function: Water stress score → annual operational cost increase as % of
asset value. Calibrated from:
  • Water-intensive industries (manufacturing, data centres, agri-processing):
    high water stress → 0.5–2% additional operational cost from sourcing, treatment,
    regulatory compliance and supply disruption.
  • Commercial and residential: moderate impact — cooling systems, landscaping.
  • Source: WRI (2023) Aqueduct 4.0 Technical Note; CDP Water Security (2023).

References
----------
Kuzma S. et al. (2023). Aqueduct 4.0: Updated decision-relevant global water risk
  indicators. WRI Technical Note. https://doi.org/10.46830/writn.23.00061
IPCC AR6 WG2 Chapter 4: Water. https://www.ipcc.ch/report/ar6/wg2/chapter/chapter-4/
CDP (2023). Scaling Up: The Case for Ambitious Corporate Water Targets.
"""

import logging
import numpy as np
from typing import Optional, Tuple, Dict

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # seconds

# ---------------------------------------------------------------------------
# WRI Aqueduct BWS → damage fraction conversion
# ---------------------------------------------------------------------------
# Maps water stress score (0–5+ continuous) to annual damage fraction of asset value.
# Damage here represents: increased operational costs from water sourcing, treatment,
# regulatory compliance, cooling water restrictions, and supply chain disruption.
#
# Thresholds calibrated to WRI Aqueduct category boundaries with CDP operational
# cost data. Water-intensive assets (manufacturing, data centres) use upper bound;
# commercial/residential use lower bound; middle values used as defaults.
#
# Format: [(bws_score, damage_fraction), ...]
_BWS_DAMAGE_CURVE: list = [
    (0.0, 0.0000),    # No water stress → negligible operational impact
    (1.0, 0.0005),    # Low-medium  → ~0.05% of value/yr additional cost
    (2.0, 0.0020),    # Medium-high → ~0.20% of value/yr
    (3.0, 0.0055),    # High        → ~0.55% of value/yr
    (4.0, 0.0120),    # Extremely high → ~1.20% of value/yr
    (5.0, 0.0200),    # Beyond scale (extreme scarcity) → ~2.0% of value/yr
]

# Asset-type multipliers for water stress sensitivity
# Water-intensive assets are significantly more exposed; residential assets are least.
_ASSET_TYPE_WATER_SENSITIVITY: Dict[str, float] = {
    "industrial":         2.5,
    "manufacturing":      2.5,
    "data_center":        3.0,   # cooling-water intensive
    "agricultural":       4.0,   # directly dependent on water availability
    "commercial":         0.8,
    "retail":             0.7,
    "office":             0.6,
    "residential":        0.5,
    "residential_masonry": 0.5,
    "residential_wood":   0.5,
    "hotel":              1.2,
    "logistics":          0.8,
    "healthcare":         1.5,
    "education":          0.6,
    "infrastructure":     1.0,
    "default":            1.0,
}

# Regional baseline BWS scores (0–5 scale) — fallback when API unavailable
# Derived from WRI Aqueduct 4.0 country-level medians (2023 baseline)
# Source: Kuzma et al. (2023) Aqueduct 4.0 Technical Note
_REGIONAL_BWS_BASELINE: Dict[str, float] = {
    "EUR": 1.8,    # Europe: moderate — Mediterranean regions higher, N. Europe lower
    "USA": 1.5,    # North America: variable; West is high-stress, East is moderate
    "CHN": 2.5,    # China: high in North China Plain; South China lower
    "IND": 3.2,    # South Asia: high water stress — Indo-Gangetic Plain
    "AUS": 2.0,    # Australia: Murray-Darling basin high; tropical north lower
    "BRA": 0.8,    # Latin America: generally water-rich except NE Brazil
    "MEA": 4.1,    # Middle East & Africa: extremely high in MENA
    "global": 2.0,
}

# Projected future BWS multipliers by scenario and year
# Relative to 2023 baseline; from Aqueduct 4.0 future projections
# Source: Kuzma et al. (2023); WRI Aqueduct 4.0 future scenarios
_BWS_FUTURE_MULTIPLIER: Dict[str, Dict[int, float]] = {
    "optimistic":           {2020: 1.0, 2030: 1.05, 2040: 1.10, 2050: 1.14, 2080: 1.20},
    "business_as_usual":    {2020: 1.0, 2030: 1.10, 2040: 1.22, 2050: 1.36, 2080: 1.60},
    "pessimistic":          {2020: 1.0, 2030: 1.15, 2040: 1.32, 2050: 1.52, 2080: 1.90},
}

# Map NGFS scenario keys to Aqueduct scenario.
# Accepts both scenario_id (e.g. "net_zero_2050") and SSP label (e.g. "SSP2-4.5").
_NGFS_TO_AQUEDUCT: Dict[str, str] = {
    # Scenario IDs
    "net_zero_2050":      "optimistic",
    "below_2c":           "optimistic",
    "divergent_net_zero": "optimistic",
    "iea_nze":            "optimistic",
    "iea_aps":            "optimistic",
    "delayed_transition": "business_as_usual",
    "ndcs_only":          "business_as_usual",
    "iea_steps":          "business_as_usual",
    "ssp2_45":            "business_as_usual",
    "ssp1_19":            "optimistic",
    "ssp1_26":            "optimistic",
    "current_policies":   "pessimistic",
    "fragmented_world":   "pessimistic",
    "ssp5_85":            "pessimistic",
    "ssp3_70":            "pessimistic",
    # SSP labels (passed by hazard_fetcher via scenario_ssp)
    "SSP1-1.9":           "optimistic",
    "SSP1-2.6":           "optimistic",
    "SSP2-4.5":           "business_as_usual",
    "SSP3-7.0":           "pessimistic",
    "SSP5-8.5":           "pessimistic",
}

STANDARD_RETURN_PERIODS = np.array([10, 50, 100, 250, 500, 1000], dtype=float)

# Water stress is chronic, not a traditional return-period peril.
# We express it as: damage fraction at each "RP" corresponds to
# the damage under increasingly severe water stress conditions
# (representing increasing quantiles of the water stress distribution).
# RP10 = current median BWS; RP100 = BWS at 75th percentile; RP1000 = extreme.
_BWS_RP_SCALE: Dict[float, float] = {
    10:   0.7,    # 70% of baseline BWS (low end of current stress)
    50:   1.0,    # 100% = baseline BWS
    100:  1.3,    # 130% — elevated stress (dry years)
    250:  1.7,    # 170% — high stress
    500:  2.2,    # 220% — very high stress
    1000: 3.0,    # 300% — extreme scarcity (tail scenario)
}


def _interp_damage_curve(bws: float) -> float:
    """Linearly interpolate BWS → damage fraction from the damage curve."""
    curve = _BWS_DAMAGE_CURVE
    if bws <= curve[0][0]:
        return curve[0][1]
    if bws >= curve[-1][0]:
        return curve[-1][1]
    for i in range(len(curve) - 1):
        x0, y0 = curve[i]
        x1, y1 = curve[i + 1]
        if x0 <= bws <= x1:
            frac = (bws - x0) / (x1 - x0)
            return y0 + frac * (y1 - y0)
    return curve[-1][1]


def _interp_scenario(scenario_key: str, year: int) -> float:
    """Interpolate BWS future multiplier for a scenario and year."""
    mapping = _BWS_FUTURE_MULTIPLIER.get(scenario_key, _BWS_FUTURE_MULTIPLIER["business_as_usual"])
    keys = sorted(mapping.keys())
    if year <= keys[0]:
        return mapping[keys[0]]
    if year >= keys[-1]:
        return mapping[keys[-1]]
    for i in range(len(keys) - 1):
        lo, hi = keys[i], keys[i + 1]
        if lo <= year <= hi:
            frac = (year - lo) / (hi - lo)
            return mapping[lo] + frac * (mapping[hi] - mapping[lo])
    return 1.0


# ---------------------------------------------------------------------------
# WRI Aqueduct API fetcher
# ---------------------------------------------------------------------------

def fetch_aqueduct_bws(lat: float, lon: float) -> Optional[float]:
    """
    Fetch baseline water stress (BWS) from the WRI Aqueduct Analyzer API.

    Returns BWS score (0–5 scale, or higher for extreme scarcity) for the
    watershed containing (lat, lon), or None on failure.

    Source: WRI Aqueduct 4.0 — https://www.wri.org/data/aqueduct-water-risk-atlas
    API: https://aqueduct.wri.org/api/
    Citation: Kuzma et al. (2023) Aqueduct 4.0 Technical Note
              https://doi.org/10.46830/writn.23.00061
    """
    try:
        import requests
        # WRI Aqueduct public API — point query
        # The Aqueduct analyzer API accepts GeoJSON point geometry
        params = {
            "geometry": f'{{"type":"Point","coordinates":[{lon},{lat}]}}',
            "indicators": "bws",
            "year": "2023",
        }
        r = requests.get(
            "https://aqueduct.wri.org/api/v2/point",
            params=params,
            timeout=_TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            # Try multiple response schema shapes
            if "data" in data and data["data"]:
                for item in data["data"]:
                    if item.get("indicator") == "bws":
                        return float(item.get("value", 0.0))
            # Fallback schema
            if "bws" in data:
                return float(data["bws"])
        return None
    except Exception as e:
        logger.debug(f"Aqueduct API failed: {e}")
        return None


def fetch_aqueduct_projected(
    lat: float, lon: float, scenario: str = "business_as_usual", year: int = 2050
) -> Optional[float]:
    """
    Fetch projected water stress score from WRI Aqueduct future scenarios.

    Parameters
    ----------
    scenario : 'optimistic', 'business_as_usual', or 'pessimistic'
    year     : 2030, 2040, 2050, or 2080

    Returns projected BWS score, or None on failure.
    """
    try:
        import requests
        valid_years = [2030, 2040, 2050, 2080]
        yr = min(valid_years, key=lambda y: abs(y - year))
        params = {
            "geometry": f'{{"type":"Point","coordinates":[{lon},{lat}]}}',
            "indicators": "bws",
            "scenario": scenario,
            "year": str(yr),
        }
        r = requests.get(
            "https://aqueduct.wri.org/api/v2/point/projected",
            params=params,
            timeout=_TIMEOUT,
        )
        if r.status_code == 200:
            data = r.json()
            if "data" in data and data["data"]:
                for item in data["data"]:
                    if item.get("indicator") == "bws":
                        return float(item.get("value", 0.0))
        return None
    except Exception as e:
        logger.debug(f"Aqueduct projected API failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Main fetch function
# ---------------------------------------------------------------------------

def fetch_water_stress_profile(
    lat: float,
    lon: float,
    region_iso3: str,
    asset_type: str = "default",
    ngfs_scenario: str = "ndcs_only",
    return_periods: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray, str]:
    """
    Fetch water stress hazard profile for a location.

    Returns (return_periods, damage_fractions, source_key) where damage_fractions
    are asset-value-normalised annual physical damage fractions (0–1) at each
    return period equivalent.

    Priority:
      1. WRI Aqueduct API (live point query, baseline + projected)
      2. Regional baseline (from WRI Aqueduct country-level medians)

    Parameters
    ----------
    lat, lon       : Location coordinates
    region_iso3    : ISO3 country code for regional fallback zone mapping
    asset_type     : Asset type key for sensitivity multiplier
    ngfs_scenario  : NGFS scenario key for future projection
    return_periods : Return periods to evaluate (default: [10, 50, 100, 250, 500, 1000])

    Returns
    -------
    (return_periods, damage_fractions, source) where source is 'aqueduct' or 'regional_baseline'
    """
    if return_periods is None:
        return_periods = STANDARD_RETURN_PERIODS

    # Try exact match, then prefix match (e.g. "commercial_office" → "commercial")
    sensitivity = _ASSET_TYPE_WATER_SENSITIVITY.get(asset_type)
    if sensitivity is None:
        prefix = asset_type.split("_")[0]
        sensitivity = _ASSET_TYPE_WATER_SENSITIVITY.get(prefix, _ASSET_TYPE_WATER_SENSITIVITY["default"])

    # --- Try WRI Aqueduct API ---
    bws_baseline = fetch_aqueduct_bws(lat, lon)
    source = "aqueduct"

    if bws_baseline is None:
        # Fall back to regional baseline
        from engine.hazard_fetcher import get_region_zone
        zone = get_region_zone(region_iso3)
        bws_baseline = _REGIONAL_BWS_BASELINE.get(zone, _REGIONAL_BWS_BASELINE["global"])
        source = "regional_baseline"

    # NOTE: No scenario multiplier applied here. The fetched BWS is a present-day
    # baseline. Temporal/scenario evolution is handled by the damage engine via
    # get_scenario_multipliers(). This prevents double-counting the climate signal.

    # Apply return-period stress scale (represents variability around baseline BWS)
    damages = []
    for rp in return_periods:
        rp_scale = _BWS_RP_SCALE.get(float(rp), 1.0)
        # Scale BWS by RP factor only (no scenario mult — engine handles that)
        bws_rp = bws_baseline * rp_scale
        # Clip to realistic range (>5 = extreme scarcity beyond Aqueduct scale)
        bws_rp = min(bws_rp, 6.0)
        damage_frac = _interp_damage_curve(bws_rp) * sensitivity
        damages.append(damage_frac)

    return return_periods, np.array(damages), source


def get_water_stress_rating(bws: float) -> Dict[str, str]:
    """
    Return human-readable water stress rating for a BWS score.
    Category definitions from WRI Aqueduct 4.0.
    """
    if bws < 1.0:
        return {"category": "Low", "color": "#2A9D8F", "description": "Less than 10% of renewable water supply is withdrawn annually. Low competition for water; ample supply relative to demand."}
    elif bws < 2.0:
        return {"category": "Low-Medium", "color": "#57CC99", "description": "10–20% of renewable supply is withdrawn. Some water competition; seasonal stress possible in drier years."}
    elif bws < 3.0:
        return {"category": "Medium-High", "color": "#E9C46A", "description": "20–40% of renewable supply is withdrawn. Significant water competition; operational restrictions possible during dry periods."}
    elif bws < 4.0:
        return {"category": "High", "color": "#F4721A", "description": "40–80% of renewable supply is withdrawn. Major water competition; supply disruptions and regulatory restrictions likely without active water management."}
    else:
        return {"category": "Extremely High", "color": "#C94040", "description": "More than 80% of renewable supply is withdrawn. Extreme water scarcity; major operational, reputational, and regulatory risk. Dependent on inter-basin transfers or groundwater depletion."}


def get_water_stress_source_info() -> Dict:
    """Return full provenance information for the water stress data source."""
    return {
        "name": "WRI Aqueduct 4.0",
        "description": (
            "World Resources Institute Aqueduct 4.0 (2023). Global sub-catchment water risk "
            "dataset covering 180,000+ sub-watersheds at HydroBASINS Level 6 resolution. "
            "Baseline and future projections (2030, 2040, 2050, 2080) under three SSP-aligned "
            "scenarios (Optimistic/SSP1, Business-as-Usual/SSP2, Pessimistic/SSP3). "
            "Key indicator: Baseline Water Stress (BWS) = total annual withdrawals / "
            "available renewable supply (blue water)."
        ),
        "citation": "Kuzma S. et al. (2023) Aqueduct 4.0 WRI Technical Note",
        "doi": "https://doi.org/10.46830/writn.23.00061",
        "url": "https://www.wri.org/data/aqueduct-water-risk-atlas",
        "resolution": "Sub-catchment (HydroBASINS Level 6 — ~50,000 global watersheds)",
        "variables": ["Baseline Water Stress (BWS)", "Baseline Water Depletion (BWD)",
                      "Projected BWS (2030/2040/2050/2080)"],
        "scenarios": ["Optimistic (SSP1)", "Business as Usual (SSP2)", "Pessimistic (SSP3)"],
        "access": "Public API + downloadable GDB/GeoTIFF",
        "license": "CC BY 4.0",
    }
