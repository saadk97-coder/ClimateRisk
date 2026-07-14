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

# Fix #3 — fraction of an incumbent asset that is the carbon-specific technology and is
# written off on a full tech switch (e.g. blast furnace + coke ovens ≈ 45% of an integrated
# steelworks; the rolling/finishing/logistics is reused). Scaled by the firm's ambition.
TECH_SUBSTITUTION_SHARE = 0.45


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
    stranded_fraction_2050: float    # RECOGNISED cumulative impairment 2025–50 ÷ replacement value
    annual_impairment_usd: Dict[int, float]  # {year: impairment in USD}
    revenue_index: Dict[int, float]  # {year: revenue multiplier (sector_pathways)}
    crossover_year_early: Optional[int] = None   # R6 — Lafond-band earliest crossover
    crossover_year_late: Optional[int] = None    # R6 — Lafond-band latest crossover
    stranding_slope: float = 0.20                # R7 — logistic slope actually used
    strandable_ceiling_frac: float = 0.0         # cap ÷ replacement value (max that COULD strand)
    notes: str = ""


def _sector_stranding_slope(sector: str) -> float:
    """R7 — per-sector logistic stranding slope (default 0.20 if unset)."""
    tax = load_sector_taxonomy()["sectors"]
    meta = tax.get(sector, {})
    try:
        return float(meta.get("stranding_slope", 0.20))
    except (TypeError, ValueError):
        return 0.20


def _tech_carbon_adder(tech: str, scenario_id: str, year: int, region_iso3: str,
                       price_scale: float = 1.0) -> float:
    """
    P6 — carbon cost per functional unit for a technology, in the same unit as its
    cost_2025 field: carbon_price(scenario, region, year) × carbon_ef_per_unit.
    Returns 0.0 when the tech has no emission factor (non-fossil / no clean pairing).
    """
    lc = load_learning_curves()["technologies"]
    ef = float(lc.get(tech, {}).get("carbon_ef_per_unit", 0.0) or 0.0)
    if ef <= 0:
        return 0.0
    # Imported lazily to avoid a circular import at module load.
    from engine.transition.carbon_pricing import get_carbon_price
    from engine.transition.data_loader import get_ngfs_region
    price = get_carbon_price(scenario_id, year, get_ngfs_region(region_iso3)) * max(0.0, price_scale)
    return ef * price


def _regional_cost_factor(tech: str, region_iso3: Optional[str]) -> float:
    """
    Geographic resource/cost multiplier on a technology's LCOE (region_factors.json).
    Clean power scales with the zone's renewable factor, green-H2-linked commodities with
    the green-H2 factor, fossil generation/fuel with the fossil factor. A watt in Texas or
    MENA is cheaper than in N. Europe or Japan, so crossover (and stranding) happen earlier
    there. region_iso3 None → 1.0 (global average, preserves the world-average anchors).
    """
    if not region_iso3:
        return 1.0
    from engine.transition.data_loader import load_region_factors, resource_zone
    rf = load_region_factors()
    zone = resource_zone(region_iso3)   # sub-national (USA-TX) → country → global
    zdata = rf["zones"].get(zone, {})
    tmap = rf["tech_factor_map"]
    for key in ("renewable_lcoe_factor", "green_h2_factor", "fossil_lcoe_factor"):
        if tech in tmap.get(key, []):
            return float(zdata.get(key, 1.0))
    return 1.0


def _project_cost(tech: str, scenario_id: str, year: int,
                  region_iso3: Optional[str] = None) -> Optional[TechnologyProjection]:
    """Project a technology's unit cost to `year` using Wright's Law + Lafond bands,
    scaled by the geographic resource/cost factor for `region_iso3` (None = global)."""
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

    # Find base cost field — first key starting with "cost_2025", scaled by the
    # geographic resource/cost factor for this region (Texas/MENA cheaper than N. Europe).
    cost_2025 = next((float(v) for k, v in t.items() if k.startswith("cost_2025")), 0.0)
    if cost_2025 <= 0:
        return None
    cost_2025 = cost_2025 * _regional_cost_factor(tech, region_iso3)
    pred = cost_2025 * (q_ratio ** b) if lr > 0 else cost_2025 * (1.0 + g * 0.0)
    # If LR=0, no cost change; if Q grows but LR=0, costs stay flat.

    # Farmer–Lafond log-normal band (1-σ): sigma_t = sigma * sqrt(years_ahead)
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


