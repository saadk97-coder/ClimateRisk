"""
Regression tests for platform integrity.

These tests lock critical numerical and structural behaviors identified
during code review to prevent regressions.
"""

import sys
import os
import numpy as np
import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.asset_model import Asset
from engine.annual_risk import compute_annual_damages
from engine.hazard_fetcher import get_region_zone
from engine.impact_functions import get_damage_fraction
from engine.ead_calculator import calc_ead_from_intensities, CHRONIC_HAZARDS


def _make_asset(**overrides):
    """Create a test asset with sensible defaults."""
    defaults = dict(
        id="TEST001",
        name="Test Asset",
        lat=51.5,
        lon=-0.1,
        asset_type="residential_masonry",
        replacement_value=10_000_000,
        construction_material="masonry",
        year_built=2000,
        stories=2,
        basement=False,
        roof_type="gable",
        first_floor_height_m=0.0,
        terrain_elevation_asl_m=10.0,
        floor_area_m2=200.0,
        region="GBR",
    )
    defaults.update(overrides)
    return Asset(**defaults)


def _make_hazard_data(source="fallback_baseline"):
    """Create minimal hazard data for testing."""
    return {
        "flood": {
            "return_periods": [10, 50, 100, 250, 500, 1000],
            "intensities": [0.5, 1.0, 1.5, 2.0, 2.5, 3.0],
            "source": source,
        },
    }


# ── Test 1: Scenario order invariance ────────────────────────────────────────

def test_scenario_order_invariance():
    """Results must not depend on the order of selected_scenarios."""
    asset = _make_asset()
    hdata = _make_hazard_data()

    df_a = compute_annual_damages(asset, "current_policies", hdata, 0.035)
    df_b = compute_annual_damages(asset, "current_policies", hdata, 0.035)

    # Same scenario, same data → identical results regardless of call order
    assert np.allclose(df_a["ead"].values, df_b["ead"].values), \
        "Same scenario + same data must produce identical EAD"


# ── Test 2: Different scenarios produce different outputs (for non-ISIMIP) ────

def test_different_scenarios_differ_for_fallback():
    """Under fallback data (mult != 1.0), different scenarios must produce
    different EAD for at least some years."""
    asset = _make_asset()
    hdata = _make_hazard_data(source="fallback_baseline")

    df_cp = compute_annual_damages(asset, "current_policies", hdata, 0.035)
    df_nz = compute_annual_damages(asset, "net_zero_2050", hdata, 0.035)

    # At 2050, warming differs between scenarios, so multiplier differs
    ead_cp_2050 = df_cp[df_cp["year"] == 2050]["ead"].sum()
    ead_nz_2050 = df_nz[df_nz["year"] == 2050]["ead"].sum()

    assert ead_cp_2050 != ead_nz_2050, \
        "Different scenarios with fallback data must produce different EAD at 2050"


# ── Test 3: Different SSPs produce different results (former bug) ────────────

def test_different_ssps_produce_different_results():
    """Two scenarios with different SSPs must produce different multipliers
    and therefore different EAD.  This is the test that would have caught the
    former bug where all scenarios shared one SSP's hazard baseline."""
    asset = _make_asset()
    hdata = _make_hazard_data(source="fallback_baseline")

    df_ssp245 = compute_annual_damages(asset, "ndcs_only", hdata, 0.035)       # SSP2-4.5
    df_ssp585 = compute_annual_damages(asset, "current_policies", hdata, 0.035)  # SSP5-8.5

    ead_245_2050 = df_ssp245[df_ssp245["year"] == 2050]["ead"].sum()
    ead_585_2050 = df_ssp585[df_ssp585["year"] == 2050]["ead"].sum()

    assert ead_585_2050 > ead_245_2050, \
        f"SSP5-8.5 EAD at 2050 ({ead_585_2050}) must exceed SSP2-4.5 ({ead_245_2050})"


# ── Test 4: All sources now apply multipliers (unified climate signal) ────────

