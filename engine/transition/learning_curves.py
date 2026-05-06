"""
Layer 2 — Technology disruption with learning-curve aware projections.

Methodology
-----------
Wright's Law:
  Cost(Q) = Cost(Q0) * (Q / Q0) ^ b      where  b = log2(1 - LR)

Lafond et al. (2018) distributional forecast:
  log Cost_t  ~ Normal(mu = log Cost_pred(t), sigma = lafond_sigma * sqrt(t))

For each asset:
  1. Look up incumbent and challenger technologies (from sector_taxonomy).
  2. Project cumulative-capacity-weighted unit costs forward to each year using
     Wright's Law and the scenario-specific deployment growth.
  3. Identify the year of cost crossover (challenger ≤ incumbent).
  4. Stranded-asset trigger: if crossover < end-of-life, flag and compute
     impairment via a logistic decline curve calibrated so that:
       - 0% impairment up to crossover − 5y
       - 50% at crossover
       - ~95% by crossover + 10y (for fossil-dependent assets)
       - capped at fossil_dependency_pct of replacement value
  5. Translate revenue erosion through the sector_pathways multiplier.

Sources
-------
- Way, Ives, Mealy, Farmer (2022). 'Empirically grounded technology forecasts and
  the energy transition.' Joule 6(9): 2057-2082.
- Lafond et al. (2018). 'How well do experience curves predict technological
  progress?' TFSC 128: 104-117.
- Carbon Tracker (2022). 'A tale of two share issues: stranded asset risk in
  fossil fuel reserves.'
"""

from __future__ import annotations
from dataclasses import dataclass
from math import log2, exp, sqrt, log
from typing import Dict, List, Optional, Tuple
import logging

from engine.transition.data_loader import (
    load_learning_curves,
    load_sector_pathways,
    load_sector_taxonomy,
    map_scenario_to_ngfs,
)

_log = logging.getLogger(__name__)

# Reference cumulative capacity index at base year 2025 = 1.0; subsequent years
# scaled by annual capacity growth from learning_curves.json.
_BASE_YEAR = 2025


@dataclass
class TechnologyProjection:
    technology: str
    label: str
    learning_rate: float
    cost_2025: float
    year: int
    projected_cost: float
    cost_lo: float                   # 1-σ lower band (Lafond)
    cost_hi: float                   # 1-σ upper band
    cumulative_capacity_index: float


@dataclass
class StrandingResult:
    asset_id: str
    sector: str
    scenario_id: str
    incumbent_tech: str
    challenger_tech: Optional[str]
    crossover_year: Optional[int]    # None if no crossover within horizon
    stranded_fraction_2050: float    # fraction of replacement value impaired by 2050
    annual_impairment_usd: Dict[int, float]  # {year: impairment in USD}
    revenue_index: Dict[int, float]  # {year: revenue multiplier (sector_pathways)}
    notes: str = ""


def _project_cost(tech: str, scenario_id: str, year: int) -> Optional[TechnologyProjection]:
    """Project a technology's unit cost to `year` using Wright's Law + Lafond bands."""
    lc = load_learning_curves()
    techs = lc["technologies"]
    if tech not in techs:
        return None
    t = techs[tech]
    lr = float(t["learning_rate"])
    sigma = float(t.get("lafond_sigma", 0.05))
    growth_map = t.get("annual_capacity_growth_2025_2050", {})
    g_raw = float(growth_map.get(map_scenario_to_ngfs(scenario_id),
                                 growth_map.get(scenario_id, 0.0)))
    # Cumulative installed capacity is monotonic non-decreasing — negative
    # growth in the source data represents demand decline, captured in
    # sector_pathways. Clamp at 0 here so Wright's Law isn't run backwards.
    g = max(g_raw, 0.0)

    years_ahead = max(0, year - _BASE_YEAR)
    # Cumulative capacity index Q/Q0 (compound growth)
    q_ratio = (1.0 + g) ** years_ahead
    if lr <= 0 or q_ratio <= 0:
        b = 0.0
    else:
        b = log2(max(1.0 - lr, 1e-6))   # Wright's Law exponent (negative for LR>0)

    # Find base cost field — first key starting with "cost_2025"
    cost_2025 = next((float(v) for k, v in t.items() if k.startswith("cost_2025")), 0.0)
    if cost_2025 <= 0:
        return None
    pred = cost_2025 * (q_ratio ** b) if lr > 0 else cost_2025 * (1.0 + g * 0.0)
    # If LR=0, no cost change; if Q grows but LR=0, costs stay flat.

    # Lafond log-normal band (1-σ): sigma_t = sigma * sqrt(years_ahead)
    sigma_t = sigma * sqrt(max(years_ahead, 1))
    cost_lo = pred * exp(-sigma_t)
    cost_hi = pred * exp(+sigma_t)

    return TechnologyProjection(
        technology=tech,
        label=t.get("label", tech),
        learning_rate=lr,
        cost_2025=cost_2025,
        year=year,
        projected_cost=pred,
        cost_lo=cost_lo,
        cost_hi=cost_hi,
        cumulative_capacity_index=q_ratio,
    )


def project_technology(tech: str, scenario_id: str, years: List[int]) -> List[TechnologyProjection]:
    """Project a single technology's cost across years."""
    out: List[TechnologyProjection] = []
    for y in years:
        proj = _project_cost(tech, scenario_id, y)
        if proj:
            out.append(proj)
    return out


