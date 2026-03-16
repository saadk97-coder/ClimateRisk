"""
Climate Exposure Scoring — normalised risk scores and Climate Value-at-Risk.

Provides:
  • Climate Exposure Score (1–10) — hazard-specific normalised risk rating per asset,
    comparable across the portfolio regardless of asset size. Analogous to industry
    risk-rating systems but grounded in the platform's own EAD calculations.

  • Expected Annual Loss Ratio (EALR %) — expected annual physical damage
    expressed as a percentage of replacement value, enabling cross-portfolio comparison.
    This is an expected-loss metric, not a tail Value-at-Risk measure.

  • 30-Year Forward Risk Projection — year-by-year score trajectory from 2025–2050,
    showing how risk evolves under each scenario.

  • Stranded Asset Analysis — flags assets where cumulative discounted climate costs
    exceed a defined threshold of asset value, suggesting active financial impairment.

Scoring methodology
-------------------
The Climate Exposure Score is derived from the asset's EALR (Expected Annual Loss Ratio = EAD/value)
using a log-transformed normalisation to spread scores across the 1–10 range:

    raw_pct = EAD / replacement_value × 100
    score   = 1 + 9 × log(1 + raw_pct / midpoint) / log(1 + max_pct / midpoint)

Hazard-specific midpoints and maxima reflect the typical damage profile of each peril:
  Flood     : midpoint = 0.5% EAD/value → score 5.5; max = 5% → score 10
  Wind      : midpoint = 0.3%; max = 3%
  Wildfire  : midpoint = 0.4%; max = 4%
  Heat      : midpoint = 0.2%; max = 2%   (chronic; lower single-year peaks)
  Water Str : midpoint = 0.15%; max = 1.5%

These thresholds are calibrated to the platform's vulnerability curve library
(HAZUS/JRC/ILO), not to external provider benchmarks.
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, List, Tuple


# ---------------------------------------------------------------------------
# Scoring calibration — hazard-specific thresholds
# ---------------------------------------------------------------------------
# mid_pct: EAD/value % at which score ≈ 5.5 (midpoint of scale)
# max_pct: EAD/value % that maps to score ≈ 10 (practical ceiling)
_SCORE_PARAMS: Dict[str, Dict[str, float]] = {
    "flood":        {"mid_pct": 0.5,  "max_pct": 5.0},
    "wind":         {"mid_pct": 0.3,  "max_pct": 3.0},
    "wildfire":     {"mid_pct": 0.4,  "max_pct": 4.0},
    "heat":         {"mid_pct": 0.2,  "max_pct": 2.0},
    "coastal_flood": {"mid_pct": 0.6,  "max_pct": 6.0},
    "cyclone":      {"mid_pct": 0.35, "max_pct": 3.5},
    "water_stress": {"mid_pct": 0.15, "max_pct": 1.5},
    "default":      {"mid_pct": 0.4,  "max_pct": 4.0},
}

# Stranded asset threshold: cumulative PV climate costs that trigger a flag
# Default: 15% of asset replacement value over the analysis period
STRANDED_ASSET_THRESHOLD_PCT: float = 15.0


def climate_exposure_score(ead: float, asset_value: float, hazard: str = "default") -> float:
    """
    Compute a Climate Exposure Score (1–10) from EAD and asset value.

    Parameters
    ----------
    ead          : Expected Annual Damage (£ or any currency)
    asset_value  : Asset replacement value (same currency)
    hazard       : Hazard type key for calibration

    Returns
    -------
    Score in range [1.0, 10.0]. Returns 1.0 for zero or negative values.

    Methodology
    -----------
    Log-transformed normalisation on EAD/value %, calibrated per hazard type.
    Log scale prevents a few very-high-damage assets from compressing all others
    to the low end of a linear scale.
    """
    if asset_value <= 0 or ead <= 0:
        return 1.0
    params = _SCORE_PARAMS.get(hazard, _SCORE_PARAMS["default"])
    raw_pct = (ead / asset_value) * 100.0
    mid = params["mid_pct"]
    mx  = params["max_pct"]
    # Log-normalised score: maps [0, max_pct] → [1, 10]
    log_num = np.log1p(raw_pct / mid)
    log_den = np.log1p(mx / mid)
    score = 1.0 + 9.0 * min(log_num / log_den, 1.0)
    return float(np.clip(score, 1.0, 10.0))


def climate_var_pct(ead: float, asset_value: float) -> float:
    """
    Expected Annual Loss Ratio (EALR %) — EAD expressed as % of asset value.

    This is the primary cross-portfolio comparison metric. An EALR of 1%
    means the asset incurs on average 1% of its replacement value annually in
    climate-related damage under the chosen scenario.

    Note: This is an expected loss ratio, not Value-at-Risk in the financial
    sense (which would measure tail loss at a confidence level). The function
    name is retained for backward compatibility.

    Source framing: TCFD (2017) Recommendations of the Task Force on
    Climate-related Financial Disclosures, p.12.
    """
    if asset_value <= 0:
        return 0.0
    return float((ead / asset_value) * 100.0)


def score_label(score: float) -> str:
    """Human-readable risk band for a Climate Exposure Score."""
    if score < 2.5:
        return "Very Low"
    elif score < 4.0:
        return "Low"
    elif score < 5.5:
        return "Moderate"
    elif score < 7.0:
        return "Elevated"
    elif score < 8.5:
        return "High"
    else:
        return "Very High"


def score_color(score: float) -> str:
    """Return BSR-palette colour string for a score band."""
    if score < 2.5:
        return "#2A9D8F"   # teal  — very low
    elif score < 4.0:
        return "#57CC99"   # green — low
    elif score < 5.5:
        return "#E9C46A"   # amber — moderate
    elif score < 7.0:
        return "#F4721A"   # BSR orange — elevated
    elif score < 8.5:
        return "#C94040"   # warm red — high
    else:
        return "#7B2D8B"   # purple — very high


# ---------------------------------------------------------------------------
# Portfolio-level scoring
# ---------------------------------------------------------------------------

def score_portfolio(
    annual_df: pd.DataFrame,
    assets: list,
    year: int = 2050,
    scenario_id: Optional[str] = None,
) -> pd.DataFrame:
    """
    Compute Climate Exposure Scores for all assets and hazards at a given year/scenario.

    Parameters
    ----------
    annual_df   : Output of compute_portfolio_annual_damages (columns: asset_id, scenario_id,
                  year, hazard, ead, pv)
    assets      : List of Asset objects
    year        : Reference year for scores
    scenario_id : If None, uses first available scenario

    Returns
    -------
    DataFrame with columns: asset_id, name, value, hazard, ead, climate_var_pct, score, label
    """
    asset_map = {a.id: a for a in assets}

    if annual_df.empty:
        return pd.DataFrame()

    df = annual_df.copy()
    if scenario_id:
        df = df[df["scenario_id"] == scenario_id]
    else:
        sc = df["scenario_id"].iloc[0] if len(df) > 0 else None
        if sc:
            df = df[df["scenario_id"] == sc]

    df = df[df["year"] == year]

    rows = []
    for _, row in df.iterrows():
        asset = asset_map.get(row["asset_id"])
        if asset is None:
            continue
        val = asset.replacement_value
        ead = float(row.get("ead", 0))
        haz = str(row.get("hazard", "default"))
        score = climate_exposure_score(ead, val, haz)
        rows.append({
            "asset_id":        row["asset_id"],
            "name":            asset.name,
            "asset_type":      asset.asset_type,
            "region":          asset.region,
            "value":           val,
            "hazard":          haz,
            "ead":             ead,
            "climate_var_pct": climate_var_pct(ead, val),
            "score":           score,
            "label":           score_label(score),
            "color":           score_color(score),
        })

    return pd.DataFrame(rows)


def portfolio_climate_var(
    annual_df: pd.DataFrame,
    assets: list,
    year: int = 2050,
    scenario_id: Optional[str] = None,
) -> Dict[str, float]:
    """
    Aggregate Expected Annual Loss Ratio (EALR) at portfolio level.

    Returns
    -------
    Dict with:
      portfolio_ead        : total EAD across all assets and hazards
      portfolio_value      : total replacement value
      portfolio_var_pct    : portfolio-level EALR (%) — retained name for compat
      var_by_hazard        : {hazard: (ead, ealr_pct)} breakdown
      var_by_asset         : {asset_id: (ead, ealr_pct)} breakdown
    """
    asset_map = {a.id: a for a in assets}
    total_value = sum(a.replacement_value for a in assets)

    if annual_df.empty or total_value == 0:
        return {"portfolio_ead": 0.0, "portfolio_value": total_value,
                "portfolio_var_pct": 0.0, "var_by_hazard": {}, "var_by_asset": {}}

    df = annual_df.copy()
    if scenario_id:
        df = df[df["scenario_id"] == scenario_id]
    df = df[df["year"] == year]

    total_ead = float(df["ead"].sum())

    var_by_hazard = {}
    for haz, grp in df.groupby("hazard"):
        h_ead = float(grp["ead"].sum())
        var_by_hazard[haz] = {"ead": h_ead, "var_pct": h_ead / total_value * 100}

    var_by_asset = {}
    for aid, grp in df.groupby("asset_id"):
        asset = asset_map.get(aid)
        a_ead = float(grp["ead"].sum())
        a_val = asset.replacement_value if asset else 1.0
        var_by_asset[aid] = {"ead": a_ead, "var_pct": a_ead / a_val * 100}

    return {
        "portfolio_ead":     total_ead,
        "portfolio_value":   total_value,
        "portfolio_var_pct": total_ead / total_value * 100,
        "var_by_hazard":     var_by_hazard,
        "var_by_asset":      var_by_asset,
    }


def forward_risk_scores(
    annual_df: pd.DataFrame,
    asset_id: str,
    asset_value: float,
    scenario_id: Optional[str] = None,
    hazard: Optional[str] = None,
) -> Dict[int, float]:
    """
    Return year → Climate Exposure Score mapping for a single asset.
    If hazard is None, uses combined EAD across all hazards (with 'default' calibration).
    """
    if annual_df.empty:
        return {}

    df = annual_df.copy()
    if scenario_id:
        df = df[df["scenario_id"] == scenario_id]
    df = df[df["asset_id"] == asset_id]
    if hazard:
        df = df[df["hazard"] == hazard]

    year_scores: Dict[int, float] = {}
    for yr, grp in df.groupby("year"):
        total_ead = float(grp["ead"].sum())
        haz_key = hazard if hazard else "default"
        year_scores[int(yr)] = climate_exposure_score(total_ead, asset_value, haz_key)

    return year_scores


# ---------------------------------------------------------------------------
# Stranded Asset Analysis
# ---------------------------------------------------------------------------

def stranded_asset_analysis(
    annual_df: pd.DataFrame,
    assets: list,
    scenario_id: Optional[str] = None,
    threshold_pct: float = STRANDED_ASSET_THRESHOLD_PCT,
) -> pd.DataFrame:
    """
    Flag assets where cumulative discounted physical climate costs exceed
    a threshold percentage of replacement value.

    The 'stranded asset' concept from TCFD/IPCC refers to assets whose
    economic value is impaired earlier than expected as a result of
    climate-related factors. Here we apply it to cumulative physical
    damage rather than the traditional transition-risk framing.

    Parameters
    ----------
    threshold_pct : Cumulative PV damages as % of value above which asset is flagged.
                    Default: 15% — broadly consistent with insurance total-loss thresholds.

    Returns
    -------
    DataFrame with columns: asset_id, name, value, cumulative_pv, pv_as_pct_of_value,
                             stranded_flag, stranded_year (first year score > threshold/2)
    """
    asset_map = {a.id: a for a in assets}

    if annual_df.empty:
        return pd.DataFrame()

    df = annual_df.copy()
    if scenario_id:
        df = df[df["scenario_id"] == scenario_id]

    rows = []
    for aid, grp in df.groupby("asset_id"):
        asset = asset_map.get(aid)
        if asset is None:
            continue
        val = asset.replacement_value
        cumulative_pv = float(grp["pv"].sum())
        pv_pct = cumulative_pv / val * 100 if val > 0 else 0.0
        stranded = pv_pct >= threshold_pct

        # First year where annual EAD alone exceeds 5% of value (acute impairment signal)
        acute_threshold = val * 0.05
        annual_totals = grp.groupby("year")["ead"].sum()
        breach_years = annual_totals[annual_totals >= acute_threshold].index
        first_breach = int(breach_years.min()) if len(breach_years) > 0 else None

        rows.append({
            "asset_id":             aid,
            "name":                 asset.name,
            "asset_type":           asset.asset_type,
            "region":               asset.region,
            "value":                val,
            "cumulative_pv":        cumulative_pv,
            "pv_as_pct_of_value":   pv_pct,
            "stranded_flag":        stranded,
            "acute_breach_year":    first_breach,
            "threshold_pct":        threshold_pct,
        })

    return pd.DataFrame(rows)
