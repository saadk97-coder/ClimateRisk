"""
Climate-Adjusted Discounted Cash Flow (DCF) Engine.

Implements the framework described in:
  BSR (Business for Social Responsibility), "From Climate Science to Corporate Strategy"
  https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf

  Also consistent with TCFD guidance on financial impact quantification:
  https://www.fsb-tcfd.org/recommendations/

Methodology
-----------
Standard DCF:
  NPV_base = Σ_{t=0}^{T} CF_t / (1+WACC)^t + TV / (1+WACC)^T

Climate-adjusted DCF:
  CF_t_adj = CF_t − ΔDamage_t + ΔSavings_t (avoided damage from adaptation)
  NPV_climate = Σ_{t=0}^{T} CF_t_adj / (1+WACC)^t + TV_adj / (1+WACC)^T

Climate risk premium approach (optional):
  WACC_climate = WACC + λ × physical_risk_score
  Where λ is the climate risk premium loading (user-defined)

Scenario-weighted NPV:
  E[NPV] = Σ_s P(s) × NPV(s)
  Where P(s) is the user-assigned probability for scenario s.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class DCFInputs:
    """Base-case DCF inputs for a company / asset portfolio."""
    name: str
    base_year: int = 2025
    forecast_years: int = 10          # number of explicit forecast years
    terminal_growth_rate: float = 0.02
    wacc: float = 0.08
    climate_risk_premium: float = 0.0  # added to WACC for climate-adjusted runs
    # Annual base-case free cash flows (list of length forecast_years)
    # If empty, a simple perpetuity from asset value is used
    cashflows: List[float] = field(default_factory=list)
    # Optional: initial portfolio/asset replacement value as proxy for terminal value
    asset_value: float = 0.0


@dataclass
class DCFResult:
    scenario_id: str
    label: str
    npv_base: float
    npv_climate: float
    npv_climate_adapted: float
    total_pv_damages: float          # PV of all climate damages
    total_pv_avoided: float          # PV of damages avoided by adaptation
    total_adaptation_capex: float
    npv_delta: float                 # npv_climate - npv_base (negative = impairment)
    npv_delta_pct: float
    annual_detail: pd.DataFrame      # year, cf, damage, saving, adj_cf, disc_factor, pv_adj_cf


def _discount_factors(years: np.ndarray, wacc: float) -> np.ndarray:
    return 1.0 / (1.0 + wacc) ** years


def _terminal_value(last_cf: float, growth: float, wacc: float) -> float:
    if wacc <= growth:
        return last_cf * 20  # cap to prevent explosion
    return last_cf * (1 + growth) / (wacc - growth)


def compute_base_dcf(inputs: DCFInputs) -> float:
    """Compute standard base-case NPV."""
    if not inputs.cashflows and inputs.asset_value > 0:
        # Simplified: treat asset_value as terminal value already at base_year
        return inputs.asset_value
    if not inputs.cashflows:
        return 0.0

    cfs = np.array(inputs.cashflows, dtype=float)
    years = np.arange(1, len(cfs) + 1, dtype=float)
    disc = _discount_factors(years, inputs.wacc)
    npv = float(np.sum(cfs * disc))

    # Terminal value after explicit forecast period
    tv = _terminal_value(cfs[-1], inputs.terminal_growth_rate, inputs.wacc)
    npv += tv / (1.0 + inputs.wacc) ** len(cfs)
    return npv


def compute_climate_dcf(
    inputs: DCFInputs,
    annual_damages_df: pd.DataFrame,  # from annual_risk.compute_portfolio_annual_damages
    scenario_id: str,
    adaptation_savings_df: Optional[pd.DataFrame] = None,  # year → avoided_ead
    total_adaptation_capex: float = 0.0,
) -> DCFResult:
    """
    Compute climate-adjusted NPV.

    Parameters
    ----------
    inputs               : DCFInputs with base case financials
    annual_damages_df    : tidy DataFrame with columns year, ead, scenario_id
    scenario_id          : which scenario to use from annual_damages_df
    adaptation_savings_df: optional year-level avoided damage savings
    total_adaptation_capex: upfront adaptation investment cost

    Returns
    -------
    DCFResult with full annual breakdown
    """
    from engine.scenario_model import SCENARIOS
    sc_label = SCENARIOS.get(scenario_id, {}).get("label", scenario_id)

    wacc_adj = inputs.wacc + inputs.climate_risk_premium

    # Annual damage stream (sum across hazards and assets for this scenario)
    sc_damages = annual_damages_df[annual_damages_df["scenario_id"] == scenario_id].copy()
    damage_by_year = (
        sc_damages.groupby("year")["ead"].sum().reindex(
            range(inputs.base_year, inputs.base_year + inputs.forecast_years + 1), fill_value=0.0
        )
    )

    # Adaptation savings stream
    savings_by_year = pd.Series(0.0, index=damage_by_year.index)
    if adaptation_savings_df is not None and not adaptation_savings_df.empty:
        s = adaptation_savings_df.set_index("year")["avoided_ead"]
        for y in savings_by_year.index:
            if y in s.index:
                savings_by_year[y] = float(s[y])

    # Build annual detail table
    rows = []
    years = sorted(damage_by_year.index)
    base_cfs = list(inputs.cashflows) if inputs.cashflows else [0.0] * inputs.forecast_years

    npv_base = compute_base_dcf(inputs)

    pv_damages_total = 0.0
    pv_avoided_total = 0.0
    pv_adj_cf_total = 0.0

    for i, year in enumerate(years[:inputs.forecast_years]):
        t = year - inputs.base_year + 1
        disc = 1.0 / (1.0 + wacc_adj) ** t
        cf = base_cfs[i] if i < len(base_cfs) else 0.0
        damage = float(damage_by_year.get(year, 0.0))
        saving = float(savings_by_year.get(year, 0.0))
        adj_cf = cf - damage + saving
        pv_adj = adj_cf * disc

        pv_damages_total += damage / (1.0 + wacc_adj) ** t
        pv_avoided_total += saving / (1.0 + wacc_adj) ** t
        pv_adj_cf_total += pv_adj

        rows.append({
            "year": year,
            "base_cf": round(cf, 2),
            "climate_damage": round(damage, 2),
            "adaptation_saving": round(saving, 2),
            "adjusted_cf": round(adj_cf, 2),
            "discount_factor": round(disc, 6),
            "pv_adjusted_cf": round(pv_adj, 2),
        })

    # Add terminal value to climate-adjusted NPV
    if rows:
        last_adj_cf = rows[-1]["adjusted_cf"]
        tv_adj = _terminal_value(last_adj_cf, inputs.terminal_growth_rate, wacc_adj)
        t_final = inputs.forecast_years
        npv_climate = pv_adj_cf_total + tv_adj / (1.0 + wacc_adj) ** t_final
        npv_climate_adapted = npv_climate  # same — savings already included in adj_cf
    else:
        npv_climate = npv_base - pv_damages_total
        npv_climate_adapted = npv_climate + pv_avoided_total

    # Deduct upfront adaptation capex
    npv_climate_adapted -= total_adaptation_capex

    npv_delta = npv_climate - npv_base
    npv_delta_pct = (npv_delta / abs(npv_base) * 100) if npv_base != 0 else 0.0

    detail_df = pd.DataFrame(rows)

    return DCFResult(
        scenario_id=scenario_id,
        label=sc_label,
        npv_base=round(npv_base, 2),
        npv_climate=round(npv_climate, 2),
        npv_climate_adapted=round(npv_climate_adapted, 2),
        total_pv_damages=round(pv_damages_total, 2),
        total_pv_avoided=round(pv_avoided_total, 2),
        total_adaptation_capex=round(total_adaptation_capex, 2),
        npv_delta=round(npv_delta, 2),
        npv_delta_pct=round(npv_delta_pct, 3),
        annual_detail=detail_df,
    )


def scenario_weighted_npv(
    dcf_results: List[DCFResult],
    weights: Dict[str, float],
) -> Tuple[float, float]:
    """
    Compute probability-weighted NPV across scenarios.

    Parameters
    ----------
    dcf_results : list of DCFResult
    weights     : {scenario_id: probability} — must sum to 1.0

    Returns
    -------
    (weighted_npv_climate, weighted_npv_adapted)
    """
    total_w = sum(weights.values())
    w_climate = sum(
        weights.get(r.scenario_id, 0.0) / total_w * r.npv_climate
        for r in dcf_results
    )
    w_adapted = sum(
        weights.get(r.scenario_id, 0.0) / total_w * r.npv_climate_adapted
        for r in dcf_results
    )
    return w_climate, w_adapted
