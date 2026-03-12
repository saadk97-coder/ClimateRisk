"""
Annual 2025–2050 EAD computation and present-value discounting.

For each year in the analysis window, applies the scenario-specific hazard
multiplier to pre-fetched baseline intensities, runs the vulnerability curve
and EAD integration, then discounts to a base year.

Calculation trace (auditable step by step):
  1. baseline_intensity[rp]          ← from ISIMIP API or regional fallback
  2. warming_c                        ← scenario warming trajectory (interpolated)
  3. hazard_multiplier                ← IPCC AR6 hazard scaling (see scenario_model.py)
  4. adjusted_intensity[rp]           ← baseline × multiplier (flood: minus elevation)
  5. damage_fraction[rp]              ← vulnerability curve (HAZUS/JRC/Syphard/IEA)
  6. EAD                              ← ∫ damage(aep) d(aep) via trapezoidal rule
  7. PV                               ← EAD / (1 + r)^(year - base_year)
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional

from engine.asset_model import Asset
from engine.scenario_model import get_scenario_multipliers, get_warming
from engine.ead_calculator import calc_ead_from_intensities


DEFAULT_YEARS = list(range(2025, 2051))
BASE_YEAR = 2025


def compute_annual_damages(
    asset: Asset,
    scenario_id: str,
    hazard_data: Dict[str, dict],
    discount_rate: float,
    years: Optional[List[int]] = None,
    base_year: int = BASE_YEAR,
) -> pd.DataFrame:
    """
    Compute per-hazard annual EAD and PV for every year in the window.

    Parameters
    ----------
    asset         : Asset dataclass
    scenario_id   : scenario key from scenario_model.SCENARIOS
    hazard_data   : {hazard: {return_periods, intensities, source}} — pre-fetched
    discount_rate : annual discount rate (e.g. 0.035)
    years         : list of integer years (default 2025–2050)
    base_year     : reference year for PV discounting (default 2025)

    Returns
    -------
    DataFrame with columns:
        year, hazard, warming_c, multiplier, ead, pv,
        ead_pct_value, baseline_intensity_rp100, adjusted_intensity_rp100,
        damage_fraction_rp100, data_source
    """
    if years is None:
        years = DEFAULT_YEARS

    rows = []
    for hazard, hdata in hazard_data.items():
        rp = np.array(hdata["return_periods"], dtype=float)
        base_intens = np.array(hdata["intensities"], dtype=float)
        source = hdata.get("source", "fallback_baseline")

        # Reference RP100 for audit readability
        rp100_idx = int(np.argmin(np.abs(rp - 100))) if len(rp) > 0 else 0

        for year in years:
            warming_c = get_warming(scenario_id, year)

            # Scenario multiplier — skip if data is already SSP-specific (ISIMIP)
            # to avoid double-counting the climate signal
            if source.startswith("isimip"):
                mult = 1.0
            else:
                from engine.hazard_fetcher import get_region_zone
                region_zone = get_region_zone(asset.region) if hasattr(asset, 'region') else "global"
                mult = get_scenario_multipliers(scenario_id, year, hazard, region_zone)

            # Adjust intensity — first-floor height correction for flood and coastal flood
            intens = base_intens.copy()
            if hazard in ("flood", "coastal_flood"):
                intens = np.clip(intens - asset.first_floor_height_m, 0.0, None)

            ead, damage_fracs = calc_ead_from_intensities(
                rp, intens, asset.asset_type, hazard, asset.replacement_value, mult
            )
            pv = ead / (1.0 + discount_rate) ** (year - base_year)

            rows.append({
                "asset_id": asset.id,
                "asset_name": asset.name,
                "scenario_id": scenario_id,
                "year": year,
                "hazard": hazard,
                "warming_c": round(warming_c, 3),
                "multiplier": round(mult, 4),
                "ead": round(ead, 2),
                "pv": round(pv, 2),
                "ead_pct_value": round(ead / asset.replacement_value * 100, 5) if asset.replacement_value > 0 else 0.0,
                "baseline_intensity_rp100": round(float(base_intens[rp100_idx]), 4),
                "adjusted_intensity_rp100": round(float(intens[rp100_idx] * mult), 4),
                "damage_fraction_rp100": round(float(damage_fracs[rp100_idx]), 5),
                "data_source": source,
            })

    return pd.DataFrame(rows)


def compute_portfolio_annual_damages(
    assets: List[Asset],
    scenario_ids: List[str],
    hazard_data_all: Dict[str, dict],
    discount_rate: float,
    years: Optional[List[int]] = None,
    base_year: int = BASE_YEAR,
    progress_callback=None,
    hazard_data_by_scenario: Optional[Dict[str, Dict[str, dict]]] = None,
) -> pd.DataFrame:
    """
    Run annual damage computation for all assets × scenarios.

    Parameters
    ----------
    hazard_data_all         : {asset_id: {hazard: data}} — shared across scenarios (legacy)
    hazard_data_by_scenario : {scenario_id: {asset_id: {hazard: data}}} — per-scenario
                              If provided, takes precedence over hazard_data_all for each
                              scenario that has data.  This ensures ISIMIP data (which
                              already embeds the SSP climate signal) uses the correct
                              SSP-specific baseline per scenario.

    Returns a single tidy DataFrame.
    """
    all_rows = []
    total = len(assets) * len(scenario_ids)
    done = 0

    for asset in assets:
        for scenario_id in scenario_ids:
            # Pick scenario-specific hazard data if available, else shared
            if hazard_data_by_scenario and scenario_id in hazard_data_by_scenario:
                hdata = hazard_data_by_scenario[scenario_id].get(asset.id, {})
            else:
                hdata = hazard_data_all.get(asset.id, {})

            if not hdata:
                done += 1
                if progress_callback:
                    progress_callback(done / total)
                continue

            df = compute_annual_damages(asset, scenario_id, hdata, discount_rate, years, base_year)
            all_rows.append(df)
            done += 1
            if progress_callback:
                progress_callback(done / total)

    if all_rows:
        return pd.concat(all_rows, ignore_index=True)
    return pd.DataFrame()


def summarise_annual(df: pd.DataFrame, group_by_hazard: bool = False) -> pd.DataFrame:
    """
    Aggregate annual EAD / PV across assets for a scenario.

    Parameters
    ----------
    df            : output of compute_portfolio_annual_damages
    group_by_hazard : if True, break down by hazard; else sum all hazards

    Returns
    -------
    DataFrame: year, (hazard), total_ead, total_pv
    """
    if df.empty:
        return pd.DataFrame()

    group_cols = ["scenario_id", "year"]
    if group_by_hazard:
        group_cols.append("hazard")

    agg = df.groupby(group_cols, as_index=False).agg(
        total_ead=("ead", "sum"),
        total_pv=("pv", "sum"),
    )
    return agg


def pv_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return total PV of damages per scenario (sum over all years 2025–2050).
    """
    if df.empty:
        return pd.DataFrame()
    return (
        df.groupby(["scenario_id", "asset_id"], as_index=False)
        .agg(total_pv_damages=("pv", "sum"), total_ead_mean=("ead", "mean"))
    )