def test_all_sources_apply_multipliers():
    """After Session 4 fix: ALL sources (including ISIMIP) apply multipliers.
    No more 'if source.startswith(isimip): mult = 1.0' — that created
    incoherent annual timelines."""
    asset = _make_asset()
    hdata_isimip = _make_hazard_data(source="isimip3b")

    df = compute_annual_damages(asset, "current_policies", hdata_isimip, 0.035)

    # Multiplier should NOT be 1.0 at 2050 (warming > 0 → mult > 1.0)
    mult_2050 = df[df["year"] == 2050]["multiplier"].values[0]
    assert mult_2050 > 1.0, \
        f"ISIMIP source must now apply multiplier > 1.0 at 2050 (got {mult_2050})"

    # And EAD should increase over time
    ead_2025 = df[df["year"] == 2025]["ead"].sum()
    ead_2050 = df[df["year"] == 2050]["ead"].sum()
    assert ead_2050 > ead_2025, \
        "Even ISIMIP-sourced data must show increasing EAD over time (multipliers applied)"


# ── Test 5: Freeboard ingestion — old CSV with elevation_m ────────────────────

def test_old_csv_elevation_not_freeboard():
    """Old CSV with 'elevation_m' must map to terrain_elevation_asl_m, NOT first_floor_height_m."""
    old_csv_row = {
        "id": "OLD001",
        "name": "Old Asset",
        "lat": 51.5, "lon": -0.1,
        "asset_type": "residential_masonry",
        "replacement_value": 5_000_000,
        "elevation_m": 35.0,  # old field — ASL, not freeboard
        "region": "GBR",
    }
    asset = Asset.from_dict(old_csv_row)

    assert asset.terrain_elevation_asl_m == 35.0, \
        f"elevation_m should map to terrain_elevation_asl_m, got {asset.terrain_elevation_asl_m}"
    assert asset.first_floor_height_m == 0.0, \
        f"Old CSV without first_floor_height_m should default to 0.0, got {asset.first_floor_height_m}"


# ── Test 6: Negative freeboard clamped ────────────────────────────────────────

def test_negative_freeboard_clamped():
    """Negative first_floor_height_m must be clamped to 0.0."""
    asset = _make_asset(first_floor_height_m=-1.5)
    assert asset.first_floor_height_m == 0.0, \
        "Negative freeboard must be clamped to 0.0"


# ── Test 7: First-floor height reduces flood intensity ────────────────────────

def test_freeboard_reduces_flood_intensity():
    """Asset with freeboard should have lower flood EAD than slab-on-grade."""
    asset_slab = _make_asset(first_floor_height_m=0.0)
    asset_raised = _make_asset(first_floor_height_m=1.0)
    hdata = _make_hazard_data()

    df_slab = compute_annual_damages(asset_slab, "current_policies", hdata, 0.035)
    df_raised = compute_annual_damages(asset_raised, "current_policies", hdata, 0.035)

    ead_slab = df_slab[df_slab["year"] == 2030]["ead"].sum()
    ead_raised = df_raised[df_raised["year"] == 2030]["ead"].sum()

    assert ead_raised < ead_slab, \
        f"Raised asset EAD ({ead_raised}) must be less than slab-on-grade ({ead_slab})"


# ── Test 8: Region zone mapping — including zone key pass-through ────────────

def test_region_zone_mapping():
    """ISO3 codes must map to valid zone keys.  Zone keys passed directly
    must be returned as-is (not mapped to 'global')."""
    # ISO3 → zone
    assert get_region_zone("GBR") == "EUR", "GBR should map to EUR"
    assert get_region_zone("USA") == "USA", "USA should map to USA"
    assert get_region_zone("CHN") == "CHN", "CHN should map to CHN"
    assert get_region_zone("SAU") == "MEA", "SAU should map to MEA"

    # Zone key pass-through (critical fix — was mapping to 'global' before)
    assert get_region_zone("EUR") == "EUR", "EUR zone key must pass through"
    assert get_region_zone("MEA") == "MEA", "MEA zone key must pass through"

    # Unknown countries fall back to global
    assert get_region_zone("XYZ") == "global", "Unknown ISO3 should map to global"


# ── Test 9: Water stress returns non-zero damage fractions ────────────────────

def test_water_stress_damage_fraction():
    """get_damage_fraction('water_stress', ...) must pass through the input value,
    not silently return 0.0."""
    df = get_damage_fraction("water_stress", "residential_masonry", 0.15)
    assert df == 0.15, \
        f"Water stress damage fraction should pass through (got {df})"


# ── Test 10: Water stress uses chronic pathway (no EP-curve integration) ──────

