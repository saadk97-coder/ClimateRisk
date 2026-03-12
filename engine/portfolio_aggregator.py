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

    # Correlation-adjusted portfolio risk using proper variance decomposition.
    # EAD is the mean loss; we estimate per-asset loss std dev as CV * EAD,
    # where CV (coefficient of variation) is typical for cat loss distributions.
    CV_LOSS = 2.0  # loss distribution CV — conservative cat-model estimate

    n = len(subset)
    portfolio_sigma = 0.0
    undiversified_sigma = 0.0

    if n == 1:
        portfolio_ead = sum_ead
    else:
        eads = np.array([r.total_ead for r in subset])
        sigmas = eads * CV_LOSS  # per-asset loss standard deviation

        # Build correlation matrix using region zone (ISO3 → zone key)
        from engine.hazard_fetcher import get_region_zone
        asset_regions = [get_region_zone(getattr(r, 'region', 'global')) for r in subset]
        corr_matrix = np.full((n, n), DIFF_REGION_CORR)
        for i in range(n):
            corr_matrix[i, i] = 1.0
            for j in range(i + 1, n):
                if asset_regions[i] == asset_regions[j]:
                    corr_matrix[i, j] = SAME_REGION_CORR
                    corr_matrix[j, i] = SAME_REGION_CORR

        # Portfolio variance: σ_p² = Σ_i Σ_j ρ_ij σ_i σ_j
        var_portfolio = float(sigmas @ corr_matrix @ sigmas)
        portfolio_sigma = np.sqrt(max(var_portfolio, 0.0))
        undiversified_sigma = float(np.sum(sigmas))

        # Portfolio EAD (mean) is simply the sum — means add linearly
        portfolio_ead = sum_ead

    # Diversification benefit is on the risk (volatility), not the mean
    diversification_benefit = undiversified_sigma - portfolio_sigma if n > 1 else 0.0

    return {
        "n_assets": n,
        "total_value": total_value,
        "sum_individual_ead": sum_ead,
        "portfolio_ead": portfolio_ead,
        "ead_pct": portfolio_ead / total_value * 100 if total_value > 0 else 0.0,
        "diversification_benefit": diversification_benefit,
        "portfolio_sigma": portfolio_sigma,
        "undiversified_sigma": undiversified_sigma,
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
