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

from engine.transition.data_loader import load_sector_taxonomy

# Purchased-electricity (Scope 2) is not in the direct Scope-1 intensity. For a
# screening estimate, uplift the direct intensity by a modest factor to approximate
# Scope 1+2 for sectors that buy meaningful grid power (light industry, services);
# heavy fossil sectors are Scope-1-dominated so the uplift matters less.
_SCOPE2_UPLIFT = 1.15


def estimate_scope12_from_revenue(sector: str, revenue_usd: float) -> float:
    """Screening Scope 1+2 (tCO2/yr) from sector emission intensity × revenue.

    Intensity is tCO2 per $M of gross output (taxonomy `emission_intensity_t_per_revenue`).
    Returns 0 for an unknown sector or non-positive revenue.
    """
    if revenue_usd is None or revenue_usd <= 0:
        return 0.0
    meta = load_sector_taxonomy()["sectors"].get(sector, {})
    intensity = float(meta.get("emission_intensity_t_per_revenue", 0.0))   # t / $M
    if intensity <= 0:
        return 0.0
    return round(intensity * (revenue_usd / 1e6) * _SCOPE2_UPLIFT, 1)


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
