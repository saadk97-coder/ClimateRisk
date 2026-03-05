"""
Portfolio aggregation: correlation-adjusted rollup of asset-level EADs.
"""

import numpy as np
import pandas as pd
from typing import List, Dict
from engine.damage_engine import AssetResult

# Inter-asset hazard correlation assumptions (conservative)
# Same region + same hazard → higher correlation
SAME_REGION_CORR = 0.60
DIFF_REGION_CORR = 0.15


def results_to_dataframe(results: List[AssetResult]) -> pd.DataFrame:
    """Flatten list of AssetResult into a tidy DataFrame."""
    rows = []
    for r in results:
        row = {
            "asset_id": r.asset_id,
            "asset_name": r.asset_name,
            "asset_value": r.asset_value,
            "scenario_id": r.scenario_id,
            "year": r.year,
            "total_ead": r.total_ead,
            "total_ead_pct": r.total_ead_pct * 100,
        }
        for hazard, hr in r.hazard_results.items():
            row[f"ead_{hazard}"] = hr.ead
            row[f"df_{hazard}"] = hr.ead_pct_value * 100
            row[f"source_{hazard}"] = hr.data_source
        rows.append(row)
    return pd.DataFrame(rows)


def aggregate_portfolio(
    results: List[AssetResult],
    scenario_id: str,
    year: int,
) -> Dict:
    """
    Return portfolio-level summary for a given scenario/year.

    Returns
    -------
    dict with keys: total_value, total_ead, ead_pct, ead_by_hazard,
                    diversification_benefit, n_assets
    """
    subset = [r for r in results if r.scenario_id == scenario_id and r.year == year]
    if not subset:
        return {}

    total_value = sum(r.asset_value for r in subset)
    sum_ead = sum(r.total_ead for r in subset)

    # Collect per-hazard EADs
    all_hazards = set()
    for r in subset:
        all_hazards.update(r.hazard_results.keys())

    ead_by_hazard = {}
    for hazard in all_hazards:
        ead_by_hazard[hazard] = sum(
            r.hazard_results[hazard].ead for r in subset if hazard in r.hazard_results
        )

    # Simplified correlation-adjusted portfolio EAD
    n = len(subset)
    if n == 1:
        portfolio_ead = sum_ead
    else:
        # Assume uniform correlation ρ between assets
        rho = SAME_REGION_CORR
        # Var(portfolio) ≈ Σ σi² + ρ Σ_{i≠j} σi σj
        # Use EAD as proxy for σ (loss std)
        eads = np.array([r.total_ead for r in subset])
        var_undiversified = np.sum(eads**2)
        var_cross = rho * (np.sum(eads)**2 - np.sum(eads**2))
        var_portfolio = var_undiversified + var_cross
        portfolio_ead = np.sqrt(max(var_portfolio, 0.0))
        # Cap at undiversified sum
        portfolio_ead = min(portfolio_ead, sum_ead)

    diversification_benefit = sum_ead - portfolio_ead if n > 1 else 0.0

    return {
        "n_assets": n,
        "total_value": total_value,
        "sum_individual_ead": sum_ead,
        "portfolio_ead": portfolio_ead,
        "ead_pct": portfolio_ead / total_value * 100 if total_value > 0 else 0.0,
        "diversification_benefit": diversification_benefit,
        "ead_by_hazard": ead_by_hazard,
    }


def scenario_comparison_table(
    results: List[AssetResult],
    scenario_ids: List[str],
    years: List[int],
) -> pd.DataFrame:
    """Return wide-format table: rows=scenario, cols=year, values=portfolio EAD."""
    rows = []
    for sc in scenario_ids:
        row = {"scenario_id": sc}
        for yr in years:
            agg = aggregate_portfolio(results, sc, yr)
            row[str(yr)] = agg.get("portfolio_ead", 0.0)
        rows.append(row)
    return pd.DataFrame(rows)
