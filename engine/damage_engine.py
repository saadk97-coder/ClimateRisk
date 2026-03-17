"""
Damage engine: orchestrates per-asset, per-hazard, per-scenario EAD calculation.
"""

import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from engine.asset_model import Asset
from engine.scenario_model import SCENARIOS, get_scenario_multipliers, get_slr_additive
from engine.hazard_fetcher import fetch_all_hazards
from engine.ead_calculator import calc_ead_from_intensities, calc_ead, STANDARD_RETURN_PERIODS
from engine.impact_functions import get_damage_fraction

SUPPORTED_HAZARDS = ["flood", "wind", "wildfire", "heat", "coastal_flood", "water_stress"]


@dataclass
class AssetHazardResult:
    asset_id: str
    hazard: str
    scenario_id: str
    year: int
    return_periods: List[float]
    intensities: List[float]
    damage_fractions: List[float]
    ead: float
    ead_pct_value: float
    data_source: str
    hazard_multiplier: float


@dataclass
class AssetResult:
    asset_id: str
    asset_name: str
    asset_value: float
    scenario_id: str
    year: int
    total_ead: float
    total_ead_pct: float
    hazard_results: Dict[str, AssetHazardResult] = field(default_factory=dict)
    region: str = "global"  # ISO3 country code for correlation grouping


def _get_hazards_for_asset(asset: Asset) -> List[str]:
    from engine.asset_model import load_asset_types
    catalog = load_asset_types()
    atype = catalog.get(asset.asset_type, {})
    hazards = list(atype.get("hazards", SUPPORTED_HAZARDS))

    # Dynamically add coastal_flood for any asset within the coastal zone
    if "coastal_flood" not in hazards:
        try:
            from engine.coastal import is_coastal
            if is_coastal(asset.lat, asset.lon):
                hazards.append("coastal_flood")
        except Exception:
            pass

    return hazards


