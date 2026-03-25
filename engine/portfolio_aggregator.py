"""
Portfolio aggregation: correlation-adjusted rollup of asset-level EADs.
"""

import numpy as np
import pandas as pd
from typing import List, Dict

from engine.correlation import (
    HAZARD_CORRELATION_SPECS,
    haversine_km,
    hazard_pair_correlation,
    portfolio_dependence_note,
)
from engine.damage_engine import AssetResult

CV_LOSS = 2.0


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
            "lat": getattr(r, "lat", np.nan),
            "lon": getattr(r, "lon", np.nan),
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

    n = len(subset)
    portfolio_sigma = 0.0
    undiversified_sigma = 0.0
    variance_by_hazard = {}

    if n == 1:
        portfolio_ead = sum_ead
    else:
        asset_coords = [(float(getattr(r, "lat", 0.0) or 0.0), float(getattr(r, "lon", 0.0) or 0.0)) for r in subset]
        distance_matrix = np.zeros((n, n), dtype=float)
        for i in range(n):
            distance_matrix[i, i] = 0.0
            for j in range(i + 1, n):
                distance_km = haversine_km(
                    asset_coords[i][0],
                    asset_coords[i][1],
                    asset_coords[j][0],
                    asset_coords[j][1],
                )
                distance_matrix[i, j] = distance_km
                distance_matrix[j, i] = distance_km

        for hazard in sorted(all_hazards):
            hazard_eads = np.array(
                [
                    r.hazard_results[hazard].ead if hazard in r.hazard_results else 0.0
                    for r in subset
                ],
                dtype=float,
            )
            if not np.any(hazard_eads):
                continue

            sigmas = hazard_eads * CV_LOSS
            corr_matrix = np.eye(n, dtype=float)
            for i in range(n):
                for j in range(i + 1, n):
                    rho = hazard_pair_correlation(hazard, distance_matrix[i, j])
                    corr_matrix[i, j] = rho
                    corr_matrix[j, i] = rho

            hazard_variance = float(sigmas @ corr_matrix @ sigmas)
            variance_by_hazard[hazard] = hazard_variance
            undiversified_sigma += float(np.sum(sigmas))

        portfolio_sigma = np.sqrt(max(sum(variance_by_hazard.values()), 0.0))
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
        "variance_by_hazard": {hazard: float(value) for hazard, value in variance_by_hazard.items()},
        "correlation_method": portfolio_dependence_note(),
        "hazard_correlation_specs": {
            hazard: {
                "scale_km": spec["scale_km"],
                "floor": spec["floor"],
                "label": spec["label"],
            }
            for hazard, spec in HAZARD_CORRELATION_SPECS.items()
            if hazard != "default"
        },
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
