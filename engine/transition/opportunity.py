"""
Transition OPPORTUNITY capex — a separate lens for clean-growth companies.

The transition-risk model prices the cost to decarbonise a company's OWN emissions.
It deliberately does not price the growth capital a transition WINNER spends to expand
its low-carbon business (a renewables/grid utility, an EV maker, a transition-minerals
miner). This module estimates that growth-capital opportunity so it can be shown
side-by-side with the risk — never summed into it.

A sector is a transition BENEFICIARY when its demand grows BECAUSE of decarbonisation:
its Net-Zero demand pathway rises materially ABOVE its Current-Policies pathway (baseline
economic growth, which is not a green opportunity, cancels out). The growth capital is a
screening multiple of the firm's asset base:

    transition_growth = clamp(NZ_growth − CurrentPolicies_growth, 0, GROWTH_CAP)
    opportunity_capex  = transition_growth × replacement_value × OPP_CAPEX_INTENSITY

Screening only — a firm captures a SHARE of global sector growth, so this is an
order-of-magnitude indication of the expansion investment, not a capital budget.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from engine.transition.data_loader import load_sector_pathways, map_scenario_to_ngfs

# A firm won't grow more than ~this multiple off the back of the transition even if the
# GLOBAL sector market grows 5-14× (it captures a share). Clamp the growth signal.
GROWTH_CAP = 1.5
# $ of growth capex per $ of asset base, per unit of transition growth. Default; overridden
# per sector below because capital intensity of the build varies a lot.
OPP_CAPEX_INTENSITY = 0.6
# Per-sector capital intensity of the low-carbon build. Renewables/grid are extremely
# capital-heavy (assets ARE the capex); EV assembly and mineral processing are lighter per $
# of expansion; engineered-wood mills lighter still.
_SECTOR_OPP_INTENSITY = {
    "power_renewable": 1.0,     # generation + grid assets are the capital
    "power_gas": 0.9,
    "metals_mining": 0.7,       # new mines/processing are capital-heavy
    "road_transport_ev": 0.5,   # gigafactories + lines, but lighter per $ than power
    "data_center": 0.8,         # facilities + compute
    "wood_products_timber": 0.35,
}
# Minimum transition-attributable growth to count a sector as a beneficiary.
_BENEFICIARY_THRESHOLD = 0.15
_BASELINE_SCENARIO = "current_policies"


@dataclass
class OpportunityResult:
    sector: str
    is_beneficiary: bool
    transition_growth: float          # NZ growth minus baseline growth, clamped [0, CAP]
    opportunity_capex_usd: float      # screening growth-capital estimate over the horizon
    nz_growth: float                  # raw NZ demand-pathway growth factor − 1
    baseline_growth: float            # raw Current-Policies growth factor − 1


def _pathway_growth(sector: str, scenario_id: str) -> float:
    """Fractional demand growth 2025→2050 for a sector under a scenario (0 = flat)."""
    pw = load_sector_pathways()["sectors"].get(sector, {})
    curve = pw.get(map_scenario_to_ngfs(scenario_id)) or pw.get(scenario_id) or {}
    if "2025" not in curve or "2050" not in curve:
        return 0.0
    base = float(curve["2025"]) or 1.0
    return float(curve["2050"]) / base - 1.0


def estimate_opportunity_capex(
    sector: str,
    replacement_value: float,
    scenario_id: str = "net_zero_2050",
    horizon: Optional[List[int]] = None,
) -> OpportunityResult:
    """Growth-capital opportunity for a transition beneficiary. Non-beneficiaries return 0."""
    nz = _pathway_growth(sector, scenario_id)
    base = _pathway_growth(sector, _BASELINE_SCENARIO)
    transition_growth = max(0.0, nz - base)
    is_beneficiary = transition_growth >= _BENEFICIARY_THRESHOLD
    capped = min(GROWTH_CAP, transition_growth)
    intensity = _SECTOR_OPP_INTENSITY.get(sector, OPP_CAPEX_INTENSITY)
    capex = round(capped * max(0.0, replacement_value) * intensity, 2) if is_beneficiary else 0.0
    return OpportunityResult(
        sector=sector, is_beneficiary=is_beneficiary, transition_growth=round(capped, 3),
        opportunity_capex_usd=capex, nz_growth=round(nz, 3), baseline_growth=round(base, 3),
    )