def run_asset_scenario(
    asset: Asset,
    scenario_id: str,
    year: int,
    hazard_overrides: Optional[Dict[str, dict]] = None,
    run_uncertainty: bool = False,
) -> AssetResult:
    """
    Run damage calculation for a single asset under a single scenario/year.
    """
    scenario = SCENARIOS[scenario_id]
    ssp = scenario["ssp"]

    # Map year to ISIMIP time period string
    if year <= 2040:
        time_period = "2021_2040"
    elif year <= 2060:
        time_period = "2041_2060"
    else:
        time_period = "2061_2080"

    hazards = _get_hazards_for_asset(asset)

    # Fetch hazard intensities
    if hazard_overrides:
        hazard_data = {}
        for h in hazards:
            if h in hazard_overrides:
                hazard_data[h] = hazard_overrides[h]
            else:
                from engine.hazard_fetcher import fetch_hazard_intensities
                rp, intens, src = fetch_hazard_intensities(
                    asset.lat, asset.lon, h, asset.region, ssp, time_period,
                    terrain_elevation_asl_m=getattr(asset, "terrain_elevation_asl_m", 0.0),
                    asset_type=asset.asset_type,
                )
                hazard_data[h] = {
                    "return_periods": rp.tolist(),
                    "intensities": intens.tolist(),
                    "source": src,
                }
    else:
        hazard_data = fetch_all_hazards(
            asset.lat, asset.lon, asset.region, hazards, ssp, time_period,
            terrain_elevation_asl_m=getattr(asset, "terrain_elevation_asl_m", 0.0),
            asset_type=asset.asset_type,
        )

    # Apply elevation adjustment to flood intensity
    hazard_results = {}
    total_ead = 0.0
    from engine.hazard_fetcher import get_region_zone
    region_zone = get_region_zone(asset.region)

    for hazard, hdata in hazard_data.items():
        rp = np.array(hdata["return_periods"], dtype=float)
        intens = np.array(hdata["intensities"], dtype=float)
        source = hdata["source"]

        # Scenario hazard multiplier — applied uniformly to ALL sources.
        mult = get_scenario_multipliers(scenario_id, year, hazard, region_zone)

        if hazard == "coastal_flood":
            # Correct order: scale baseline by storminess, ADD SLR, SUBTRACT freeboard.
            # SLR and freeboard are physical offsets — must NOT be multiplied.
            slr_m = get_slr_additive(scenario_id, year, region_zone)
            intens = np.clip(intens * mult + slr_m - asset.first_floor_height_m, 0.0, None)
            # Pass mult=1.0 because scaling is already applied above
            ead, damage_fracs = calc_ead_from_intensities(
                rp, intens, asset.asset_type, hazard, asset.replacement_value, 1.0
            )
        elif hazard == "flood":
            # Correct order: scale baseline by multiplier, THEN subtract freeboard.
            # Freeboard is a physical offset — must NOT be multiplied.
            intens = np.clip(intens * mult - asset.first_floor_height_m, 0.0, None)
            ead, damage_fracs = calc_ead_from_intensities(
                rp, intens, asset.asset_type, hazard, asset.replacement_value, 1.0
            )
        else:
            # Non-depth hazards: standard path — multiplier applied inside calc_ead
            ead, damage_fracs = calc_ead_from_intensities(
                rp, intens, asset.asset_type, hazard, asset.replacement_value, mult
            )

        # Effective intensities for reporting
        if hazard in ("flood", "coastal_flood"):
            effective_intens = intens  # already fully adjusted above
        else:
            effective_intens = intens * mult

        hazard_results[hazard] = AssetHazardResult(
            asset_id=asset.id,
            hazard=hazard,
            scenario_id=scenario_id,
            year=year,
            return_periods=rp.tolist(),
            intensities=effective_intens.tolist(),
            damage_fractions=damage_fracs.tolist(),
            ead=ead,
            ead_pct_value=ead / asset.replacement_value if asset.replacement_value > 0 else 0.0,
            data_source=source,
            hazard_multiplier=mult,
        )
        total_ead += ead

    return AssetResult(
        asset_id=asset.id,
        asset_name=asset.name,
        asset_value=asset.replacement_value,
        scenario_id=scenario_id,
        year=year,
        total_ead=total_ead,
        total_ead_pct=total_ead / asset.replacement_value if asset.replacement_value > 0 else 0.0,
        hazard_results=hazard_results,
        region=asset.region,
    )


def run_portfolio(
    assets: List[Asset],
    scenario_ids: List[str],
    years: List[int],
    hazard_overrides: Optional[Dict[str, Dict[str, dict]]] = None,
    progress_callback=None,
    hazard_overrides_by_scenario: Optional[Dict[str, Dict[str, Dict[str, dict]]]] = None,
) -> List[AssetResult]:
    """
    Run full portfolio calculation across all scenarios and years.

    Parameters
    ----------
    hazard_overrides            : {asset_id: {hazard: data}} — shared across scenarios (legacy)
    hazard_overrides_by_scenario: {scenario_id: {asset_id: {hazard: data}}} — per-scenario
                                  Takes precedence when available.
    """
    results = []
    total = len(assets) * len(scenario_ids) * len(years)
    done = 0

    for asset in assets:
        # Streamlit Cloud serialises dataclasses to dicts in session_state
        if isinstance(asset, dict):
            asset = Asset.from_dict(asset)
        for scenario_id in scenario_ids:
            for year in years:
                overrides = None
                # Prefer scenario-specific overrides
                if hazard_overrides_by_scenario and scenario_id in hazard_overrides_by_scenario:
                    sc_overrides = hazard_overrides_by_scenario[scenario_id]
                    if asset.id in sc_overrides:
                        overrides = sc_overrides[asset.id]
                elif hazard_overrides and asset.id in hazard_overrides:
                    overrides = hazard_overrides[asset.id]

                result = run_asset_scenario(asset, scenario_id, year, overrides)
                results.append(result)
                done += 1

                if progress_callback:
                    progress_callback(done / total)

    return results