def project_technology(tech: str, scenario_id: str, years: List[int],
                       region_iso3: Optional[str] = None) -> List[TechnologyProjection]:
    """Project a single technology's cost across years (region-aware LCOE)."""
    out: List[TechnologyProjection] = []
    for y in years:
        proj = _project_cost(tech, scenario_id, y, region_iso3=region_iso3)
        if proj:
            out.append(proj)
    return out


def find_crossover_year(
    incumbent: str,
    challenger: str,
    scenario_id: str,
    horizon: Tuple[int, int] = (2025, 2050),
    carbon_inclusive: bool = False,
    region_iso3: str = "USA",
    price_scale: float = 1.0,
    band: str = "median",
) -> Optional[int]:
    """
    Return the first year in [start, end] when challenger <= incumbent cost.
    None if no crossover within horizon. If challenger is already below at start,
    returns the start year.

    carbon_inclusive : P6 — when True, add the incumbent's carbon cost
        (carbon_price × emission factor, same functional unit) to its effective
        cost, so a rising carbon price pulls the crossover earlier. Default False
        keeps the pure-LCOE behaviour and the worked-example anchors.
    band : R6 — "median" (default) compares central projections; "early"
        compares challenger low-band vs incumbent high-band (earliest plausible
        crossover); "late" compares challenger high-band vs incumbent low-band
        (latest plausible crossover).
    """
    if not (incumbent and challenger):
        return None
    start, end = horizon
    for y in range(start, end + 1):
        ci = _project_cost(incumbent, scenario_id, y, region_iso3=region_iso3)
        cc = _project_cost(challenger, scenario_id, y, region_iso3=region_iso3)
        if ci is None or cc is None:
            return None
        # Compare projected_cost directly assuming the taxonomy pairs
        # technologies with comparable functional units.
        if band == "early":
            inc, chal = ci.cost_hi, cc.cost_lo
        elif band == "late":
            inc, chal = ci.cost_lo, cc.cost_hi
        else:
            inc, chal = ci.projected_cost, cc.projected_cost
        if carbon_inclusive:
            inc = inc + _tech_carbon_adder(incumbent, scenario_id, y, region_iso3, price_scale)
        if chal <= inc:
            return y
    return None


