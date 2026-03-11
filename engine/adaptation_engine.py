"""
Adaptation measures engine: NPV of avoided EAD, cost-benefit ratio, payback period.
"""

import json
import os
import numpy as np
from typing import List, Dict, Optional
from dataclasses import dataclass

_CATALOG: Optional[dict] = None


def _load_catalog() -> dict:
    global _CATALOG
    if _CATALOG is None:
        path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "data", "adaptation_catalog.json")
        )
        with open(path) as f:
            _CATALOG = json.load(f)
    return _CATALOG


def list_measures(hazard: Optional[str] = None, asset_type: Optional[str] = None) -> List[dict]:
    """Return adaptation measures, optionally filtered by hazard and/or asset_type."""
    catalog = _load_catalog()
    measures = catalog["measures"]
    if hazard:
        measures = [m for m in measures if m["hazard"] == hazard]
    if asset_type:
        measures = [
            m for m in measures
            if not m.get("applicable_asset_types") or asset_type in m["applicable_asset_types"]
        ]
    return measures


def get_measure(measure_id: str) -> Optional[dict]:
    catalog = _load_catalog()
    for m in catalog["measures"]:
        if m["id"] == measure_id:
            return m
    return None


@dataclass
class AdaptationResult:
    measure_id: str
    measure_label: str
    hazard: str
    asset_id: str
    asset_value: float
    capex: float
    npv_opex: float
    total_cost: float
    baseline_ead: float
    adapted_ead: float
    avoided_ead_annual: float
    npv_benefits: float
    cbr: float              # cost-benefit ratio = npv_benefits / total_cost
    payback_years: float
    design_life_years: int
    damage_reduction_pct: float


def calc_adaptation(
    measure_id: str,
    asset_id: str,
    asset_value: float,
    baseline_ead: float,
    discount_rate: float = 0.035,
) -> AdaptationResult:
    """
    Calculate NPV cost-benefit for an adaptation measure on an asset.

    Parameters
    ----------
    measure_id      : ID from adaptation catalog
    asset_id        : asset identifier
    asset_value     : replacement value £/$/€
    baseline_ead    : current/future EAD without adaptation
    discount_rate   : annual discount rate (default 3.5% green finance rate)
    """
    measure = get_measure(measure_id)
    if measure is None:
        raise ValueError(f"Unknown measure: {measure_id}")

    design_life = measure["design_life_years"]
    reduction_pct = measure["damage_reduction_pct"] / 100.0

    capex = asset_value * measure["capex_pct"] / 100.0
    opex_annual = capex * measure["opex_annual_pct"] / 100.0

    avoided_ead = baseline_ead * reduction_pct
    adapted_ead = baseline_ead - avoided_ead

    # NPV of benefits and opex over design life
    years = np.arange(1, design_life + 1)
    discount_factors = 1.0 / (1.0 + discount_rate) ** years

    npv_benefits = float(np.sum(avoided_ead * discount_factors))
    npv_opex = float(np.sum(opex_annual * discount_factors))
    total_cost = capex + npv_opex

    cbr = npv_benefits / total_cost if total_cost > 0 else 0.0
    payback_years = capex / avoided_ead if avoided_ead > 0 else float("inf")

    return AdaptationResult(
        measure_id=measure_id,
        measure_label=measure["label"],
        hazard=measure["hazard"],
        asset_id=asset_id,
        asset_value=asset_value,
        capex=capex,
        npv_opex=npv_opex,
        total_cost=total_cost,
        baseline_ead=baseline_ead,
        adapted_ead=adapted_ead,
        avoided_ead_annual=avoided_ead,
        npv_benefits=npv_benefits,
        cbr=cbr,
        payback_years=payback_years,
        design_life_years=design_life,
        damage_reduction_pct=measure["damage_reduction_pct"],
    )


@dataclass
class AdaptationNPVResult:
    """NPV-based adaptation result using the full annual damage stream."""
    measure_id: str
    measure_label: str
    hazard: str
    asset_id: str
    asset_value: float
    # Costs
    capex_total: float
    npv_opex: float
    total_cost: float
    # Benefits (NPV of avoided damages over the full annual stream)
    npv_baseline_damages: float
    npv_adapted_damages: float
    npv_avoided_damages: float
    # Metrics
    cbr: float
    roi_pct: float
    irr: float
    discounted_payback_year: Optional[int]
    design_life_years: int
    damage_reduction_pct: float
    # Year-by-year cash flow table
    annual_cashflows: list   # list of dicts with year-level detail

    @property
    def net_npv(self) -> float:
        return self.npv_avoided_damages - self.total_cost