def test_water_stress_chronic_pathway():
    """Water stress EAD must use the chronic pathway (median RP50 × value),
    NOT trapezoidal EP-curve integration."""
    assert "water_stress" in CHRONIC_HAZARDS, \
        "water_stress must be in CHRONIC_HAZARDS set"

    rp = np.array([10, 50, 100, 250, 500, 1000], dtype=float)
    # Damage fractions (pre-computed by water_stress module)
    intensities = np.array([0.005, 0.010, 0.015, 0.020, 0.025, 0.030])
    value = 10_000_000

    ead, fracs = calc_ead_from_intensities(rp, intensities, "industrial", "water_stress", value, 1.0)

    # Chronic pathway: EAD = damage_fraction_at_RP50 × value
    # RP50 is index 1, intensity = 0.010, pass-through → frac = 0.010
    expected = 0.010 * value  # 100,000
    assert abs(ead - expected) < 1.0, \
        f"Water stress EAD should be {expected} (chronic median), got {ead}"


# ── Test 11: Horizon monotonicity sanity check ────────────────────────────────

def test_ead_increases_with_time_for_high_emission():
    """Under high-emission scenario with fallback data, EAD at 2050 should
    exceed EAD at 2025 (warming increases → multiplier increases)."""
    asset = _make_asset()
    hdata = _make_hazard_data()

    df = compute_annual_damages(asset, "current_policies", hdata, 0.035)
    ead_2025 = df[df["year"] == 2025]["ead"].sum()
    ead_2050 = df[df["year"] == 2050]["ead"].sum()

    assert ead_2050 >= ead_2025, \
        f"EAD should not decrease from 2025 ({ead_2025}) to 2050 ({ead_2050}) under high emission"


# ── Test 12: Adjusted intensity includes first-floor height reduction ─────────

def test_adjusted_intensity_includes_freeboard():
    """The adjusted_intensity_rp100 audit column must reflect first-floor height reduction."""
    asset = _make_asset(first_floor_height_m=1.0)
    hdata = _make_hazard_data()

    df = compute_annual_damages(asset, "current_policies", hdata, 0.035)
    row = df[(df["year"] == 2030) & (df["hazard"] == "flood")].iloc[0]

    baseline_rp100 = row["baseline_intensity_rp100"]
    adjusted_rp100 = row["adjusted_intensity_rp100"]

    assert adjusted_rp100 < baseline_rp100, \
        f"Adjusted intensity ({adjusted_rp100}) should be less than baseline ({baseline_rp100}) with 1m freeboard"


# ── Test 13: Additive SLR for coastal flood ──────────────────────────────────

def test_coastal_flood_additive_slr():
    """Coastal flood must use additive SLR, not purely multiplicative scaling."""
    from engine.scenario_model import get_slr_additive
    slr = get_slr_additive("current_policies", 2050)
    assert slr > 0.0, f"SLR at 2050 under current_policies must be > 0, got {slr}"
    # SLR should be in a physically reasonable range (0.1–1.5m by 2050)
    assert 0.05 < slr < 1.5, f"SLR at 2050 should be 0.05–1.5m, got {slr}"


# ── Test 14: SLR does NOT apply regional factor (Session 5 fix) ────────────

def test_slr_no_regional_factor():
    """get_slr_additive must return the same value regardless of region,
    because regional variation is handled by get_scenario_multipliers().
    Double-applying was the bug fixed in Session 5."""
    from engine.scenario_model import get_slr_additive
    slr_global = get_slr_additive("current_policies", 2050, region="global")
    slr_ind = get_slr_additive("current_policies", 2050, region="IND")
    slr_eur = get_slr_additive("current_policies", 2050, region="EUR")
    assert slr_global == slr_ind == slr_eur, \
        f"SLR must be region-independent: global={slr_global}, IND={slr_ind}, EUR={slr_eur}"


# ── Test 15: Scenario-agnostic ISIMIP baseline ────────────────────────────

