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


def _portfolio_pv(assets, scenario, discount, base_year, **kw) -> float:
    res = run_portfolio_transition(assets, [scenario], **kw)[scenario]
    return sum(_pv(r.annual_total_cost_usd, base_year, discount) for r in res)


def tornado(
    assets: List, scenario: str, discount_rate: float = 0.09,
    layer4_routing: str = ROUTE_CASHFLOWS, enable_layers: tuple = (1, 2, 3, 4),
    scope3_mode: str = "full",
) -> dict:
    """Return {base_pv, bars: [TornadoBar sorted by swing desc]} for one scenario."""
    horizon = DEFAULT_HORIZON
    base_year = min(horizon)
    common = dict(layer4_routing=layer4_routing, enable_layers=enable_layers)

    base_pv = _portfolio_pv(assets, scenario, discount_rate, base_year,
                            scope3_mode=scope3_mode, **common)

    bars: List[TornadoBar] = []

    def add(name, lo_label, hi_label, lo_pv, hi_pv):
        bars.append(TornadoBar(name, lo_label, hi_label, lo_pv, hi_pv, abs(hi_pv - lo_pv)))

    # Carbon price ±30%
    add("Carbon price ±30%", "−30%", "+30%",
        _portfolio_pv(assets, scenario, discount_rate, base_year, scope3_mode=scope3_mode,
                      price_scale=0.7, **common),
        _portfolio_pv(assets, scenario, discount_rate, base_year, scope3_mode=scope3_mode,
                      price_scale=1.3, **common))

    # Pass-through ±20%
    add("Pass-through ±20%", "−20%", "+20%",
        _portfolio_pv(assets, scenario, discount_rate, base_year, scope3_mode=scope3_mode,
                      pass_through_scale=0.8, **common),
        _portfolio_pv(assets, scenario, discount_rate, base_year, scope3_mode=scope3_mode,
                      pass_through_scale=1.2, **common))

    # Substitution elasticity σ (higher σ dampens network propagation → lower cost)
    add("Substitution σ (1.0–2.5)", "σ=2.5", "σ=1.0",
        _portfolio_pv(assets, scenario, discount_rate, base_year, scope3_mode=scope3_mode,
                      elasticity=2.5, **common),
        _portfolio_pv(assets, scenario, discount_rate, base_year, scope3_mode=scope3_mode,
                      elasticity=1.0, **common))

    # Scope-3 treatment (full vs auto)
    add("Scope-3 treatment", "auto", "full",
        _portfolio_pv(assets, scenario, discount_rate, base_year, scope3_mode="auto", **common),
        _portfolio_pv(assets, scenario, discount_rate, base_year, scope3_mode="full", **common))

    # Discount rate ±2pp (recompute PV on the base results)
    res = run_portfolio_transition(assets, [scenario], scope3_mode=scope3_mode, **common)[scenario]
    lo_pv = sum(_pv(r.annual_total_cost_usd, base_year, discount_rate + 0.02) for r in res)
    hi_pv = sum(_pv(r.annual_total_cost_usd, base_year, max(0.0, discount_rate - 0.02)) for r in res)
    add("Discount rate ±2pp", f"{(discount_rate+0.02)*100:.0f}%", f"{max(0,discount_rate-0.02)*100:.0f}%",
        lo_pv, hi_pv)

    bars.sort(key=lambda b: b.swing, reverse=True)
    return {"base_pv": base_pv, "bars": bars}
