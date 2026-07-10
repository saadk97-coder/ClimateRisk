"""
Portfolio climate-alignment metrics: financed emissions (PCAF-style), Implied
Temperature Rise (ITR), and technology/pathway alignment (PACTA-style).

Screening-grade. Attribution follows PCAF: the reporting entity is attributed a
share of each asset's absolute emissions and transition cost. ITR compares each
asset's (abated) Scope 1+2 pathway to a 1.5°C-consistent linear-to-net-zero budget;
pathway alignment compares the asset's decline to the scenario's sector pathway.

References
----------
- PCAF (2022). The Global GHG Accounting and Reporting Standard for the Financial
  Industry (2nd ed.) — attribution & financed emissions.
- SBTi (2023). Financial Sector / Temperature Scoring — ITR framing.
- 2 Degrees Investing Initiative — PACTA — technology-pathway alignment.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional

from engine.transition.carbon_pricing import abatement_index
from engine.transition.data_loader import (
    load_sector_pathways, load_sector_taxonomy, map_scenario_to_ngfs,
)

BUDGET_START = 2025
BUDGET_END = 2050


# ---------------------------------------------------------------------------
# Financed / attributed emissions (PCAF)
# ---------------------------------------------------------------------------
@dataclass
class FinancedEmissions:
    scope1: float
    scope2: float
    scope3: float
    total_s1_s2: float
    total_s1_s2_s3: float
    per_asset: List[dict]


def financed_emissions(assets: List, attribution: Optional[Dict[str, float]] = None) -> FinancedEmissions:
    """Attributed absolute emissions. attribution maps asset_id → share in [0,1]
    (default 1.0 = 100% owned)."""
    attribution = attribution or {}
    s1 = s2 = s3 = 0.0
    per = []
    for a in assets:
        f = max(0.0, min(1.0, attribution.get(a.id, 1.0)))
        a1 = a.scope1_emissions_tco2 * f
        a2 = a.scope2_emissions_tco2 * f
        a3 = a.scope3_emissions_tco2 * f
        s1 += a1; s2 += a2; s3 += a3
        per.append({"asset_id": a.id, "attribution": f,
                    "scope1": a1, "scope2": a2, "scope3": a3, "scope1_2": a1 + a2})
    return FinancedEmissions(s1, s2, s3, s1 + s2, s1 + s2 + s3, per)


# ---------------------------------------------------------------------------
# Implied Temperature Rise (ITR)
# ---------------------------------------------------------------------------
def _asset_s12_path(asset, years: List[int]) -> Dict[int, float]:
    idx = abatement_index(getattr(asset, "decarb_target_year", 0),
                          getattr(asset, "decarb_residual_pct", 0.0), years)
    e0 = asset.scope1_emissions_tco2 + asset.scope2_emissions_tco2
    return {y: e0 * idx[y] for y in years}


def implied_temperature_rise(
    assets: List, attribution: Optional[Dict[str, float]] = None,
    years: Optional[List[int]] = None, base_temp: float = 1.5, beta: float = 1.2,
) -> dict:
    """Emissions-weighted portfolio ITR and per-asset ITR.

    Each asset's 1.5°C budget is the area under a straight line from today's Scope
    1+2 to zero by BUDGET_END. ITR = base_temp + beta × (cumulative_actual/budget − 1),
    clamped to [1.2, 4.0]. An asset on a net-zero-by-2050 path scores ~base_temp;
    flat emissions score materially hotter.
    """
    years = years or list(range(BUDGET_START, BUDGET_END + 1))
    attribution = attribution or {}
    span = years[-1] - years[0]
    total_w = 0.0
    weighted = 0.0
    per = []
    for a in assets:
        e0 = a.scope1_emissions_tco2 + a.scope2_emissions_tco2
        if e0 <= 0:
            continue
        actual = sum(_asset_s12_path(a, years).values())
        budget = 0.5 * e0 * span  # triangle: e0 → 0 over the horizon
        ratio = (actual / budget - 1.0) if budget > 0 else 0.0
        itr = min(4.0, max(1.2, base_temp + beta * ratio))
        f = max(0.0, min(1.0, attribution.get(a.id, 1.0)))
        w = e0 * f
        weighted += itr * w
        total_w += w
        per.append({"asset_id": a.id, "itr": round(itr, 2),
                    "target_year": getattr(a, "decarb_target_year", 0) or None})
    portfolio_itr = round(weighted / total_w, 2) if total_w > 0 else base_temp
    return {"portfolio_itr": portfolio_itr, "per_asset": per, "weight_basis": "Scope 1+2 × attribution"}


# ---------------------------------------------------------------------------
# Technology / pathway alignment (PACTA-style)
# ---------------------------------------------------------------------------
def _interp(curve: Dict[str, float], year: int) -> float:
    if not curve:
        return 1.0
    ys = sorted(int(y) for y in curve)
    if year <= ys[0]:
        return float(curve[str(ys[0])])
    if year >= ys[-1]:
        return float(curve[str(ys[-1])])
    for a, b in zip(ys, ys[1:]):
        if a <= year <= b:
            va, vb = float(curve[str(a)]), float(curve[str(b)])
            return va + (year - a) / (b - a) * (vb - va)
    return 1.0


def pathway_alignment(asset, scenario_id: str, years: Optional[List[int]] = None) -> dict:
    """Compare the asset's Scope 1+2 decline by BUDGET_END against the scenario's
    sector demand pathway (the alignment benchmark). Returns a status + the gap."""
    years = years or list(range(BUDGET_START, BUDGET_END + 1))
    tax = load_sector_taxonomy()["sectors"]
    meta = tax.get(asset.sector, tax.get("services", {}))
    pathways = load_sector_pathways()["sectors"]
    curve = pathways.get(asset.sector, {}).get(map_scenario_to_ngfs(scenario_id), {})
    idx = abatement_index(getattr(asset, "decarb_target_year", 0),
                          getattr(asset, "decarb_residual_pct", 0.0), years)
    asset_2050 = idx[years[-1]]
    bench_2050 = _interp(curve, years[-1])
    gap = asset_2050 - bench_2050
    if gap <= 0.05:
        status = "aligned"
    elif gap <= 0.25:
        status = "lagging"
    else:
        status = "misaligned"
    return {"asset_id": asset.id, "sector": asset.sector,
            "fossil_dependent": bool(meta.get("fossil_dependent")),
            "asset_2050_index": round(asset_2050, 3),
            "benchmark_2050_index": round(bench_2050, 3),
            "gap": round(gap, 3), "status": status}