def _logistic_impairment(year: int, crossover_year: int, slope: float = 0.20) -> float:
    """
    Logistic stranding curve. With slope=0.20:
      - 50% of cap impaired AT crossover year
      - ~5% of cap impaired at crossover - 15 years
      - ~95% of cap impaired at crossover + 15 years
    Reflects ~25y typical fossil-asset response time once challenger reaches cost parity.
    R7 — slope is per-sector (see _sector_stranding_slope); a steeper slope
    strands the asset faster once crossover triggers.
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
    non_fossil_base_fraction: float = 0.5,
    slope: Optional[float] = None,
    carbon_inclusive_crossover: bool = False,
    region_iso3: str = "USA",
    price_scale: float = 1.0,
    incumbent_share: float = 1.0,
    ambition: float = 0.0,
) -> StrandingResult:
    """
    Compute stranded-asset impairment trajectory + revenue index for one asset × scenario.

    non_fossil_base_fraction : R1 — share of replacement value exposed to stranding
        for NON-fossil-dependent sectors (only the portion tied to the incumbent
        technology can strand). Default 0.5 preserves the calibrated anchors.
    slope : R7 — logistic stranding slope; None uses the per-sector value.
    carbon_inclusive_crossover : P6 — include the incumbent's carbon cost when
        finding the cost crossover year (opt-in; default off).
    """
    tax = load_sector_taxonomy()["sectors"]
    sec_meta = tax.get(sector, tax["services"])
    incumbent = sec_meta.get("primary_technology")
    challenger = sec_meta.get("challenger_technology")
    fossil_dependent = bool(sec_meta.get("fossil_dependent", False))
    slope = _sector_stranding_slope(sector) if slope is None else float(slope)

    horizon = (min(years), max(years)) if years else (2025, 2050)
    _xkw = dict(carbon_inclusive=carbon_inclusive_crossover,
                region_iso3=region_iso3, price_scale=price_scale)
    crossover = (find_crossover_year(incumbent, challenger, scenario_id, horizon=horizon, **_xkw)
                 if challenger else None)
    cost_crossover = crossover   # the pure COST crossover, before any demand-trigger fallback
    # R6 — Lafond-band crossover range (earliest / latest plausible cost parity).
    crossover_early = (find_crossover_year(incumbent, challenger, scenario_id, horizon=horizon,
                                           band="early", **_xkw) if challenger else None)
    crossover_late = (find_crossover_year(incumbent, challenger, scenario_id, horizon=horizon,
                                          band="late", **_xkw) if challenger else None)

    pathways = load_sector_pathways()["sectors"]
    pathway = pathways.get(sector, pathways.get("services", {}))
    scen = map_scenario_to_ngfs(scenario_id)
    pathway_curve = pathway.get(scen, pathway.get("ndcs_only", {}))

    # Secondary trigger: demand-driven stranding. If no cost crossover but the
    # sector pathway falls below 0.5 within horizon, set crossover at the year
    # the pathway crosses 0.5. Captures stranding from demand collapse alone
    # (e.g., refineries when oil demand falls, regardless of biorefining cost).
    _demand_trigger = None
    if fossil_dependent:
        for y in range(horizon[0], horizon[1] + 1):
            if _interp_pathway(pathway_curve, y) < 0.5:
                _demand_trigger = y
                break
    if crossover is None:
        crossover = _demand_trigger
    # R6 — a demand-collapse trigger has no Lafond cost band; fall back to the
    # central trigger for the early/late bounds so the range is never emptier
    # than the point estimate.
    crossover_early = crossover_early or crossover
    crossover_late = crossover_late or crossover

    # Cap on impairment scales with scenario-specific sector demand collapse.
    # Maximum stranding share = max(0, 1 - pathway_at_2050).
    # Asset-side base: full replacement value for fossil-dependent sectors;
    # half for non-fossil (only the share tied to incumbent tech can strand).
    nf_frac = min(1.0, max(0.0, non_fossil_base_fraction))
    base = replacement_value if fossil_dependent else replacement_value * nf_frac
    # Adaptive capacity: a firm already partly transitioned has less incumbent base to
    # strand. incumbent_share = 1 − already_transitioned (1.0 = frozen, no adaptation).
    base = base * max(0.0, min(1.0, incumbent_share))
    horizon_end = max(years) if years else 2050
    pathway_end = _interp_pathway(pathway_curve, horizon_end)
    demand_cap_frac = max(0.0, 1.0 - pathway_end)
    # Fix #3 — TECH-SUBSTITUTION stranding. Even where DEMAND holds (steel, cement), a cost
    # crossover means the incumbent asset (blast furnace, wet kiln) is replaced by the
    # challenger and written off. The carbon-specific portion of the asset (≈ TECH_SUB_SHARE)
    # strands to the extent the firm actually transitions (ambition). Reported as a lens,
    # separate from cash flow; paired with the transition capex that builds the replacement.
    tech_cap_frac = (TECH_SUBSTITUTION_SHARE * max(0.0, min(1.0, ambition))
                     if (cost_crossover is not None and challenger) else 0.0)
    cap = max(demand_cap_frac, tech_cap_frac) * base

    annual_impairment: Dict[int, float] = {}
    rev_index: Dict[int, float] = {}
    for y in years:
        if crossover is not None:
            # Year-over-year incremental impairment. Always use the prior year's
            # logistic value (not zero) at the start of the horizon, so we don't
            # dump pre-horizon stranding into year 1.
            frac = _logistic_impairment(y, crossover, slope)
            prev_frac = _logistic_impairment(y - 1, crossover, slope)
            incremental = max(0.0, frac - prev_frac)
            annual_impairment[y] = round(incremental * cap, 2)
        else:
            annual_impairment[y] = 0.0
        # Sector pathway revenue index
        rev_index[y] = _interp_pathway(pathway_curve, y)

    # % stranded MUST equal the dollars actually recognised (reviewer finding 1):
    # report the recognised cumulative impairment over the horizon ÷ replacement
    # value, NOT the logistic level at 2050 (which includes pre-2025 stranding that
    # is never booked). The strandable *ceiling* (cap ÷ value) is reported alongside
    # as the theoretical maximum, clearly distinct from what is recognised.
    recognised_cum = sum(annual_impairment.values())
    stranded_fraction = recognised_cum / max(replacement_value, 1.0)
    ceiling_frac = cap / max(replacement_value, 1.0)

    return StrandingResult(
        asset_id=asset_id,
        sector=sector,
        scenario_id=scenario_id,
        incumbent_tech=incumbent or "",
        challenger_tech=challenger,
        crossover_year=crossover,
        stranded_fraction_2050=round(stranded_fraction, 4),
        annual_impairment_usd=annual_impairment,
        revenue_index=rev_index,
        crossover_year_early=crossover_early,
        crossover_year_late=crossover_late,
        stranding_slope=slope,
        strandable_ceiling_frac=round(ceiling_frac, 4),
        notes=(
            "Wright's Law projection (Way et al. 2022); Lafond bands; "
            f"slope={slope:g}; carbon_inclusive={carbon_inclusive_crossover}; "
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
