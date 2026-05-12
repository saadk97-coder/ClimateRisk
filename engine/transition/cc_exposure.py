"""
Layer 4 — Reputational and capital-access overlay.

Methodology
-----------
Sautner, van Lent, Vilkov, Zhang (2023) decompose firm-level Climate Change
Exposure (CCExposure) into three sub-measures from earnings-call transcripts:
  - opportunity:  positive narrative (revenue uplift)
  - regulatory:   policy/legal exposure (cost & spread)
  - physical:     climate-physical-impact discussion (cost & spread)

Empirical elasticities (Sautner et al. 2023, Management Science) translate one-σ
CCExposure shocks into pricing impacts:
  - +12 bps credit spread per unit regulatory exposure
  - +6 bps credit spread per unit physical exposure
  - +50 bps total equity premium per unit total exposure
  - +35 bps revenue growth per unit opportunity exposure
  - −25 bps revenue drag per unit regulatory exposure

This layer routes outputs to either CASH FLOWS (revenue modifier) or DISCOUNT
RATE (financing premium), preserving the BSR framework's non-duplication rule.
The orchestrator (transition_engine) picks one route per use-case to avoid
double-counting.

Sources
-------
- Sautner, van Lent, Vilkov, Zhang (2023). 'Firm-Level Climate Change Exposure.'
  Journal of Finance 78(3): 1449-1498.
- Sautner et al. (2023). 'Pricing Climate Change Exposure.' Management Science.
- Engle, Giglio, Kelly, Lee, Stroebel (2020). 'Hedging Climate Change News.'
  RFS 33(3): 1184-1216 — climate news beta as triangulation.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import logging

from engine.transition.data_loader import load_cc_exposure, map_scenario_to_ngfs

_log = logging.getLogger(__name__)

# Default channel: route Layer 4 outputs to either CFs or WACC (not both).
ROUTE_CASHFLOWS = "cashflows"
ROUTE_WACC = "wacc"


@dataclass
class CCExposureResult:
    asset_id: str
    sector: str
    scenario_id: str
    cce_opportunity: float           # scenario-adjusted CCExposure sub-scores
    cce_regulatory: float
    cce_physical: float
    credit_spread_premium_bps: float    # added to debt cost / WACC
    equity_premium_bps: float           # added to cost of equity / WACC
    revenue_growth_modifier_bps: float  # net (opportunity + regulatory drag) — applied to revenue growth
    annual_revenue_modifier_usd: Dict[int, float]   # per year, USD
    routing: str                        # ROUTE_CASHFLOWS or ROUTE_WACC
    notes: str = ""


def get_sector_exposure(sector: str) -> Dict[str, float]:
    cce = load_cc_exposure()
    return cce["sectors"].get(sector, cce["default_unmatched"])


def _scenario_modifiers(scenario_id: str) -> Dict[str, float]:
    cce = load_cc_exposure()
    mods = cce["_meta"]["scenario_modifiers"]
    scen = scenario_id if scenario_id in mods else map_scenario_to_ngfs(scenario_id)
    return mods.get(scen, {"opportunity": 1.0, "regulatory": 1.0, "physical": 1.0})


def compute_exposure_premium(
    asset_id: str,
    sector: str,
    scenario_id: str,
    annual_revenue: float,
    years: List[int],
    routing: str = ROUTE_CASHFLOWS,
    firm_override: Optional[Dict[str, float]] = None,
) -> CCExposureResult:
    """
    Translate CCExposure scores into either revenue/CF modifiers or WACC additions.

    Parameters
    ----------
    routing : ROUTE_CASHFLOWS (default) or ROUTE_WACC
        Determines whether the financial impact flows through cash flows
        (annual_revenue_modifier_usd) or the discount rate (credit/equity
        premium in bps). The non-duplication rule means downstream consumers
        should use exactly one of the two outputs at a time.
    firm_override : optional firm-specific {opportunity, regulatory, physical}
        scores from a Sautner-licensed feed. Sector medians used otherwise.
    """
    base = firm_override if firm_override is not None else get_sector_exposure(sector)
    mods = _scenario_modifiers(scenario_id)
    cce_opp = base.get("opportunity", 0.5) * mods.get("opportunity", 1.0)
    cce_reg = base.get("regulatory", 0.5) * mods.get("regulatory", 1.0)
    cce_phy = base.get("physical", 0.5) * mods.get("physical", 1.0)

    elasts = load_cc_exposure()["_meta"]["elasticities"]
    credit_bps = (
        cce_reg * float(elasts["credit_spread_bps_per_unit_regulatory"]) +
        cce_phy * float(elasts["credit_spread_bps_per_unit_physical"])
    )
    equity_bps = (cce_opp + cce_reg + cce_phy) * float(elasts["equity_premium_bps_per_unit_total"])
    rev_growth_bps = (
        cce_opp * float(elasts["revenue_growth_bps_per_unit_opportunity"])
        - cce_reg * float(elasts["regulatory_revenue_drag_bps_per_unit"])
    )

    # Revenue modifier USD: applied as basis-point growth to the prior year's revenue,
    # cumulating across the horizon.
    annual_mod: Dict[int, float] = {}
    if routing == ROUTE_CASHFLOWS and years:
        cumulative_factor = 1.0
        prior_year = min(years) - 1
        for y in sorted(years):
            elapsed = max(1, y - prior_year)
            cumulative_factor *= (1.0 + (rev_growth_bps / 10_000.0)) ** elapsed
            annual_mod[y] = round(annual_revenue * (cumulative_factor - 1.0), 2)
            prior_year = y
    else:
        for y in years:
            annual_mod[y] = 0.0

    return CCExposureResult(
        asset_id=asset_id,
        sector=sector,
        scenario_id=scenario_id,
        cce_opportunity=round(cce_opp, 4),
        cce_regulatory=round(cce_reg, 4),
        cce_physical=round(cce_phy, 4),
        credit_spread_premium_bps=round(credit_bps, 2),
        equity_premium_bps=round(equity_bps, 2),
        revenue_growth_modifier_bps=round(rev_growth_bps, 2),
        annual_revenue_modifier_usd=annual_mod,
        routing=routing,
        notes="Sautner et al. JoF 2023 + Mgmt Sci 2023 elasticities; sector-median CCExposure.",
    )
