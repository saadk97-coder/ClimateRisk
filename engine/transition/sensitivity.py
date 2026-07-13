"""
One-at-a-time sensitivity (tornado) for the transition engine: which assumption moves
the present value of transition cost the most? Complements the Monte-Carlo range (which
gives the spread) by attributing it to individual drivers.

Each driver is swung low/high while all others hold at base, and the resulting PV of
portfolio transition cost is recorded. Drivers reuse the engine's existing knobs
(carbon-price scale, pass-through scale, substitution elasticity, Scope-3 mode) plus the
discount rate applied at PV time.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional

from engine.transition.transition_engine import run_portfolio_transition, DEFAULT_HORIZON
from engine.transition.cc_exposure import ROUTE_CASHFLOWS


@dataclass
class TornadoBar:
    driver: str
    low_label: str
    high_label: str
    low_pv: float
    high_pv: float
    swing: float   # |high - low|


def _pv(series: Dict[int, float], base_year: int, discount: float) -> float:
    return sum(v / (1.0 + discount) ** (y - base_year) for y, v in series.items())


def _stream(r, target: str) -> Dict[int, float]:
    """Pick the cash-flow cost stream or the stranded-impairment stream."""
    return r.annual_impairment_usd if target == "impairment" else r.annual_total_cost_usd


def _portfolio_pv(assets, scenario, discount, base_year, target="cost", **kw) -> float:
    res = run_portfolio_transition(assets, [scenario], **kw)[scenario]
    return sum(_pv(_stream(r, target), base_year, discount) for r in res)


def tornado(
    assets: List, scenario: str, discount_rate: float = 0.09,
    layer4_routing: str = ROUTE_CASHFLOWS, enable_layers: tuple = (1, 2, 3, 4),
    scope3_mode: str = "full", target: str = "cost",
) -> dict:
    """
    One-at-a-time sensitivity tornado for one scenario.

    target : "cost" (default) swings drivers of the PV of transition CASH-FLOW
        cost; "impairment" swings drivers of the PV of stranded ASSET impairment
        (crossover trigger year, stranding slope, base). U1 — the impairment
        view widens the analysis beyond the price/pass-through drivers to the
        trigger-year and pathway/base assumptions that dominate stranding.

    Returns {base_pv, bars: [TornadoBar sorted by swing desc], target}.
    """
    horizon = DEFAULT_HORIZON
    base_year = min(horizon)
    common = dict(layer4_routing=layer4_routing, enable_layers=enable_layers)

    def pv(**kw):
        kw.setdefault("scope3_mode", scope3_mode)
        return _portfolio_pv(assets, scenario, discount_rate, base_year, target=target,
                             **common, **kw)

    base_pv = pv()
    bars: List[TornadoBar] = []

    def add(name, lo_label, hi_label, lo_pv, hi_pv):
        bars.append(TornadoBar(name, lo_label, hi_label, lo_pv, hi_pv, abs(hi_pv - lo_pv)))

    if target == "impairment":
        # U1 / R6 — trigger-year uncertainty: pure-LCOE crossover vs carbon-inclusive
        # crossover (a rising carbon price pulls the crossover — and stranding — earlier).
        add("Crossover trigger (carbon-incl.)", "pure LCOE", "carbon-incl.",
            pv(carbon_inclusive_crossover=False),
            pv(carbon_inclusive_crossover=True))
        # R7 — stranding diffusion slope (how fast impairment accrues once triggered).
        add("Stranding slope", "0.12 (slow)", "0.35 (fast)",
            pv(stranding_slope=0.12), pv(stranding_slope=0.35))
        # R1 — non-fossil impairment base (share of value tied to the incumbent tech).
        add("Non-fossil base share", "0.25", "0.75",
            pv(non_fossil_base_fraction=0.25), pv(non_fossil_base_fraction=0.75))
        # Carbon price ±30% (matters only via carbon-inclusive crossover — usually small).
        add("Carbon price ±30%", "−30%", "+30%",
            pv(price_scale=0.7, carbon_inclusive_crossover=True),
            pv(price_scale=1.3, carbon_inclusive_crossover=True))
        # Discount rate ±2pp
        res = run_portfolio_transition(assets, [scenario], scope3_mode=scope3_mode, **common)[scenario]
        add("Discount rate ±2pp", f"{(discount_rate+0.02)*100:.0f}%",
            f"{max(0,discount_rate-0.02)*100:.0f}%",
            sum(_pv(r.annual_impairment_usd, base_year, discount_rate + 0.02) for r in res),
            sum(_pv(r.annual_impairment_usd, base_year, max(0.0, discount_rate - 0.02)) for r in res))
        bars.sort(key=lambda b: b.swing, reverse=True)
        return {"base_pv": base_pv, "bars": bars, "target": target}

    # ---- target == "cost" (transition cash-flow PV) -----------------------
    add("Carbon price ±30%", "−30%", "+30%", pv(price_scale=0.7), pv(price_scale=1.3))
    add("Pass-through ±20%", "−20%", "+20%",
        pv(pass_through_scale=0.8), pv(pass_through_scale=1.2))
    # L3 partial pass-through: firm absorbs all upstream cost vs recovers its PT share.
    add("L3 input-cost pass-through", "full absorb", "partial",
        pv(l3_partial_pass_through=False), pv(l3_partial_pass_through=True))
    add("Substitution σ (1.0–2.5)", "σ=2.5", "σ=1.0",
        pv(elasticity=2.5), pv(elasticity=1.0))
    add("Scope-3 treatment", "auto", "full",
        pv(scope3_mode="auto"), pv(scope3_mode="full"))
    res = run_portfolio_transition(assets, [scenario], scope3_mode=scope3_mode, **common)[scenario]
    add("Discount rate ±2pp", f"{(discount_rate+0.02)*100:.0f}%",
        f"{max(0,discount_rate-0.02)*100:.0f}%",
        sum(_pv(r.annual_total_cost_usd, base_year, discount_rate + 0.02) for r in res),
        sum(_pv(r.annual_total_cost_usd, base_year, max(0.0, discount_rate - 0.02)) for r in res))
    bars.sort(key=lambda b: b.swing, reverse=True)
    return {"base_pv": base_pv, "bars": bars, "target": target}
