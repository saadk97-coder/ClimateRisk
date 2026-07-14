"""
Screening estimation for low-disclosure entities.

When a company publishes little — no reported Scope 1+2, no transition plan, no
capex — the engine would otherwise treat it as zero-emission (and so zero carbon
cost), which understates its risk. This module fills the gaps from OUR OWN inputs
so an opaque entity can still be screened from just {sector, region, revenue}:

  * Scope 1+2  → sector emission intensity (tCO2 per $M output) × revenue.
  * Scope 3    → left to the Layer-3 Leontief estimate (revenue × input share),
                 which already does not need a reported figure.
  * capex      → the model's top-down transition-capex estimate (already default).
  * positioning→ derived from the estimated emissions (already default).

Everything here is a SCREENING approximation (EEIO/EXIOBASE-informed sector
averages, not firm data) and is flagged as such via `data_quality`.
"""

from __future__ import annotations
from dataclasses import replace
from typing import Tuple

from engine.transition.data_loader import load_sector_taxonomy, load_estimation_intensity

# Purchased-electricity (Scope 2) is not in the taxonomy's direct Scope-1 intensity. When we
# fall back to it, uplift by a modest factor to approximate Scope 1+2.
_SCOPE2_UPLIFT = 1.15


def scope12_intensity_t_per_musd(sector: str) -> float:
    """Scope 1+2 intensity (tCO2 per $M revenue) used for the estimation path. Prefers the
    firm-calibrated `estimation_intensity.json`; falls back to the taxonomy EEIO intensity
    (× a Scope-2 uplift), which is tuned for the L3 shock and undershoots a heavy producer."""
    calibrated = load_estimation_intensity().get("scope12_t_per_musd_revenue", {})
    if sector in calibrated:
        return float(calibrated[sector])
    tax_ei = float(load_sector_taxonomy()["sectors"].get(sector, {})
                   .get("emission_intensity_t_per_revenue", 0.0))
    return tax_ei * _SCOPE2_UPLIFT


def estimate_scope12_from_revenue(sector: str, revenue_usd: float) -> float:
    """Screening Scope 1+2 (tCO2/yr) = sector intensity (tCO2/$M) × revenue.
    Returns 0 for an unknown sector or non-positive revenue."""
    if revenue_usd is None or revenue_usd <= 0 or not sector:
        return 0.0
    intensity = scope12_intensity_t_per_musd(sector)   # t / $M
    if intensity <= 0:
        return 0.0
    return round(intensity * (revenue_usd / 1e6), 1)


def estimate_emissions_if_missing(asset) -> Tuple[object, bool]:
    """Return (asset, estimated?). If the asset reports no Scope 1+2 but has a sector and
    revenue, fill Scope 1+2 with a screening estimate (all attributed to Scope 1 for
    simplicity) and return estimated=True. Otherwise return the asset unchanged."""
    s12 = (getattr(asset, "scope1_emissions_tco2", 0.0) or 0.0) + \
          (getattr(asset, "scope2_emissions_tco2", 0.0) or 0.0)
    sector = getattr(asset, "sector", "") or ""
    revenue = getattr(asset, "annual_revenue", 0.0) or 0.0
    if s12 > 0 or not sector or revenue <= 0:
        return asset, False
    est = estimate_scope12_from_revenue(sector, revenue)
    if est <= 0:
        return asset, False
    return replace(asset, scope1_emissions_tco2=est, scope2_emissions_tco2=0.0), True