def find_crossover_year(
    incumbent: str,
    challenger: str,
    scenario_id: str,
    horizon: Tuple[int, int] = (2025, 2050),
) -> Optional[int]:
    """
    Return the first year in [start, end] when challenger <= incumbent cost.
    None if no crossover within horizon. If challenger is already below at start,
    returns the start year.
    """
    if not (incumbent and challenger):
        return None
    start, end = horizon
    for y in range(start, end + 1):
        ci = _project_cost(incumbent, scenario_id, y)
        cc = _project_cost(challenger, scenario_id, y)
        if ci is None or cc is None:
            return None
        # Normalise to same units only when units match — both should be cost
        # per common output. We compare projected_cost directly assuming the
        # taxonomy pairs technologies with comparable functional units.
        if cc.projected_cost <= ci.projected_cost:
            return y
    return None


def _logistic_impairment(year: int, crossover_year: int, slope: float = 0.20) -> float:
    """
    Logistic stranding curve. With slope=0.20:
      - 50% of cap impaired AT crossover year
      - ~5% of cap impaired at crossover - 15 years
      - ~95% of cap impaired at crossover + 15 years
    Reflects ~25y typical fossil-asset response time once challenger reaches cost parity.
    """
    if crossover_year is None:
        return 0.0
    z = slope * (year - crossover_year)
    return 1.0 / (1.0 + exp(-z))


def compute_stranding(
    asset_id: str,
    sector: str,
    replacement_value: float,
    scenario_id: str,
    years: List[int],
) -> StrandingResult:
    """
    Compute stranded-asset impairment trajectory + revenue index for one asset × scenario.
    """
    tax = load_sector_taxonomy()["sectors"]
    sec_meta = tax.get(sector, tax["services"])
    incumbent = sec_meta.get("primary_technology")
    challenger = sec_meta.get("challenger_technology")
    fossil_dependent = bool(sec_meta.get("fossil_dependent", False))

    horizon = (min(years), max(years)) if years else (2025, 2050)
    crossover = find_crossover_year(incumbent, challenger, scenario_id, horizon=horizon) if challenger else None

    pathways = load_sector_pathways()["sectors"]
    pathway = pathways.get(sector, pathways.get("services", {}))
    scen = map_scenario_to_ngfs(scenario_id)
    pathway_curve = pathway.get(scen, pathway.get("ndcs_only", {}))

    # Secondary trigger: demand-driven stranding. If no cost crossover but the
    # sector pathway falls below 0.5 within horizon, set crossover at the year
    # the pathway crosses 0.5. Captures stranding from demand collapse alone
    # (e.g., refineries when oil demand falls, regardless of biorefining cost).
    if crossover is None and fossil_dependent:
        for y in range(horizon[0], horizon[1] + 1):
            if _interp_pathway(pathway_curve, y) < 0.5:
                crossover = y
                break

    # Cap on impairment scales with scenario-specific sector demand collapse.
    # Maximum stranding share = max(0, 1 - pathway_at_2050).
    # Asset-side base: full replacement value for fossil-dependent sectors;
    # half for non-fossil (only the share tied to incumbent tech can strand).
    base = replacement_value if fossil_dependent else replacement_value * 0.5
    horizon_end = max(years) if years else 2050
    pathway_end = _interp_pathway(pathway_curve, horizon_end)
    cap = max(0.0, 1.0 - pathway_end) * base

    annual_impairment: Dict[int, float] = {}
    rev_index: Dict[int, float] = {}
    for y in years:
        if crossover is not None:
            # Year-over-year incremental impairment. Always use the prior year's
            # logistic value (not zero) at the start of the horizon, so we don't
            # dump pre-horizon stranding into year 1.
            frac = _logistic_impairment(y, crossover)
            prev_frac = _logistic_impairment(y - 1, crossover)
            incremental = max(0.0, frac - prev_frac)
            annual_impairment[y] = round(incremental * cap, 2)
        else:
            annual_impairment[y] = 0.0
        # Sector pathway revenue index
        rev_index[y] = _interp_pathway(pathway_curve, y)

    stranded_2050 = _logistic_impairment(2050, crossover) * cap if crossover else 0.0

    return StrandingResult(
        asset_id=asset_id,
        sector=sector,
        scenario_id=scenario_id,
        incumbent_tech=incumbent or "",
        challenger_tech=challenger,
        crossover_year=crossover,
        stranded_fraction_2050=round(stranded_2050 / max(replacement_value, 1.0), 4),
        annual_impairment_usd=annual_impairment,
        revenue_index=rev_index,
        notes=(
            "Wright's Law projection (Way et al. 2022); Lafond bands; "
            "fossil_dependent=" + str(fossil_dependent)
        ),
    )


def _interp_pathway(curve: Dict[str, float], year: int) -> float:
    if not curve:
        return 1.0
    years = sorted(int(y) for y in curve.keys())
    if year <= years[0]:
        return float(curve[str(years[0])])
    if year >= years[-1]:
        return float(curve[str(years[-1])])
    for i in range(len(years) - 1):
        y0, y1 = years[i], years[i + 1]
        if y0 <= year <= y1:
            v0 = float(curve[str(y0)])
            v1 = float(curve[str(y1)])
            return v0 + (year - y0) / (y1 - y0) * (v1 - v0)
    return 1.0


def revenue_erosion_usd(
    annual_revenue: float,
    revenue_index: Dict[int, float],
) -> Dict[int, float]:
    """
    Convert sector pathway index into year-over-year revenue erosion (USD).
    Positive value means revenue lost relative to 2025 baseline.
    """
    out: Dict[int, float] = {}
    for y, idx in revenue_index.items():
        out[y] = round(max(0.0, annual_revenue * (1.0 - idx)), 2)
    return out
