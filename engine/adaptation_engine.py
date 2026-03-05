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
