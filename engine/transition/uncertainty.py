"""
Monte-Carlo uncertainty for the transition-risk engine.

Single-point transition estimates hide the fact that the dominant drivers — the
carbon-price trajectory, cost pass-through, and network substitution — are
themselves uncertain. This module re-runs the four-layer engine over N draws,
perturbing those drivers, and returns the distribution of the present value of
transition cost and stranded impairment.

Perturbation channels (per draw, shared across the portfolio for a scenario so
correlated policy uncertainty is preserved):
  - price_scale        ~ LogNormal(0, price_cv)      — carbon-price / policy path
  - pass_through_scale ~ Normal(1, pt_cv) clamped>=0 — cost incidence
  - elasticity         ~ Uniform(el_lo, el_hi)       — L3 substitution (Papageorgiou range)

Layer-2 impairment carries its own Lafond band in learning_curves; that channel
is not resampled here (documented limitation) — the focus is the cash-flow cost
and its PV.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np

from engine.transition.transition_engine import run_portfolio_transition, DEFAULT_HORIZON
from engine.transition.cc_exposure import ROUTE_WACC


@dataclass
class MCConfig:
    draws: int = 400
    price_cv: float = 0.20          # log-normal sigma on the carbon price
    pt_cv: float = 0.10             # normal CV on pass-through
    elasticity_lo: float = 1.0
    elasticity_hi: float = 2.5
    seed: Optional[int] = 42


@dataclass
class MCResult:
    scenario_id: str
    draws: int
    pv_cost: np.ndarray             # PV of transition cash-flow cost per draw
    pv_impairment: np.ndarray       # PV of stranded impairment per draw
    base_pv_cost: float             # deterministic base (all scales = 1)
    base_pv_impairment: float

    def pct(self, arr: np.ndarray, p: float) -> float:
        return float(np.percentile(arr, p)) if len(arr) else 0.0

    def summary(self) -> Dict[str, Dict[str, float]]:
        out = {}
        for name, arr, base in (
            ("transition_cost", self.pv_cost, self.base_pv_cost),
            ("stranded_impairment", self.pv_impairment, self.base_pv_impairment),
        ):
            out[name] = {
                "base": base,
                "p5": self.pct(arr, 5), "p50": self.pct(arr, 50), "p95": self.pct(arr, 95),
                "mean": float(np.mean(arr)) if len(arr) else 0.0,
            }
        return out


def _pv(series: Dict[int, float], base_year: int, discount: float) -> float:
    # End-of-year convention (y − base_year + 1), matching dcf_engine and
    # transition_dcf so every transition PV in the app is discounted identically.
    return sum(v / (1.0 + discount) ** (y - base_year + 1) for y, v in series.items())


def _portfolio_pv(results, base_year: int, discount: float):
    cost = sum(_pv(r.annual_total_cost_usd, base_year, discount) for r in results)
    imp = sum(_pv(r.annual_impairment_usd, base_year, discount) for r in results)
    return cost, imp


def run_monte_carlo(
    assets: List,
    scenario_id: str,
    discount_rate: float = 0.09,
    horizon: Optional[List[int]] = None,
    layer4_routing: str = ROUTE_WACC,
    enable_layers: tuple = (1, 2, 3, 4),
    scope3_mode: str = "auto",
    config: Optional[MCConfig] = None,
) -> MCResult:
    """Run the four-layer model over `config.draws` perturbed samples for one scenario."""
    cfg = config or MCConfig()
    horizon = horizon or DEFAULT_HORIZON
    base_year = min(horizon)
    rng = np.random.default_rng(cfg.seed)

    # deterministic base
    base = run_portfolio_transition(
        assets, [scenario_id], horizon=horizon, layer4_routing=layer4_routing,
        elasticity=1.0, enable_layers=enable_layers, scope3_mode=scope3_mode,
    )[scenario_id]
    base_cost, base_imp = _portfolio_pv(base, base_year, discount_rate)

    price_scales = rng.lognormal(mean=0.0, sigma=cfg.price_cv, size=cfg.draws)
    pt_scales = np.clip(rng.normal(1.0, cfg.pt_cv, size=cfg.draws), 0.0, None)
    elasticities = rng.uniform(cfg.elasticity_lo, cfg.elasticity_hi, size=cfg.draws)

    pv_cost = np.empty(cfg.draws)
    pv_imp = np.empty(cfg.draws)
    for i in range(cfg.draws):
        res = run_portfolio_transition(
            assets, [scenario_id], horizon=horizon, layer4_routing=layer4_routing,
            elasticity=float(elasticities[i]), enable_layers=enable_layers,
            scope3_mode=scope3_mode,
            price_scale=float(price_scales[i]), pass_through_scale=float(pt_scales[i]),
        )[scenario_id]
        c, m = _portfolio_pv(res, base_year, discount_rate)
        pv_cost[i] = c
        pv_imp[i] = m

    return MCResult(
        scenario_id=scenario_id, draws=cfg.draws,
        pv_cost=pv_cost, pv_impairment=pv_imp,
        base_pv_cost=base_cost, base_pv_impairment=base_imp,
    )
