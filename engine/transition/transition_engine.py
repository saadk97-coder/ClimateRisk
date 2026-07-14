"""
Transition Risk Orchestrator
============================

Composes Layers 1–4 into a single per-asset annual transition cost stream that
plugs into the existing climate-adjusted DCF engine.

Non-duplication discipline (BSR framework rule)
-----------------------------------------------
Each channel is ROUTED ONCE BY DESIGN, with disclosed boundary exceptions (Scope 2/3
incidence is handled by the scope2_mode/scope3_mode switches; demand-collapse loss
appears as BOTH revenue erosion in cash flows AND a separate impairment lens — never
summed). Channel → destination:

  * Layer 1 (carbon cost)              → CASH FLOW (OpEx)
  * Layer 2 (technology / stranding)   → ASSET VALUE (impairment) + CASH FLOW (revenue erosion)
  * Layer 3 (network propagation)      → CASH FLOW (input cost)
  * Layer 4 (reputation / capital)     → WACC (equity risk premium, Sautner Pricing) by
                                          DEFAULT; the cash-flow revenue route is opt-in and
                                          UNSOURCED (market-opportunity → manual layer). R5.

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
from engine.transition.data_loader import get_ngfs_region, map_scenario_to_ngfs
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

# Fix #1 — when a firm reports its UPSTREAM Scope 3, L3 is anchored to that reported
# quantity: cost = scope3_upstream × carbon_price × incidence. The incidence is the share
# of the supplier's carbon cost that reaches this firm via input prices (supplier
# pass-through to buyer). Overridable via scope3_incidence.
L3_SCOPE3_INCIDENCE = 0.5
# Fix #2 — share of the customer's use-phase carbon burden that comes back to the product
# MAKER as demand/margin pressure (customers bear most; the maker loses some pricing/volume).
USE_PHASE_INCIDENCE = 0.15
# Financed emissions (financials). A lender/investor doesn't PAY its book's carbon, but bears
# transition risk transmitted through the portfolio (credit impairment, stranded collateral,
# lost high-carbon lending). Screening share of the financed carbon cost that lands on the
# institution. Deliberately small; a real figure needs PCAF portfolio + credit modelling.
FINANCED_INCIDENCE = 0.03


def _resolve_positioning(explicit, asset):
    """Positioning override precedence: explicit arg → asset field → None (derive).
    The asset field uses -1 as the 'unset' sentinel (dataclasses can't hold None here)."""
    if explicit is not None:
        return explicit
    v = getattr(asset, "positioning_override", -1.0)
    return v if (v is not None and v >= 0.0) else None


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
    data_quality: str = "sector-proxy"          # 'firm' | 'sector-proxy' | 'degraded'
    data_quality_flags: List[str] = field(default_factory=list)
    strategy: object = None                      # AdaptiveStrategy (adaptive capacity)

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
    layer4_routing: str = ROUTE_WACC,
    elasticity: float = 1.0,
    enable_layers: tuple = (1, 2, 3, 4),
    scope3_mode: str = "auto",
    price_scale: float = 1.0,
    pass_through_scale: float = 1.0,
    l3_mode: str = "world",
    cascade: bool = False,
    cascade_theta: float = 0.02,
    cascade_contagion: float = 0.5,
    firm_cce_override: Optional[Dict[str, float]] = None,
    carbon_inclusive_crossover: bool = False,
    non_fossil_base_fraction: float = 0.5,
    stranding_slope: Optional[float] = None,
    l3_partial_pass_through: bool = False,
    scope3_incidence: Optional[float] = None,
    scope2_mode: str = "auto",
    equity_weight: float = 0.6,
    debt_weight: float = 0.4,
    tax_rate: float = 0.25,
    adaptive: bool = True,
    ambition_override: Optional[float] = None,
    positioning_override: Optional[float] = None,
    plan_coverage: Optional[float] = None,
    transition_capex_override: Optional[float] = None,
    capex_schedule_override: Optional[Dict[int, float]] = None,
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
    scope3_mode : 'auto' (default — drop the L1 Scope-3 term whenever Layer 3 is
        enabled, so upstream carbon is counted once via the network cascade rather
        than twice) or 'full' (keep Scope-3 in L1; use only when Layer 3 is off).
    scope2_mode : 'auto' (default — drop the L1 Scope-2 term when Layer 3 is enabled,
        since purchased-electricity carbon reaches the firm through power prices
        modelled in L3) or 'direct' (keep Scope 2 in L1, for a firm that pays an
        explicit carbon charge on its electricity).
    equity_weight, debt_weight, tax_rate : capital structure for converting the
        Layer-4 equity premium and credit spread into a single ΔWACC (default
        60/40, 25% tax) — used only when layer4_routing = ROUTE_WACC.
    """
    horizon = horizon or DEFAULT_HORIZON

    # Loud validation of mode/routing enums (they otherwise fall through silently).
    if layer4_routing not in (ROUTE_WACC, ROUTE_CASHFLOWS):
        _log.warning("Unknown layer4_routing '%s'; defaulting to ROUTE_WACC.", layer4_routing)
        layer4_routing = ROUTE_WACC
    if l3_mode not in ("world", "mrio"):
        _log.warning("Unknown l3_mode '%s'; defaulting to 'world'.", l3_mode)
        l3_mode = "world"
    if scope3_mode not in ("auto", "full"):
        _log.warning("Unknown scope3_mode '%s'; defaulting to 'auto'.", scope3_mode)
        scope3_mode = "auto"

    sector = asset.sector or "services"
    if not asset.sector:
        _log.warning("Asset %s has no sector; using 'services' proxy.", asset.id)
    region = asset.region

    # ── Adaptive capacity / transition strategy ─────────────────────────────
    # Converts GROSS L2 erosion into RESIDUAL risk after a stated pathway. ON by
    # default; ambition defaults from the scenario narrative, positioning is derived
    # (science) or overridden (art), capex is company-provided or estimated.
    strategy = None
    if adaptive:
        from engine.transition.adaptive_capacity import build_strategy
        strategy = build_strategy(
            asset_id=asset.id, sector=sector, scenario_id=scenario_id,
            region_band=get_ngfs_region(region),
            scope12_tco2=asset.scope1_emissions_tco2 + asset.scope2_emissions_tco2,
            revenue_usd=asset.annual_revenue, replacement_value=asset.replacement_value,
            horizon=list(horizon),
            target_year=getattr(asset, "decarb_target_year", 0),
            residual_pct=getattr(asset, "decarb_residual_pct", 0.0),
            ambition_override=ambition_override,
            positioning_override=_resolve_positioning(positioning_override, asset),
            plan_coverage=plan_coverage,
            transition_capex_override=(transition_capex_override
                                       if transition_capex_override is not None
                                       else getattr(asset, "transition_capex_usd", 0.0) or None),
            capex_schedule_override=capex_schedule_override,
        )

    # ── Layer 1 ────────────────────────────────────────────────────────────
    layer1: List[CarbonCostResult] = []
    l1_by_year: Dict[int, float] = {y: 0.0 for y in horizon}
    if 1 in enable_layers:
        # Abatement pathway on Scope 1+2. An explicit decarb target wins; otherwise, if
        # adaptive is on, the SCENARIO-IMPLIED ambition drives an emissions pathway
        # (residual = 1 − ambition by the horizon end) — i.e. "if the company follows
        # this scenario, its emissions look like this". The transition capex below is
        # the cost of that abatement (so a target is never free).
        _tgt = getattr(asset, "decarb_target_year", 0)
        if _tgt and _tgt > min(horizon):
            em_index = abatement_index(_tgt, getattr(asset, "decarb_residual_pct", 0.0), list(horizon))
        elif strategy is not None and strategy.ambition > 0:
            em_index = abatement_index(max(horizon), (1.0 - strategy.ambition) * 100.0, list(horizon))
        else:
            em_index = abatement_index(0, 0.0, list(horizon))
        priced_fraction = getattr(asset, "priced_emissions_fraction", 1.0)
        # Non-duplication (Scope 2 & 3 incidence): Scope 2 is the power supplier's
        # carbon cost reaching the firm through electricity prices, and upstream
        # Scope 3 is supplier incidence. When Layer 3 models those supplier costs,
        # charging them AGAIN as a direct L1 liability double-counts. So by default
        # ("auto") both are dropped from L1 when L3 is enabled — Scope 2 unless the
        # firm pays an EXPLICIT carbon charge on purchased electricity (scope2_mode
        # = "direct"). "full" keeps them in L1 (use only when L3 is off).
        l1_scope3 = 0.0 if (scope3_mode == "auto" and 3 in enable_layers) else asset.scope3_emissions_tco2
        drop_scope2 = (scope2_mode == "auto" and 3 in enable_layers)
        l1_scope2 = 0.0 if drop_scope2 else asset.scope2_emissions_tco2
        layer1 = carbon_cost_timeline(
            asset_id=asset.id,
            sector=sector,
            region_iso3=region,
            scenario_id=scenario_id,
            years=horizon,
            scope1_emissions_tco2=asset.scope1_emissions_tco2,
            scope2_emissions_tco2=l1_scope2,
            scope3_emissions_tco2=l1_scope3,
            emissions_index=em_index,
            priced_fraction=priced_fraction,
            price_scale=price_scale,
            pass_through_scale=pass_through_scale,
            scope3_incidence=scope3_incidence,
        )
        for r in layer1:
            l1_by_year[r.year] = r.net_carbon_opex_usd

    # ── Layer 2 ────────────────────────────────────────────────────────────
    layer2: Optional[StrandingResult] = None
    l2_revenue_by_year: Dict[int, float] = {y: 0.0 for y in horizon}
    l2_impairment_by_year: Dict[int, float] = {y: 0.0 for y in horizon}
    _incumbent_share = (1.0 - strategy.already_transitioned) if strategy is not None else 1.0
    if 2 in enable_layers:
        layer2 = compute_stranding(
            asset_id=asset.id,
            sector=sector,
            replacement_value=asset.replacement_value,
            scenario_id=scenario_id,
            years=horizon,
            non_fossil_base_fraction=non_fossil_base_fraction,
            slope=stranding_slope,
            carbon_inclusive_crossover=carbon_inclusive_crossover,
            region_iso3=region,
            price_scale=price_scale,
            incumbent_share=_incumbent_share,   # positioning → less to strand
            ambition=(strategy.ambition if strategy is not None else 0.0),  # tech-substitution stranding
        )
        if asset.annual_revenue > 0:
            gross_erosion = revenue_erosion_usd(asset.annual_revenue, layer2.revenue_index)
            # Adaptive capacity: the pivot recaptures part of the lost incumbent
            # revenue in the growing challenger market → net erosion = gross × (1−capture).
            cap = strategy.capture_fraction if strategy is not None else 0.0
            l2_revenue_by_year = {y: round(v * (1.0 - cap), 2) for y, v in gross_erosion.items()}
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
        # R2 — partial pass-through: the firm recovers its own sector's
        # pass-through share of the upstream cost downstream, absorbing only
        # (1 − PT_focal). Default off → full absorption (legacy anchors).
        if l3_partial_pass_through:
            from engine.transition.carbon_pricing import get_pass_through
            l3_absorption = max(0.0, 1.0 - float(get_pass_through(sector)["pass_through"]))
        else:
            l3_absorption = 1.0
        # Fix #1: L3 scales by the carbon-EXPOSED input base (revenue × intermediate-input
        # share), not total revenue — so asset-light, high-revenue firms (services, finance)
        # don't book an implausible supply-chain carbon cost.
        from engine.transition.data_loader import load_sector_taxonomy as _lst
        _sector_meta = _lst()["sectors"].get(sector, {})
        l3_input_share = float(_sector_meta.get("intermediate_input_share", 0.5))
        # Biogenic upstream (Mercer live test). For forest products / bio-based sectors, much of the
        # reported upstream Scope 3 is BIOGENIC (sustainably-managed wood fibre) whose carbon is not
        # priced at the fossil carbon price. `biogenic_scope3_fraction` nets that portion out so a
        # pulp mill's fibre supply isn't charged as if it were steel or cement. Default 0.
        biogenic_frac = max(0.0, min(1.0, float(_sector_meta.get("biogenic_scope3_fraction", 0.0))))
        # Fix #1 — REPORT-ANCHORED L3. If the firm reports its upstream Scope 3 (and we're in
        # 'auto' mode, so it isn't already in L1), price that reported quantity directly rather
        # than a sector-typical Leontief propagation — using the company's actual value-chain
        # carbon (e.g. Nike 9.5 Mt, BASF 90 Mt) instead of a generic estimate. The Leontief path
        # remains the fallback for non-reporters (scope3 == 0) and for 'full' mode.
        report_anchored = (scope3_mode == "auto" and asset.scope3_emissions_tco2 > 0)
        if report_anchored:
            inc = (L3_SCOPE3_INCIDENCE if scope3_incidence is None
                   else max(0.0, min(1.0, scope3_incidence)))
            priced_scope3 = asset.scope3_emissions_tco2 * (1.0 - biogenic_frac)
            for y in horizon:
                price = get_carbon_price(scenario_id, y, ngfs_region, region_iso3=region) * max(0.0, price_scale)
                l3_by_year[y] = round(priced_scope3 * price * inc * l3_absorption, 2)
        elif l3_mode == "mrio":
            # High-resolution 20×49 EXIOBASE MRIO (+ optional Reisch cascade).
            from engine.transition.network_mrio import propagate_mrio
            for y in horizon:
                shock = propagate_mrio(
                    asset_id=asset.id, sector=sector, region_iso3=region,
                    ngfs_band=ngfs_region, scenario_id=scenario_id, year=y,
                    asset_revenue=asset.annual_revenue, elasticity=elasticity,
                    cascade=cascade, cascade_theta=cascade_theta,
                    cascade_contagion=cascade_contagion,
                    absorption=l3_absorption,
                    price_scale=price_scale, pass_through_scale=pass_through_scale,
                    input_share=l3_input_share,
                )
                layer3.append(shock)
                l3_by_year[y] = shock.total_indirect_cost_usd
        else:
            for y in horizon:
                price = get_carbon_price(scenario_id, y, ngfs_region, region_iso3=region) * max(0.0, price_scale)
                sector_shock = build_sectorwide_shock(price, pass_through_scale=pass_through_scale)
                shock = propagate_carbon_shock(
                    asset_id=asset.id,
                    sector=sector,
                    scenario_id=scenario_id,
                    year=y,
                    asset_revenue=asset.annual_revenue,
                    sector_carbon_costs=sector_shock,
                    sector_outputs=None,   # shocks already normalised
                    elasticity=elasticity,
                    absorption=l3_absorption,
                    input_share=l3_input_share,
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
            firm_override=firm_cce_override,   # firm-level Sautner CCExposure (else sector median)
        )
        if layer4_routing == ROUTE_CASHFLOWS:
            # Sign convention: positive opportunity → positive revenue → NEGATIVE cost.
            # Negative opportunity (regulatory drag dominates) → positive cost.
            l4_by_year = {y: -float(v) for y, v in layer4.annual_revenue_modifier_usd.items()}
        else:
            # ROUTE_WACC — financing premium adds to the discount rate; no CF impact.
            # The equity premium enters the COST OF EQUITY and the credit spread the
            # AFTER-TAX COST OF DEBT, weighted by capital structure — NOT added
            # one-for-one (that overstated the WACC hit). Sautner's sourced result is
            # the equity-premium term; the credit term is an unsourced placeholder.
            wacc_premium_bps = (
                equity_weight * layer4.equity_premium_bps
                + debt_weight * layer4.credit_spread_premium_bps * (1.0 - tax_rate)
            )

    # ── Adaptive-capacity transition capex ──────────────────────────────────
    # The investment that EARNS the capture and the L1 abatement (so a pivot / target
    # is never free). A cash-flow cost, routed once. Applied only when Layer 2 is on
    # (capex accompanies the technology transition).
    l2_capex_by_year: Dict[int, float] = {y: 0.0 for y in horizon}
    if strategy is not None and 2 in enable_layers:
        for y in horizon:
            l2_capex_by_year[y] = strategy.annual_capex_usd.get(y, 0.0)

    # ── Product use-phase risk (Fix #2) ─────────────────────────────────────
    # For a maker of carbon-emitting PRODUCTS (diesel machinery, engines, ICE vehicles),
    # the customers' use-phase Scope 3 (cat 11) creates demand/margin pressure as those
    # customers face carbon costs and switch to cleaner alternatives. Cost to the maker =
    # use_phase_Scope3 × carbon_price × USE_PHASE_INCIDENCE, reduced by how much the firm
    # pivots its product line to clean (capture). A cash-flow cost (routes once, distinct
    # from upstream Scope 3 which is in L3, and from own-ops Scope 1+2 in L1).
    l2_use_phase_by_year: Dict[int, float] = {y: 0.0 for y in horizon}
    _use_phase = getattr(asset, "scope3_use_phase_tco2", 0.0) or 0.0
    if _use_phase > 0 and 2 in enable_layers:
        _cap = strategy.capture_fraction if strategy is not None else 0.0
        _ngfs = get_ngfs_region(region)
        for y in horizon:
            price = get_carbon_price(scenario_id, y, _ngfs, region_iso3=region) * max(0.0, price_scale)
            l2_use_phase_by_year[y] = round(_use_phase * price * USE_PHASE_INCIDENCE * (1.0 - _cap), 2)

    # ── Financed-emissions transition exposure (financials) ─────────────────
    # For a lender/investor the material transition risk is its BOOK, not its offices. Screening
    # proxy: financed_emissions × carbon_price × FINANCED_INCIDENCE — the portfolio transition
    # risk transmitted to the institution (credit/stranding). Routed once; distinct from own-ops
    # Scope 1+2 (L1) and supply chain (L3). Needs PCAF portfolio data for a real figure.
    financed_by_year: Dict[int, float] = {y: 0.0 for y in horizon}
    _financed = getattr(asset, "financed_emissions_tco2", 0.0) or 0.0
    if _financed > 0 and 1 in enable_layers:
        _ngfs = get_ngfs_region(region)
        for y in horizon:
            price = get_carbon_price(scenario_id, y, _ngfs, region_iso3=region) * max(0.0, price_scale)
            financed_by_year[y] = round(_financed * price * FINANCED_INCIDENCE, 2)

    # ── Aggregate ──────────────────────────────────────────────────────────
    total_by_year = {
        y: l1_by_year[y] + l2_revenue_by_year[y] + l2_capex_by_year[y]
           + l2_use_phase_by_year[y] + l3_by_year[y] + l4_by_year[y]
           + financed_by_year[y]
        for y in horizon
    }

    breakdown = {
        "L1_carbon_opex": l1_by_year,
        "L2_revenue_erosion": l2_revenue_by_year,
        "L2_transition_capex": l2_capex_by_year,
        "L2_product_use_phase": l2_use_phase_by_year,
        "L2_impairment": l2_impairment_by_year,
        "L3_network_input_cost": l3_by_year,
        "L4_revenue_modifier": l4_by_year,
        "Financed_emissions_exposure": financed_by_year,
    }

    # ── Data-quality classification (audit trail) ───────────────────────────
    # Every result is at best a sector-proxy estimate unless firm data is supplied.
    # Degrading conditions (missing sector/revenue, scenario fallback, unknown
    # region) are flagged loudly so a $X built on proxies is never mistaken for a
    # $X built on firm data.
    dq_flags: List[str] = []
    if not asset.sector:
        dq_flags.append("no sector set → 'services' proxy (degraded)")
    if map_scenario_to_ngfs(scenario_id) != scenario_id:
        dq_flags.append(f"scenario '{scenario_id}' mapped to a carbon-price analog (proxy)")
    if get_ngfs_region(region) == "rest_of_world" and region not in ("", None):
        dq_flags.append(f"region '{region}' not classified → rest-of-world carbon-price band")
    if 3 in enable_layers or 4 in enable_layers:
        if asset.annual_revenue <= 0:
            dq_flags.append("no annual revenue → L3/L4 read zero (degraded)")
    if 4 in enable_layers and firm_cce_override is None:
        dq_flags.append("L4 uses sector-median CCExposure (no firm-level feed)")
    dq_flags.append("L1 pass-through & L3 intensities are sector medians")
    degraded = any("degraded" in f for f in dq_flags)
    firm_grade = (firm_cce_override is not None and asset.annual_revenue > 0 and bool(asset.sector))
    data_quality = "degraded" if degraded else ("firm" if firm_grade else "sector-proxy")
    if degraded:
        _log.warning("Asset %s: DEGRADED transition result — %s", asset.id,
                     "; ".join(f for f in dq_flags if "degraded" in f))

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
        data_quality=data_quality,
        data_quality_flags=dq_flags,
        strategy=strategy,
    )


def run_portfolio_transition(
    assets: List,
    scenario_ids: List[str],
    horizon: Optional[List[int]] = None,
    layer4_routing: str = ROUTE_WACC,
    elasticity: float = 1.0,
    enable_layers: tuple = (1, 2, 3, 4),
    scope3_mode: str = "auto",
    price_scale: float = 1.0,
    pass_through_scale: float = 1.0,
    l3_mode: str = "world",
    cascade: bool = False,
    cascade_theta: float = 0.02,
    cascade_contagion: float = 0.5,
    firm_cce_overrides: Optional[Dict[str, Dict[str, float]]] = None,
    carbon_inclusive_crossover: bool = False,
    non_fossil_base_fraction: float = 0.5,
    stranding_slope: Optional[float] = None,
    l3_partial_pass_through: bool = False,
    scope3_incidence: Optional[float] = None,
    scope2_mode: str = "auto",
    equity_weight: float = 0.6,
    debt_weight: float = 0.4,
    tax_rate: float = 0.25,
    adaptive: bool = True,
    ambition_override: Optional[float] = None,
    plan_coverage_by_asset: Optional[Dict[str, float]] = None,
    capex_schedule_by_asset: Optional[Dict[str, Dict[int, float]]] = None,
) -> Dict[str, List[TransitionAssetResult]]:
    """
    Run all assets × scenarios. Returns {scenario_id: [TransitionAssetResult, ...]}.

    firm_cce_overrides : optional {asset_id: {opportunity, regulatory, physical}} firm-level
    Sautner CCExposure, overriding the sector-median proxy in Layer 4.

    Layer 3 is computed per-asset from a SECTOR-TYPICAL shock vector (every sector
    pays carbon × pass-through on its typical emission intensity), reading off the
    focal sector's indirect input-cost exposure — NOT the asset's own L1 cost. For a
    portfolio-pooled cascade (memo's "bespoke add-on"), call propagate_carbon_shock
    directly with aggregate_sector_carbon_costs(all_layer1_results) as input.
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
                l3_mode=l3_mode, cascade=cascade,
                cascade_theta=cascade_theta, cascade_contagion=cascade_contagion,
                firm_cce_override=(firm_cce_overrides or {}).get(a.id),
                carbon_inclusive_crossover=carbon_inclusive_crossover,
                non_fossil_base_fraction=non_fossil_base_fraction,
                stranding_slope=stranding_slope,
                l3_partial_pass_through=l3_partial_pass_through,
                scope3_incidence=scope3_incidence,
                scope2_mode=scope2_mode,
                equity_weight=equity_weight,
                debt_weight=debt_weight,
                tax_rate=tax_rate,
                adaptive=adaptive,
                ambition_override=ambition_override,
                plan_coverage=(plan_coverage_by_asset or {}).get(a.id),
                capex_schedule_override=(capex_schedule_by_asset or {}).get(a.id),
            )
            out[sc].append(r)
    return out


@dataclass
class FirmRollup:
    firm_id: str
    business_lines: List[str]
    sectors: List[str]
    regions: List[str]
    annual_total_cost_usd: Dict[int, float]
    annual_impairment_usd: Dict[int, float]
    n_lines: int


def firm_rollup(results: List[TransitionAssetResult],
                assets: Optional[List] = None) -> Dict[str, FirmRollup]:
    """
    Group per-asset transition results into firm-level roll-ups by `firm_id`
    (falls back to the asset_id when no firm is set — a standalone entity is its
    own firm). Diversified, multi-region firms therefore get one consolidated
    view across their business lines.

    IMPORTANT (documented simplification): this is an INDEPENDENT sum of the
    business lines — it does NOT model group-level correlation, cross-subsidy,
    shared capital, or a single optimised group transition plan. Each line keeps
    its own (correct) sector- and region-specific positioning; the roll-up adds
    transparency, not portfolio interaction.
    """
    firm_of = {}
    if assets:
        for a in assets:
            firm_of[a.id] = getattr(a, "firm_id", "") or a.id
    horizon = results[0].horizon if results else []
    groups: Dict[str, List[TransitionAssetResult]] = {}
    for r in results:
        fid = firm_of.get(r.asset_id, r.asset_id)
        groups.setdefault(fid, []).append(r)

    out: Dict[str, FirmRollup] = {}
    for fid, rs in groups.items():
        cost = {y: sum(r.annual_total_cost_usd.get(y, 0.0) for r in rs) for y in horizon}
        imp = {y: sum(r.annual_impairment_usd.get(y, 0.0) for r in rs) for y in horizon}
        out[fid] = FirmRollup(
            firm_id=fid,
            business_lines=[r.asset_id for r in rs],
            sectors=sorted({r.sector for r in rs}),
            regions=sorted({r.region for r in rs}),
            annual_total_cost_usd=cost,
            annual_impairment_usd=imp,
            n_lines=len(rs),
        )
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
