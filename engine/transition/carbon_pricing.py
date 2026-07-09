"""
Layer 1 — Direct carbon cost with sector-level pass-through.

Methodology
-----------
For each (scenario, region, year, sector):

  gross_carbon_cost  = (scope1 + scope2) * carbon_price
  absorbed_cost      = gross_carbon_cost * (1 - pass_through)         # margin compression
  passed_through     = gross_carbon_cost * pass_through               # price increase to customers
  scope3_indirect    = scope3 * carbon_price * (1 - pass_through)     # upstream-incurred share

Net carbon OpEx adjustment to the firm = absorbed_cost (Scope 1+2) plus a
share of Scope 3 that the firm cannot push downstream. The passed-through
share flows into Layer 3 (network propagation) as a sectoral price shock.

Sources
-------
- Sijm et al. (2012) — power sector pass-through 60–100%.
- Fabra & Reguant (2014) — empirical merit-order test.
- Cludius et al. (2020) — German power market pass-through.
- Frankovic (2022) — multi-region production network with carbon shock.
- Devulder & Lisack (2020) — carbon tax in production network (BdF WP 813).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging

from engine.transition.data_loader import (
    load_carbon_prices,
    load_sector_pass_through,
    get_ngfs_region,
    map_scenario_to_ngfs,
)

_log = logging.getLogger(__name__)


@dataclass
class CarbonCostResult:
    asset_id: str
    sector: str
    scenario_id: str
    year: int
    region: str
    ngfs_region: str
    carbon_price_usd_per_t: float
    pass_through: float
    scope1_emissions_tco2: float
    scope2_emissions_tco2: float
    scope3_emissions_tco2: float
    gross_cost_usd: float          # full carbon cost on Scope 1+2
    absorbed_cost_usd: float       # margin compression on the firm
    passed_through_usd: float      # cost passed to customers (becomes Layer-3 shock)
    scope3_indirect_usd: float     # upstream Scope 3 cost not recoverable
    net_carbon_opex_usd: float     # absorbed + scope3_indirect — what hits firm CFs
    notes: str = ""


def get_carbon_price(scenario_id: str, year: int, ngfs_region: str) -> float:
    """
    Linearly interpolate the carbon price (USD/tCO2) for a given scenario × region × year.
    Held flat outside the published horizon.
    """
    cp = load_carbon_prices()
    scen_id = map_scenario_to_ngfs(scenario_id)
    scenario_data = cp["scenarios"].get(scen_id)
    if not scenario_data:
        _log.warning(f"Carbon price: no data for scenario {scenario_id}; returning 0.")
        return 0.0
    region_curve = scenario_data.get(ngfs_region) or scenario_data.get("rest_of_world", {})
    if not region_curve:
        return 0.0

    # Find bracket years in published trajectory
    years = sorted(int(y) for y in region_curve.keys())
    if not years:
        return 0.0
    if year <= years[0]:
        return float(region_curve[str(years[0])])
    if year >= years[-1]:
        return float(region_curve[str(years[-1])])

    for i in range(len(years) - 1):
        y0, y1 = years[i], years[i + 1]
        if y0 <= year <= y1:
            p0 = float(region_curve[str(y0)])
            p1 = float(region_curve[str(y1)])
            frac = (year - y0) / (y1 - y0)
            return p0 + frac * (p1 - p0)
    return 0.0


def get_pass_through(sector: str) -> dict:
    """Return pass-through coefficients for a sector (or sector-median default)."""
    spt = load_sector_pass_through()
    sectors = spt["sectors"]
    return sectors.get(sector, spt["default_unmatched"])


def abatement_index(
    target_year: int,
    residual_pct: float,
    years: List[int],
    base_year: int = 2025,
) -> Dict[int, float]:
    """
    Per-year Scope 1+2 emissions multiplier for a linear decarbonisation pathway:
    1.0 at base_year, falling to residual (residual_pct/100) by target_year, flat
    after. target_year <= 0 disables abatement (returns 1.0 for every year).
    """
    residual = min(1.0, max(0.0, residual_pct / 100.0))
    out: Dict[int, float] = {}
    for y in years:
        if not target_year or target_year <= base_year or y <= base_year:
            out[y] = 1.0
        elif y >= target_year:
            out[y] = residual
        else:
            frac = (y - base_year) / (target_year - base_year)
            out[y] = 1.0 + frac * (residual - 1.0)
    return out


def compute_carbon_cost(
    asset_id: str,
    sector: str,
    region_iso3: str,
    scenario_id: str,
    year: int,
    scope1_emissions_tco2: float,
    scope2_emissions_tco2: float,
    scope3_emissions_tco2: float = 0.0,
    pass_through_override: Optional[float] = None,
    direct_scale: float = 1.0,
    priced_fraction: float = 1.0,
) -> CarbonCostResult:
    """
    Compute Layer-1 carbon cost decomposition for one asset × scenario × year.

    direct_scale : abatement multiplier on Scope 1+2 for this year (1.0 = no abatement).
    priced_fraction : share of Scope 1+2 actually exposed to the carbon price, net of
                      free allocation / partial coverage (1.0 = fully priced).
    """
    ngfs_region = get_ngfs_region(region_iso3)
    price = get_carbon_price(scenario_id, year, ngfs_region)
    pt_data = get_pass_through(sector)
    pass_through = pass_through_override if pass_through_override is not None else float(pt_data["pass_through"])
    pass_through = max(0.0, min(1.0, pass_through))

    direct_scale = max(0.0, direct_scale)
    priced_fraction = max(0.0, min(1.0, priced_fraction))
    direct_emissions = max(0.0, scope1_emissions_tco2 + scope2_emissions_tco2) * direct_scale
    gross = direct_emissions * priced_fraction * price
    absorbed = gross * (1.0 - pass_through)
    passed = gross * pass_through
    scope3_indirect = max(0.0, scope3_emissions_tco2) * price * (1.0 - pass_through)
    net = absorbed + scope3_indirect

    return CarbonCostResult(
        asset_id=asset_id,
        sector=sector,
        scenario_id=scenario_id,
        year=year,
        region=region_iso3,
        ngfs_region=ngfs_region,
        carbon_price_usd_per_t=round(price, 2),
        pass_through=round(pass_through, 3),
        scope1_emissions_tco2=scope1_emissions_tco2,
        scope2_emissions_tco2=scope2_emissions_tco2,
        scope3_emissions_tco2=scope3_emissions_tco2,
        gross_cost_usd=round(gross, 2),
        absorbed_cost_usd=round(absorbed, 2),
        passed_through_usd=round(passed, 2),
        scope3_indirect_usd=round(scope3_indirect, 2),
        net_carbon_opex_usd=round(net, 2),
        notes=pt_data.get("source_ref", ""),
    )


def carbon_cost_timeline(
    asset_id: str,
    sector: str,
    region_iso3: str,
    scenario_id: str,
    years: List[int],
    scope1_emissions_tco2: float,
    scope2_emissions_tco2: float,
    scope3_emissions_tco2: float = 0.0,
    pass_through_override: Optional[float] = None,
    emissions_index: Optional[Dict[int, float]] = None,
    priced_fraction: float = 1.0,
) -> List[CarbonCostResult]:
    """Convenience wrapper to compute Layer-1 results across a year range.

    emissions_index : optional {year: Scope 1+2 multiplier} abatement pathway.
    priced_fraction : share of Scope 1+2 exposed to the carbon price (free allocation).
    """
    return [
        compute_carbon_cost(
            asset_id=asset_id,
            sector=sector,
            region_iso3=region_iso3,
            scenario_id=scenario_id,
            year=y,
            scope1_emissions_tco2=scope1_emissions_tco2,
            scope2_emissions_tco2=scope2_emissions_tco2,
            scope3_emissions_tco2=scope3_emissions_tco2,
            pass_through_override=pass_through_override,
            direct_scale=(emissions_index or {}).get(y, 1.0),
            priced_fraction=priced_fraction,
        )
        for y in years
    ]