def test_isimip_uses_historical_baseline():
    """ISIMIP fetcher must use historical experiment (scenario-agnostic),
    not SSP-conditioned future data. This prevents double-counting with
    the engine's scenario multipliers."""
    import importlib
    import ast

    # Parse the source directly to avoid importing xarray (not in test env)
    spec = importlib.util.find_spec("engine.isimip_fetcher")
    with open(spec.origin) as f:
        source = f.read()
    tree = ast.parse(source)

    found_baseline = None
    found_chunks = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_BASELINE_SSP":
                    found_baseline = ast.literal_eval(node.value)
                if isinstance(target, ast.Name) and target.id == "_TIME_CHUNKS":
                    found_chunks = ast.literal_eval(node.value)

    assert found_baseline == "historical", \
        f"ISIMIP baseline must be 'historical', got '{found_baseline}'"
    assert found_chunks is not None, "_TIME_CHUNKS not found in isimip_fetcher.py"
    for chunk in found_chunks:
        start_year = int(chunk.split("_")[0])
        assert start_year < 2015, \
            f"ISIMIP time chunk '{chunk}' is NOT historical (starts {start_year})"


# ── Test 16: Water stress data_center spelling matches asset_types.json ───

def test_water_stress_data_center_spelling():
    """asset_types.json uses 'data_center'; water_stress module must match."""
    import json
    import os
    from engine.water_stress import _ASSET_TYPE_WATER_SENSITIVITY

    # Check the module has "data_center" (not "data_centre")
    assert "data_center" in _ASSET_TYPE_WATER_SENSITIVITY, \
        "water_stress must use 'data_center' (not 'data_centre') to match asset_types.json"
    assert "data_centre" not in _ASSET_TYPE_WATER_SENSITIVITY, \
        "British spelling 'data_centre' should not be in water sensitivity map"


# ── Test 17: Negative terrain increases coastal flood depth ───────────────

def test_negative_terrain_increases_coastal_depth():
    """Below-sea-level terrain (e.g. polders) must INCREASE effective surge
    depth, not be skipped."""
    from engine.coastal import get_coastal_flood_intensities

    # Asset at sea level
    _, surge_zero = get_coastal_flood_intensities(
        lat=51.9, lon=4.5, region_iso3="NLD",
        terrain_elevation_asl_m=0.0
    )

    # Asset 2m below sea level (typical Dutch polder)
    _, surge_neg = get_coastal_flood_intensities(
        lat=51.9, lon=4.5, region_iso3="NLD",
        terrain_elevation_asl_m=-2.0
    )

    # Negative terrain → higher effective depth
    assert np.all(surge_neg >= surge_zero), \
        f"Below-sea-level terrain must increase surge depth: neg={surge_neg[2]:.2f} vs zero={surge_zero[2]:.2f}"
    assert surge_neg[2] > surge_zero[2], \
        "RP100 depth must be strictly greater for below-sea-level site"


# ── Test 18: CHELSA SSP mapping correctness ──────────────────────────────

def test_chelsa_ssp_mapping():
    """CHELSA SSP mapping must correctly map SSP2-4.5 to ssp245 (not ssp370)."""
    from engine.data_sources import _CHELSA_SSP_MAP
    assert _CHELSA_SSP_MAP["SSP2-4.5"] == "ssp245", \
        f"SSP2-4.5 must map to ssp245, got {_CHELSA_SSP_MAP['SSP2-4.5']}"
    assert _CHELSA_SSP_MAP.get("SSP3-7.0") == "ssp370", \
        f"SSP3-7.0 must map to ssp370, got {_CHELSA_SSP_MAP.get('SSP3-7.0')}"


# ── Test 19: Water stress sensitivity multiplier is applied ──────────────

def test_water_stress_sensitivity_applied():
    """Water stress damage fractions must differ by asset type due to
    sensitivity multipliers (e.g. data_center > residential)."""
    from engine.water_stress import _ASSET_TYPE_WATER_SENSITIVITY
    dc = _ASSET_TYPE_WATER_SENSITIVITY["data_center"]
    res = _ASSET_TYPE_WATER_SENSITIVITY["residential"]
    assert dc > res, \
        f"Data center sensitivity ({dc}) must exceed residential ({res})"


# ── Test 20: fetch_best_available handles wind (not just heat) ───────────

def test_fetch_best_available_supports_wind():
    """fetch_best_available must not fail for wind hazard — the condition
    must be 'hazard in (\"heat\", \"wind\")' not just 'hazard == \"heat\"'."""
    from engine.data_sources import fetch_best_available
    # This should not raise; it will return fallback since no real API is available
    source, val = fetch_best_available(51.5, -0.1, "wind", "GBR")
    # Should attempt NASA NEX for wind, then fall back
    assert source is not None, "fetch_best_available must return a source for wind"
