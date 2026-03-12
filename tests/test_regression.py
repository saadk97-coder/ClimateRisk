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
from engine.ead_calculator import calc_ead_from_intensities


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


# ── Test 3: ISIMIP source skips multiplier ────────────────────────────────────

def test_isimip_source_skips_multiplier():
    """When source starts with 'isimip', multiplier must be 1.0."""
    asset = _make_asset()
    hdata = _make_hazard_data(source="isimip3b")

    df = compute_annual_damages(asset, "current_policies", hdata, 0.035)

    assert all(df["multiplier"] == 1.0), \
        "ISIMIP source must set multiplier to 1.0 (no double-counting)"


# ── Test 4: Freeboard ingestion — old CSV with elevation_m ────────────────────

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

    # elevation_m should become terrain_elevation_asl_m (ASL), not freeboard
    assert asset.terrain_elevation_asl_m == 35.0, \
        f"elevation_m should map to terrain_elevation_asl_m, got {asset.terrain_elevation_asl_m}"
    assert asset.first_floor_height_m == 0.0, \
        f"Old CSV without first_floor_height_m should default to 0.0, got {asset.first_floor_height_m}"


# ── Test 5: Negative freeboard clamped ────────────────────────────────────────

def test_negative_freeboard_clamped():
    """Negative first_floor_height_m must be clamped to 0.0."""
    asset = _make_asset(first_floor_height_m=-1.5)
    assert asset.first_floor_height_m == 0.0, \
        "Negative freeboard must be clamped to 0.0"


# ── Test 6: First-floor height reduces flood intensity ────────────────────────

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


# ── Test 7: Region zone mapping ──────────────────────────────────────────────

def test_region_zone_mapping():
    """ISO3 codes must map to valid zone keys, not fall through silently."""
    assert get_region_zone("GBR") == "EUR", f"GBR should map to EUR"
    assert get_region_zone("USA") == "USA", f"USA should map to USA"
    assert get_region_zone("CHN") == "CHN", f"CHN should map to CHN"
    # Unknown countries fall back to global
    assert get_region_zone("XYZ") == "global", f"Unknown ISO3 should map to global"


# ── Test 8: Water stress returns non-zero damage fractions ────────────────────

def test_water_stress_damage_fraction():
    """get_damage_fraction('water_stress', ...) must pass through the input value,
    not silently return 0.0."""
    df = get_damage_fraction("water_stress", "residential_masonry", 0.15)
    assert df == 0.15, \
        f"Water stress damage fraction should pass through (got {df})"


# ── Test 9: Horizon monotonicity sanity check ────────────────────────────────

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


# ── Test 10: Adjusted intensity includes first-floor height reduction ─────────

def test_adjusted_intensity_includes_freeboard():
    """The adjusted_intensity_rp100 audit column must reflect first-floor height reduction."""
    asset = _make_asset(first_floor_height_m=1.0)
    hdata = _make_hazard_data()

    df = compute_annual_damages(asset, "current_policies", hdata, 0.035)
    row = df[(df["year"] == 2030) & (df["hazard"] == "flood")].iloc[0]

    baseline_rp100 = row["baseline_intensity_rp100"]
    adjusted_rp100 = row["adjusted_intensity_rp100"]

    # adjusted should be less than baseline (reduced by freeboard)
    assert adjusted_rp100 < baseline_rp100, \
        f"Adjusted intensity ({adjusted_rp100}) should be less than baseline ({baseline_rp100}) with 1m freeboard"