def calc_adaptation_npv(
    measure_id: str,
    asset_id: str,
    asset_value: float,
    annual_eads: Dict[int, float],
    discount_rate: float = 0.035,
    implementation_year: int = 2026,
    capex_phases: Optional[Dict[int, float]] = None,
    opex_override: Optional[float] = None,
    base_year: int = 2025,
) -> AdaptationNPVResult:
    """
    NPV-based adaptation CBA using the full annual EAD stream (2025-2050).

    Parameters
    ----------
    measure_id          : ID from adaptation catalog
    asset_id            : asset identifier
    asset_value         : replacement value
    annual_eads         : {year: ead} — baseline annual EAD from damage model
    discount_rate       : annual discount rate
    implementation_year : year the measure becomes effective
    capex_phases        : optional {year: fraction} for phased capex (fractions sum to 1.0)
                          e.g. {2026: 0.6, 2027: 0.4} for 60/40 split
    opex_override       : override annual opex amount (absolute); if None uses catalog %
    base_year           : PV reference year
    """
    measure = get_measure(measure_id)
    if measure is None:
        raise ValueError(f"Unknown measure: {measure_id}")

    design_life = measure["design_life_years"]
    reduction_pct = measure["damage_reduction_pct"] / 100.0

    capex_total = asset_value * measure["capex_pct"] / 100.0
    opex_annual = opex_override if opex_override is not None else capex_total * measure["opex_annual_pct"] / 100.0

    # Default phasing: 100% in year before implementation
    if capex_phases is None:
        capex_phases = {implementation_year - 1: 1.0}

    # Normalise phases to sum to 1.0
    phase_total = sum(capex_phases.values())
    if phase_total > 0:
        capex_phases = {y: v / phase_total for y, v in capex_phases.items()}

    years_sorted = sorted(annual_eads.keys())
    end_of_life_year = implementation_year + design_life - 1

    rows = []
    cum_net_cf_pv = 0.0
    discounted_payback = None
    npv_baseline = 0.0
    npv_adapted = 0.0
    npv_avoided = 0.0
    npv_cost = 0.0
    irr_cashflows = []  # for IRR: net cash flows per year

    for year in years_sorted:
        t = year - base_year
        df = 1.0 / (1.0 + discount_rate) ** t if t >= 0 else 1.0

        baseline_ead = annual_eads.get(year, 0.0)
        measure_active = implementation_year <= year <= end_of_life_year

        # Avoided damage
        avoided = baseline_ead * reduction_pct if measure_active else 0.0
        adapted_ead = baseline_ead - avoided

        # Capex in this year
        capex_yr = capex_total * capex_phases.get(year, 0.0)

        # Opex in this year
        opex_yr = opex_annual if measure_active else 0.0

        # Net cash flow = avoided damage - costs
        net_cf = avoided - capex_yr - opex_yr
        net_cf_pv = net_cf * df

        cum_net_cf_pv += net_cf_pv

        # Track discounted payback
        if discounted_payback is None and cum_net_cf_pv > 0 and measure_active:
            discounted_payback = year

        npv_baseline += baseline_ead * df
        npv_adapted += adapted_ead * df
        npv_avoided += avoided * df
        npv_cost += (capex_yr + opex_yr) * df
        irr_cashflows.append(net_cf)

        rows.append({
            "year": year,
            "baseline_ead": round(baseline_ead, 2),
            "measure_active": measure_active,
            "avoided_damage": round(avoided, 2),
            "adapted_ead": round(adapted_ead, 2),
            "capex": round(capex_yr, 2),
            "opex": round(opex_yr, 2),
            "net_cashflow": round(net_cf, 2),
            "discount_factor": round(df, 6),
            "net_cashflow_pv": round(net_cf_pv, 2),
            "cumulative_npv": round(cum_net_cf_pv, 2),
        })

    total_cost = npv_cost
    cbr = npv_avoided / total_cost if total_cost > 0 else 0.0
    roi_pct = (npv_avoided - total_cost) / total_cost * 100 if total_cost > 0 else 0.0

    # IRR via numpy
    try:
        irr = float(np.irr(irr_cashflows)) if hasattr(np, "irr") else _calc_irr(irr_cashflows)
    except Exception:
        irr = float("nan")

    return AdaptationNPVResult(
        measure_id=measure_id,
        measure_label=measure["label"],
        hazard=measure["hazard"],
        asset_id=asset_id,
        asset_value=asset_value,
        capex_total=capex_total,
        npv_opex=npv_cost - sum(capex_total * capex_phases.get(y, 0.0) * (1.0 / (1.0 + discount_rate) ** (y - base_year)) for y in years_sorted),
        total_cost=total_cost,
        npv_baseline_damages=npv_baseline,
        npv_adapted_damages=npv_adapted,
        npv_avoided_damages=npv_avoided,
        cbr=cbr,
        roi_pct=roi_pct,
        irr=irr,
        discounted_payback_year=discounted_payback,
        design_life_years=design_life,
        damage_reduction_pct=measure["damage_reduction_pct"],
        annual_cashflows=rows,
    )


