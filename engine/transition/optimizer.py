"""
Abatement investment optimizer: given a decarbonisation budget, allocate it across the
portfolio's marginal abatement measures in merit order (cheapest $/tCO₂ first) to maximise
emissions abated. No-regret (negative-cost) measures are always funded; the remaining
budget buys the next-cheapest measures until exhausted.

Linear MACC → greedy cheapest-first is the optimal allocation for max tonnes per dollar.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from engine.transition.macc import sector_curve


@dataclass
class AbatementPlan:
    budget: float
    total_spend: float               # net spend (no-regret savings reduce it)
    abated_tco2: float
    total_emissions_tco2: float
    residual_tco2: float
    residual_carbon_cost_usd: float  # residual emissions × each asset's carbon price
    marginal_cost_frontier: float    # $/tCO₂ of the last funded measure
    line_items: List[dict] = field(default_factory=list)
    per_asset: List[dict] = field(default_factory=list)


def optimize_abatement(
    assets: List, budget_usd: float, price_by_asset: Optional[Dict[str, float]] = None,
) -> AbatementPlan:
    price_by_asset = price_by_asset or {}
    items = []
    emissions = {}
    for a in assets:
        e12 = a.scope1_emissions_tco2 + a.scope2_emissions_tco2
        if e12 <= 0:
            continue
        emissions[a.id] = e12
        for m in sector_curve(a.sector):
            tonnes = float(m["potential_frac"]) * e12
            items.append({
                "asset": a.id, "measure": m["measure"],
                "cost_per_t": float(m["cost_usd_per_tco2"]),
                "tonnes": tonnes, "total_cost": float(m["cost_usd_per_tco2"]) * tonnes,
            })

    items.sort(key=lambda x: x["cost_per_t"])   # merit order
    remaining = budget_usd
    spend = 0.0
    abated_by_asset: Dict[str, float] = {a: 0.0 for a in emissions}
    funded = []
    frontier = 0.0

    for it in items:
        c = it["total_cost"]
        if c <= 0:                      # no-regret: always fund, adds (saves) money
            funded.append({**it, "funded_frac": 1.0, "spend": c})
            abated_by_asset[it["asset"]] += it["tonnes"]
            spend += c
            frontier = it["cost_per_t"]
            continue
        if remaining <= 0:
            break
        if c <= remaining:
            funded.append({**it, "funded_frac": 1.0, "spend": c})
            remaining -= c
            spend += c
            abated_by_asset[it["asset"]] += it["tonnes"]
            frontier = it["cost_per_t"]
        else:
            frac = remaining / c
            funded.append({**it, "funded_frac": frac, "spend": remaining})
            spend += remaining
            abated_by_asset[it["asset"]] += it["tonnes"] * frac
            frontier = it["cost_per_t"]
            remaining = 0.0
            break

    total_e = sum(emissions.values())
    abated = sum(abated_by_asset.values())
    per_asset = []
    residual_cost = 0.0
    for aid, e in emissions.items():
        res = e - abated_by_asset[aid]
        price = price_by_asset.get(aid, 0.0)
        residual_cost += res * price
        per_asset.append({"asset": aid, "emissions": e, "abated": abated_by_asset[aid],
                          "residual": res, "abated_pct": abated_by_asset[aid] / e if e else 0.0})

    return AbatementPlan(
        budget=budget_usd, total_spend=round(spend, 2), abated_tco2=round(abated, 1),
        total_emissions_tco2=round(total_e, 1), residual_tco2=round(total_e - abated, 1),
        residual_carbon_cost_usd=round(residual_cost, 2),
        marginal_cost_frontier=round(frontier, 2),
        line_items=funded, per_asset=per_asset,
    )
