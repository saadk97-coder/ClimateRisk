"""
Marginal Abatement Cost Curves (MACC) — the "decarbonise vs pay the carbon price"
decision. Given a sector's abatement measures (cost USD/tCO₂ and potential as a share
of Scope 1+2 emissions) and a carbon price, computes the cost-effective abatement
(measures cheaper than the price), the abatement spend, the carbon cost avoided, and
the net benefit.

Screening-grade. Curves are informed by IPCC AR6 WG3 sectoral mitigation potential/cost.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional
import json
import os

_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "transition"))


@lru_cache(maxsize=1)
def load_macc() -> dict:
    with open(os.path.join(_DIR, "macc.json"), encoding="utf-8") as f:
        return json.load(f)


def sector_curve(sector: str) -> List[dict]:
    d = load_macc()
    return d["sectors"].get(sector, d["default_unmatched"])


@dataclass
class MACCResult:
    sector: str
    carbon_price: float
    emissions_tco2: float
    cost_effective_frac: float        # share of emissions worth abating at this price
    abated_tco2: float
    abatement_cost_usd: float         # spend on the cost-effective measures
    carbon_cost_avoided_usd: float    # abated_tco2 × price
    net_benefit_usd: float            # avoided − cost (positive → abate beats paying)
    residual_carbon_cost_usd: float   # (1 − abated_frac) × emissions × price
    measures: List[dict] = field(default_factory=list)


def evaluate_macc(sector: str, emissions_tco2: float, carbon_price: float) -> MACCResult:
    """Cost-effective abatement for one sector at one carbon price."""
    curve = sorted(sector_curve(sector), key=lambda m: m["cost_usd_per_tco2"])
    frac = 0.0
    cost = 0.0
    chosen = []
    for m in curve:
        if m["cost_usd_per_tco2"] <= carbon_price and frac < 1.0:
            p = min(float(m["potential_frac"]), 1.0 - frac)
            frac += p
            cost += m["cost_usd_per_tco2"] * p * emissions_tco2
            chosen.append({**m, "applied_frac": round(p, 4)})
    abated = frac * emissions_tco2
    avoided = abated * carbon_price
    residual = (1.0 - frac) * emissions_tco2 * carbon_price
    return MACCResult(
        sector=sector, carbon_price=round(carbon_price, 2), emissions_tco2=emissions_tco2,
        cost_effective_frac=round(frac, 4), abated_tco2=round(abated, 1),
        abatement_cost_usd=round(cost, 2), carbon_cost_avoided_usd=round(avoided, 2),
        net_benefit_usd=round(avoided - cost, 2),
        residual_carbon_cost_usd=round(residual, 2), measures=chosen,
    )


def macc_steps(sector: str, emissions_tco2: float = 1.0) -> List[dict]:
    """Return the full step curve as cumulative (x = cumulative abated fraction/tonnes,
    cost) points for plotting a marginal abatement cost curve."""
    curve = sorted(sector_curve(sector), key=lambda m: m["cost_usd_per_tco2"])
    cum = 0.0
    steps = []
    for m in curve:
        steps.append({"measure": m["measure"], "cost_usd_per_tco2": m["cost_usd_per_tco2"],
                      "from_frac": round(cum, 4), "to_frac": round(cum + m["potential_frac"], 4),
                      "from_tco2": round(cum * emissions_tco2, 1),
                      "to_tco2": round((cum + m["potential_frac"]) * emissions_tco2, 1)})
        cum += m["potential_frac"]
    return steps