def _calc_irr(cashflows: list, tol: float = 1e-6, max_iter: int = 200) -> float:
    """Newton-Raphson IRR solver (np.irr was removed in NumPy 1.20)."""
    cf = np.array(cashflows, dtype=float)
    if len(cf) < 2 or np.all(cf == 0):
        return float("nan")
    # Try multiple initial guesses to handle different cash flow profiles
    for r0 in [0.1, 0.0, -0.05, 0.5]:
        r = r0
        converged = False
        for _ in range(max_iter):
            t = np.arange(len(cf))
            try:
                pv = cf / (1 + r) ** t
            except (ZeroDivisionError, FloatingPointError):
                break
            npv = pv.sum()
            dpv = -(t * cf / (1 + r) ** (t + 1)).sum()
            if abs(dpv) < 1e-14:
                break
            r_new = r - npv / dpv
            if abs(r_new - r) < tol:
                converged = True
                r = r_new
                break
            r = r_new
        if converged:
            return r
    return float("nan")


def portfolio_adaptation_frontier(
    adaptation_results: List[AdaptationResult],
) -> List[dict]:
    """
    Build a cost-vs-risk-reduction frontier for portfolio-level adaptation.
    Sorts measures by CBR descending, computes cumulative cost and risk reduction.
    """
    sorted_results = sorted(adaptation_results, key=lambda r: r.cbr, reverse=True)
    cumulative_cost = 0.0
    cumulative_avoided_ead = 0.0
    frontier = []
    for r in sorted_results:
        cumulative_cost += r.capex
        cumulative_avoided_ead += r.avoided_ead_annual
        frontier.append({
            "measure_id": r.measure_id,
            "measure_label": r.measure_label,
            "asset_id": r.asset_id,
            "capex": r.capex,
            "cbr": r.cbr,
            "cumulative_capex": cumulative_cost,
            "cumulative_avoided_ead_annual": cumulative_avoided_ead,
        })
    return frontier


def portfolio_adaptation_frontier_npv(
    adaptation_results: List[AdaptationNPVResult],
) -> List[dict]:
    """
    NPV-based portfolio frontier. Sorts by CBR descending.
    """
    sorted_results = sorted(adaptation_results, key=lambda r: r.cbr, reverse=True)
    cumulative_cost = 0.0
    cumulative_npv_avoided = 0.0
    frontier = []
    for r in sorted_results:
        cumulative_cost += r.capex_total
        cumulative_npv_avoided += r.npv_avoided_damages
        frontier.append({
            "measure_id": r.measure_id,
            "measure_label": r.measure_label,
            "asset_id": r.asset_id,
            "capex": r.capex_total,
            "cbr": r.cbr,
            "roi_pct": r.roi_pct,
            "npv_avoided": r.npv_avoided_damages,
            "net_npv": r.net_npv,
            "cumulative_capex": cumulative_cost,
            "cumulative_npv_avoided": cumulative_npv_avoided,
        })
    return frontier
