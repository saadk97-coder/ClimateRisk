"""
Transition Risk Orchestrator
============================

Composes Layers 1–4 into a single per-asset annual transition cost stream that
plugs into the existing climate-adjusted DCF engine.

Non-duplication discipline (BSR framework rule)
-----------------------------------------------
Each channel is routed exactly once:

  * Layer 1 (carbon cost)              → CASH FLOW (OpEx)
  * Layer 2 (technology / stranding)   → ASSET VALUE (impairment) + CASH FLOW (revenue erosion)
  * Layer 3 (network propagation)      → CASH FLOW (input cost)
  * Layer 4 (reputation / capital)     → either CASH FLOW (revenue) OR WACC, never both
                                          (default = CASH FLOW; orchestrator caller picks)

Outputs
-------
TransitionAssetResult contains:
  - annual_total_cost_usd      : tidy {year: USD} — feeds dcf as annual_damages
  - annual_impairment_usd      : tidy {year: USD} — value impairment (separate from CFs)
  - layer_breakdown            : per-layer per-year contribution
  - wacc_premium_bps           : Layer-4 financing add-on (only if routed to WACC)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging
import pandas as pd

from engine.transition.carbon_pricing import (
    compute_carbon_cost,
    carbon_cost_timeline,
    abatement_index,
    CarbonCostResult,
)
from engine.transition.learning_curves import (
    compute_stranding,
    revenue_erosion_usd,
    StrandingResult,
)
from engine.transition.network_propagation import (
    propagate_carbon_shock,
    aggregate_sector_carbon_costs,
    build_sectorwide_shock,
    NetworkShockResult,
)
from engine.transition.carbon_pricing import get_carbon_price
from engine.transition.data_loader import get_ngfs_region
from engine.transition.cc_exposure import (
    compute_exposure_premium,
    CCExposureResult,
    ROUTE_CASHFLOWS,
    ROUTE_WACC,
)
from engine.transition.data_loader import load_io_matrix
from engine.asset_model import Asset, normalize_assets

_log = logging.getLogger(__name__)

DEFAULT_HORIZON = list(range(2025, 2051))


@dataclass
class TransitionAssetResult:
    asset_id: str
    sector: str
    scenario_id: str
    region: str
    horizon: List[int]
    annual_total_cost_usd: Dict[int, float] = field(default_factory=dict)
    annual_impairment_usd: Dict[int, float] = field(default_factory=dict)
    layer_breakdown: Dict[str, Dict[int, float]] = field(default_factory=dict)
    wacc_premium_bps: float = 0.0
    layer1_results: List[CarbonCostResult] = field(default_factory=list)
    layer2_result: Optional[StrandingResult] = None
    layer3_results: List[NetworkShockResult] = field(default_factory=list)
    layer4_result: Optional[CCExposureResult] = None

    def to_dataframe(self) -> pd.DataFrame:
        rows = []
        for y in self.horizon:
            rows.append({
                "year": y,
                "scenario_id": self.scenario_id,
                "asset_id": self.asset_id,
                "sector": self.sector,
                "L1_carbon_opex": self.layer_breakdown.get("L1_carbon_opex", {}).get(y, 0.0),
                "L2_revenue_erosion": self.layer_breakdown.get("L2_revenue_erosion", {}).get(y, 0.0),
                "L2_impairment": self.layer_breakdown.get("L2_impairment", {}).get(y, 0.0),
                "L3_network_input_cost": self.layer_breakdown.get("L3_network_input_cost", {}).get(y, 0.0),
                "L4_revenue_modifier": self.layer_breakdown.get("L4_revenue_modifier", {}).get(y, 0.0),
                "total_cf_cost": self.annual_total_cost_usd.get(y, 0.0),
                "impairment": self.annual_impairment_usd.get(y, 0.0),
            })
        return pd.DataFrame(rows)


def run_asset_transition(
    asset: Asset,
    scenario_id: str,
    horizon: Optional[List[int]] = None,
    layer4_routing: str = ROUTE_CASHFLOWS,
    elasticity: float = 1.0,
    enable_layers: tuple = (1, 2, 3, 4),
    scope3_mode: str = "full",
    price_scale: float = 1.0,
    pass_through_scale: float = 1.0,
) -> TransitionAssetResult:
    """
    Compute a full transition risk timeline for one asset under one scenario.

    Parameters
    ----------
    asset : Asset
    scenario_id : str
    horizon : list of years, default 2025..2050 inclusive
    layer4_routing : ROUTE_CASHFLOWS or ROUTE_WACC — picks the non-duplication channel
    elasticity : Layer-3 substitution elasticity (default 1.0 = Cobb-Douglas)
    enable_layers : tuple of layer numbers to compute (e.g., (1, 2) skips 3 and 4)
    scope3_mode : 'full' (default — L1 always adds the Scope-3 term) or 'auto'
        (drop the L1 Scope-3 term whenever Layer 3 is enabled, so upstream cost is
        counted once via the network cascade rather than twice).
    """
    horizon = horizon or DEFAULT_HORIZON

    sector = asset.sector or "services"
    region = asset.region

    # ── Layer 1 ────────────────────────────────────────────────────────────
    layer1: List[CarbonCostResult] = []
    l1_by_year: Dict[int, float] = {y: 0.0 for y in horizon}
    if 1 in enable_layers:
        # Abatement pathway on Scope 1+2, and free-allocation-adjusted priced share.
        em_index = abatement_index(
            getattr(asset, "decarb_target_year", 0),
            getattr(asset, "decarb_residual_pct", 0.0),
            list(horizon),
        )
        priced_fraction = getattr(asset, "priced_emissions_fraction", 1.0)
        # Non-duplication: when L3 models upstream cost, drop the L1 Scope-3 term.
        l1_scope3 = 0.0 if (scope3_mode == "auto" and 3 in enable_layers) else asset.scope3_emissions_tco2
        layer1 = carbon_cost_timeline(
            asset_id=asset.id,
            sector=sector,
            region_iso3=region,
            scenario_id=scenario_id,
            years=horizon,
            scope1_emissions_tco2=asset.scope1_emissions_tco2,
            scope2_emissions_tco2=asset.scope2_emissions_tco2,
            scope3_emissions_tco2=l1_scope3,
            emissions_index=em_index,
            priced_fraction=priced_fraction,
            price_scale=price_scale,
            pass_through_scale=pass_through_scale,
        )
        for r in layer1:
            l1_by_year[r.year] = r.net_carbon_opex_usd

    # ── Layer 2 ────────────────────────────────────────────────────────────
    layer2: Optional[StrandingResult] = None
    l2_revenue_by_year: Dict[int, float] = {y: 0.0 for y in horizon}
    l2_impairment_by_year: Dict[int, float] = {y: 0.0 for y in horizon}
    if 2 in enable_layers:
        layer2 = compute_stranding(
            asset_id=asset.id,
            sector=sector,
            replacement_value=asset.replacement_value,
            scenario_id=scenario_id,
            years=horizon,
        )
        if asset.annual_revenue > 0:
            l2_revenue_by_year = revenue_erosion_usd(asset.annual_revenue, layer2.revenue_index)
        l2_impairment_by_year = dict(layer2.annual_impairment_usd)

    # ── Layer 3 ────────────────────────────────────────────────────────────
    # Per-asset Layer 3 uses a SECTOR-TYPICAL shock vector (every sector pays
    # carbon × pass-through on its typical emission intensity), then reads off
    # the focal sector's indirect input-cost exposure. This avoids double-
    # counting the asset's own pass-through and gives a meaningful per-asset
    # supply-chain exposure number.
    layer3: List[NetworkShockResult] = []
    l3_by_year: Dict[int, float] = {y: 0.0 for y in horizon}
    if 3 in enable_layers:
        ngfs_region = get_ngfs_region(region)
        for y in horizon:
            price = get_carbon_price(scenario_id, y, ngfs_region) * max(0.0, price_scale)
            sector_shock = build_sectorwide_shock(price)
            shock = propagate_carbon_shock(
                asset_id=asset.id,
                sector=sector,
                scenario_id=scenario_id,
                year=y,
                asset_revenue=asset.annual_revenue,
                sector_carbon_costs=sector_shock,
                sector_outputs=None,   # shocks already normalised
                elasticity=elasticity,
            )
            layer3.append(shock)
            l3_by_year[y] = shock.total_indirect_cost_usd

    # ── Layer 4 ────────────────────────────────────────────────────────────
    layer4: Optional[CCExposureResult] = None
    l4_by_year: Dict[int, float] = {y: 0.0 for y in horizon}
    wacc_premium_bps = 0.0
    if 4 in enable_layers:
        layer4 = compute_exposure_premium(
            asset_id=asset.id,
            sector=sector,
            scenario_id=scenario_id,
            annual_revenue=asset.annual_revenue,
            years=horizon,
            routing=layer4_routing,
        )
        if layer4_routing == ROUTE_CASHFLOWS:
            # Sign convention: positive opportunity → positive revenue → NEGATIVE cost.
            # Negative opportunity (regulatory drag dominates) → positive cost.
            l4_by_year = {y: -float(v) for y, v in layer4.annual_revenue_modifier_usd.items()}
        else:
            # ROUTE_WACC — financing premium adds to discount rate; no CF impact.
            wacc_premium_bps = layer4.credit_spread_premium_bps + layer4.equity_premium_bps

    # ── Aggregate ──────────────────────────────────────────────────────────
    total_by_year = {
        y: l1_by_year[y] + l2_revenue_by_year[y] + l3_by_year[y] + l4_by_year[y]
        for y in horizon
    }

    breakdown = {
        "L1_carbon_opex": l1_by_year,
        "L2_revenue_erosion": l2_revenue_by_year,
        "L2_impairment": l2_impairment_by_year,
        "L3_network_input_cost": l3_by_year,
        "L4_revenue_modifier": l4_by_year,
    }

    return TransitionAssetResult(
        asset_id=asset.id,
        sector=sector,
        scenario_id=scenario_id,
        region=region,
        horizon=list(horizon),
        annual_total_cost_usd=total_by_year,
        annual_impairment_usd=l2_impairment_by_year,
        layer_breakdown=breakdown,
        wacc_premium_bps=round(wacc_premium_bps, 2),
        layer1_results=layer1,
        layer2_result=layer2,
        layer3_results=layer3,
        layer4_result=layer4,
    )


def run_portfolio_transition(
    assets: List,
    scenario_ids: List[str],
    horizon: Optional[List[int]] = None,
    layer4_routing: str = ROUTE_CASHFLOWS,
    elasticity: float = 1.0,
    enable_layers: tuple = (1, 2, 3, 4),
    scope3_mode: str = "full",
    price_scale: float = 1.0,
    pass_through_scale: float = 1.0,
) -> Dict[str, List[TransitionAssetResult]]:
    """
    Run all assets × scenarios. Returns {scenario_id: [TransitionAssetResult, ...]}.

    Layer 3 is computed per-asset using only that asset's own Layer-1 cost as
    shock — this is the screening default. For a portfolio-pooled cascade
    (memo's "bespoke add-on"), call propagate_carbon_shock directly with
    aggregate_sector_carbon_costs(all_layer1_results) as input.
    """
    horizon = horizon or DEFAULT_HORIZON
    assets = normalize_assets(assets)
    out: Dict[str, List[TransitionAssetResult]] = {}
    for sc in scenario_ids:
        out[sc] = []
        for a in assets:
            if not a.sector:
                _log.info(f"Asset {a.id}: no sector set; skipping transition layer.")
                continue
            r = run_asset_transition(
                a, sc, horizon=horizon, layer4_routing=layer4_routing,
                elasticity=elasticity, enable_layers=enable_layers,
                scope3_mode=scope3_mode,
                price_scale=price_scale, pass_through_scale=pass_through_scale,
            )
            out[sc].append(r)
    return out


def transition_results_to_damage_df(
    results: Dict[str, List[TransitionAssetResult]],
) -> pd.DataFrame:
    """
    Flatten per-scenario per-asset transition results into the same long-form
    DataFrame shape expected by dcf_engine (columns: year, ead, scenario_id).

    The 'ead' column here represents the cash-flow cost of transition risk —
    not physical EAD. The two are added in the combined DCF.
    """
    rows = []
    for sc, asset_results in results.items():
        for ar in asset_results:
            for y, cost in ar.annual_total_cost_usd.items():
                rows.append({"year": y, "ead": float(cost), "scenario_id": sc, "asset_id": ar.asset_id})
    if not rows:
        return pd.DataFrame(columns=["year", "ead", "scenario_id", "asset_id"])
    return pd.DataFrame(rows)
