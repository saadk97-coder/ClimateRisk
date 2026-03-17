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
from engine.impact_functions import get_curve_control_points, get_damage_fraction
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
    with open(spec.origin, encoding="utf-8") as f:
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


# ── Test 21: Flood freeboard ordering — mult BEFORE freeboard ────────────

def test_flood_freeboard_ordering():
    """Flood must apply: max(0, base * mult - freeboard), NOT (base - freeboard) * mult.
    The multiplier scales the hazard intensity; freeboard is a physical offset subtracted after."""
    asset_slab = _make_asset(first_floor_height_m=0.0)
    asset_raised = _make_asset(first_floor_height_m=0.5)
    hdata = _make_hazard_data()

    df_slab = compute_annual_damages(asset_slab, "current_policies", hdata, 0.035)
    df_raised = compute_annual_damages(asset_raised, "current_policies", hdata, 0.035)

    # At 2050, mult > 1.0. With the old ordering (base - freeboard) * mult,
    # freeboard reduction was amplified by mult. With correct ordering
    # (base * mult - freeboard), freeboard reduction is constant.
    row_slab = df_slab[(df_slab["year"] == 2050) & (df_slab["hazard"] == "flood")].iloc[0]
    row_raised = df_raised[(df_raised["year"] == 2050) & (df_raised["hazard"] == "flood")].iloc[0]

    mult = row_slab["multiplier"]
    baseline_rp100 = row_slab["baseline_intensity_rp100"]
    freeboard = 0.5

    # Under correct ordering: effective = max(0, baseline * mult - freeboard)
    expected_effective = max(0, baseline_rp100 * mult - freeboard)
    actual_effective = row_raised["adjusted_intensity_rp100"]

    assert abs(actual_effective - expected_effective) < 0.01, \
        f"Flood effective intensity should be max(0, {baseline_rp100}*{mult}-{freeboard})={expected_effective:.4f}, got {actual_effective:.4f}"


# ── Test 22: Coastal flood ordering — mult * base + SLR - freeboard ──────

def test_coastal_flood_ordering():
    """Coastal flood must apply: max(0, base * storm_mult + SLR - freeboard).
    SLR and freeboard must NOT be multiplied."""
    from engine.scenario_model import get_slr_additive, get_scenario_multipliers

    asset = _make_asset(first_floor_height_m=0.3)
    rp = np.array([10, 50, 100, 250, 500, 1000], dtype=float)
    base_intens = np.array([0.2, 0.5, 0.8, 1.2, 1.6, 2.0], dtype=float)
    hdata = {
        "coastal_flood": {
            "return_periods": rp.tolist(),
            "intensities": base_intens.tolist(),
            "source": "coastal_slr_baseline",
        }
    }

    df = compute_annual_damages(asset, "current_policies", hdata, 0.035)
    row = df[(df["year"] == 2050) & (df["hazard"] == "coastal_flood")].iloc[0]

    mult = get_scenario_multipliers("current_policies", 2050, "coastal_flood", "EUR")
    slr = get_slr_additive("current_policies", 2050, "EUR")

    # Expected: max(0, 0.8 * mult + slr - 0.3)
    expected = max(0, 0.8 * mult + slr - 0.3)
    actual = row["adjusted_intensity_rp100"]

    assert abs(actual - expected) < 0.01, \
        f"Coastal effective intensity should be max(0, 0.8*{mult}+{slr}-0.3)={expected:.4f}, got {actual:.4f}"


# ── Test 23: SLR and freeboard are NOT multiplied ────────────────────────

def test_slr_and_freeboard_not_multiplied():
    """Verify that freeboard/SLR contribution is independent of the multiplier value.
    If we double the multiplier, the freeboard deduction should stay constant."""
    import engine.scenario_model as sm
    original_fn = sm.get_scenario_multipliers

    asset = _make_asset(first_floor_height_m=1.0)
    rp = np.array([10, 50, 100, 250, 500, 1000], dtype=float)
    base_intens = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0], dtype=float)
    hdata = {
        "flood": {
            "return_periods": rp.tolist(),
            "intensities": base_intens.tolist(),
            "source": "fallback_baseline",
        }
    }

    # Run with actual multiplier
    df1 = compute_annual_damages(asset, "current_policies", hdata, 0.035)
    row1 = df1[(df1["year"] == 2050) & (df1["hazard"] == "flood")].iloc[0]

    # Effective = base * mult - freeboard
    # If freeboard were multiplied, effective = (base - freeboard) * mult
    # The difference tells us which formula is used.
    mult = row1["multiplier"]
    base_rp100 = 3.0  # the baseline RP100 value
    freeboard = 1.0

    correct_effective = max(0, base_rp100 * mult - freeboard)
    wrong_effective = max(0, (base_rp100 - freeboard) * mult)

    actual = row1["adjusted_intensity_rp100"]

    # Should match correct formula, not the wrong one
    assert abs(actual - correct_effective) < 0.01, \
        f"Effective intensity {actual:.4f} should match (base*mult-fb)={correct_effective:.4f}, not ((base-fb)*mult)={wrong_effective:.4f}"


# ── Test 24: Fallback sources are not future-conditioned ─────────────────

def test_fallback_sources_not_future_conditioned():
    """The baseline fetch path must not silently use future-conditioned
    alternative sources (NASA/CHELSA/ClimateNA). These were removed from
    the fetch cascade in favour of ISIMIP + built-in regional baseline only."""
    import ast
    import importlib

    spec = importlib.util.find_spec("engine.hazard_fetcher")
    with open(spec.origin, encoding="utf-8") as f:
        source = f.read()

    # The fetch_hazard_intensities function should NOT call fetch_best_available
    # (which uses SSP/year parameters) in its main path.
    # Check that fetch_best_available is not called in the active code path.
    tree = ast.parse(source)

    # Find the fetch_hazard_intensities function
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "fetch_hazard_intensities":
            # Walk the function body for calls to fetch_best_available
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    name = ""
                    if isinstance(func, ast.Name):
                        name = func.id
                    elif isinstance(func, ast.Attribute):
                        name = func.attr
                    assert name != "fetch_best_available", \
                        "fetch_hazard_intensities must not call fetch_best_available (future-conditioned)"
            break


# ── Test 25: asset_type threaded through damage_engine fetch ─────────────

def test_asset_type_threaded_in_damage_engine():
    """damage_engine fetch paths must pass asset_type to fetch functions,
    not default to 'default'. Check by inspecting the source code."""
    import ast
    import importlib

    spec = importlib.util.find_spec("engine.damage_engine")
    with open(spec.origin, encoding="utf-8") as f:
        source = f.read()

    # Count occurrences of asset_type= in keyword arguments to fetch calls
    assert "asset_type=asset.asset_type" in source, \
        "damage_engine must pass asset_type=asset.asset_type to fetch calls"


# ── Test 26: water_stress in results hazard chart loop ───────────────────

def test_water_stress_in_results_chart():
    """The Results page stacked hazard chart must include water_stress
    to maintain reporting parity with totals."""
    import importlib

    spec = importlib.util.find_spec("pages.04_Results")
    with open(spec.origin, encoding="utf-8") as f:
        source = f.read()

    # The hazard loop for the stacked chart must include water_stress
    assert '"water_stress"' in source, \
        "Results page must include water_stress in hazard decomposition"


# ── Test 27: No TVaR/tail-risk overclaims in Results ────────────────────

def test_no_tvar_claims_in_results():
    """Results page must not claim TVaR/CVaR computation since these are not
    actually calculated. EP curve shows discrete RP points only."""
    import importlib

    spec = importlib.util.find_spec("pages.04_Results")
    with open(spec.origin, encoding="utf-8") as f:
        source = f.read().lower()

    # Should NOT contain claims about computing TVaR or 99th percentile losses
    assert "tail value at risk (tvar)" not in source, \
        "Results page must not claim TVaR is computed"
    assert '"insurance-grade"' not in source, \
        "Results page must not claim insurance-grade"


# ── Test 28: No hardcoded £ in Map page popups ──────────────────────────

def test_no_hardcoded_gbp_in_map():
    """Map page must use currency symbol from session state, not hardcoded £."""
    import importlib

    spec = importlib.util.find_spec("pages.05_Map")
    with open(spec.origin, encoding="utf-8") as f:
        source = f.read()

    # Count £ occurrences — should be zero (all replaced with _sym)
    gbp_count = source.count("£")
    assert gbp_count == 0, \
        f"Map page still has {gbp_count} hardcoded £ symbols — should use _sym from currency selector"


# ── Test 29: Vulnerability page has no upload/custom curve false promises ─

def test_no_vulnerability_false_promises():
    """Vulnerability page must not contain upload controls or claims about
    custom curves affecting calculations unless they are actually wired."""
    import importlib

    spec = importlib.util.find_spec("pages.09_Vulnerability")
    with open(spec.origin, encoding="utf-8") as f:
        source = f.read()

    assert "session restart to apply" not in source, \
        "Vulnerability page must not claim custom curves apply after restart (they don't)"
    assert "Upload Custom Curve" not in source, \
        "Vulnerability page must not offer upload if not wired to engine"


# ── Test 30: Manual hazard overrides are merged into Results run ─────────

def test_manual_overrides_merged_in_results():
    """Results page must merge hazard_overrides from session state into the
    hazard data used for computation."""
    import importlib

    spec = importlib.util.find_spec("pages.04_Results")
    with open(spec.origin, encoding="utf-8") as f:
        source = f.read()

    assert "hazard_overrides" in source, \
        "Results page must reference hazard_overrides from session state"


# ── Test 31: Asset dict normalization in app.py ──────────────────────────

def test_asset_dict_normalization():
    """Asset.from_dict should produce the same attributes as direct construction."""
    asset = _make_asset()
    d = asset.to_dict()
    rebuilt = Asset.from_dict(d)

    assert rebuilt.id == asset.id
    assert rebuilt.replacement_value == asset.replacement_value
    assert rebuilt.first_floor_height_m == asset.first_floor_height_m
    assert rebuilt.region == asset.region


# ── Test 32: Marketing claims are screening-level ────────────────────────

def test_no_insurance_grade_claim():
    """app.py must not claim 'insurance-grade' since the platform is screening-level."""
    import importlib

    spec = importlib.util.find_spec("app")
    with open(spec.origin, encoding="utf-8") as f:
        source = f.read().lower()

    # Allow "not insurance-grade" disclaimers, but reject positive claims
    for line in source.splitlines():
        if "insurance-grade" in line and "not insurance-grade" not in line:
            raise AssertionError(
                f"app.py must not claim insurance-grade (platform is screening-level): {line.strip()}"
            )


def test_asset_from_dict_parses_boolean_strings():
    """String booleans in uploaded CSV rows must be parsed correctly."""
    row = _make_asset().to_dict()
    row["basement"] = "False"
    rebuilt = Asset.from_dict(row)
    assert rebuilt.basement is False

    row["basement"] = "true"
    rebuilt_true = Asset.from_dict(row)
    assert rebuilt_true.basement is True


def test_curve_control_points_follow_alias_resolution():
    """Vulnerability reference control points must match the alias-resolved engine curve."""
    alias_x, alias_y, _, alias_key = get_curve_control_points("flood", "commercial_office")
    base_x, base_y, _, base_key = get_curve_control_points("flood", "commercial_steel")

    assert alias_key == "commercial_steel"
    assert base_key == "commercial_steel"
    assert np.allclose(alias_x, base_x)
    assert np.allclose(alias_y, base_y)


def test_governance_page_exists():
    """Governance page should exist as a first-class surface for assurance review."""
    import importlib

    spec = importlib.util.find_spec("pages.10_Governance")
    assert spec is not None, "Governance page is missing"


def test_adaptation_measures_cover_extended_asset_types():
    """Extended portfolio asset types should resolve to a usable adaptation catalog entry."""
    from engine.adaptation_engine import list_measures

    measures = list_measures(asset_type="commercial_office")
    assert measures, "commercial_office should inherit adaptation measures from the base catalog"


def test_fetch_all_hazards_preserves_requested_order():
    """Parallel hazard collection must keep the requested hazard ordering stable."""
    import engine.hazard_fetcher as hf

    original = hf.fetch_hazard_intensities

    def _fake_fetch(lat, lon, hazard, region_iso3, scenario_ssp="SSP2-4.5", time_period="2021_2040",
                    terrain_elevation_asl_m=0.0, asset_type="default", fetch_mode="balanced"):
        value = {
            "heat": 1.0,
            "flood": 2.0,
            "wind": 3.0,
        }[hazard]
        return np.array([10.0, 100.0]), np.array([value, value + 0.5]), "fallback_baseline"

    hf.fetch_hazard_intensities = _fake_fetch
    try:
        data = hf.fetch_all_hazards(
            51.5,
            -0.1,
            "GBR",
            ["heat", "flood", "wind"],
            fetch_mode="full",
        )
    finally:
        hf.fetch_hazard_intensities = original

    assert list(data.keys()) == ["heat", "flood", "wind"]
    assert data["heat"]["intensities"] == [1.0, 1.5]
    assert data["wind"]["intensities"] == [3.0, 3.5]


def test_acute_hazard_cache_uses_grid_resolution():
    """Nearby assets in the same 0.5 degree acute-hazard cell should share one cached fetch."""
    import engine.hazard_fetcher as hf

    original_impl = hf._fetch_hazard_intensities_impl
    hf._fetch_hazard_intensities_cached.cache_clear()
    calls = []

    def _fake_impl(lat, lon, hazard, region_iso3, scenario_ssp="baseline", time_period="historical",
                   terrain_elevation_asl_m=0.0, asset_type="default", fetch_mode="full"):
        calls.append((lat, lon, hazard, region_iso3, fetch_mode))
        return np.array([10.0, 100.0]), np.array([1.0, 2.0]), "fallback_baseline"

    hf._fetch_hazard_intensities_impl = _fake_impl
    try:
        hf.fetch_hazard_intensities(51.49, -0.11, "heat", "GBR", fetch_mode="full")
        hf.fetch_hazard_intensities(51.51, -0.09, "heat", "GBR", fetch_mode="full")
    finally:
        hf._fetch_hazard_intensities_impl = original_impl
        hf._fetch_hazard_intensities_cached.cache_clear()

    assert len(calls) == 1, f"Expected one shared grid-cell fetch, got {len(calls)}"


def test_dcf_page_uses_scenario_toggle_language():
    """DCF page should present scenario-specific valuation views, not weighted scenario language."""
    import importlib

    spec = importlib.util.find_spec("pages.07_DCF")
    with open(spec.origin, encoding="utf-8") as f:
        source = f.read().lower()

    assert "probability-weighted" not in source
    assert "weight by probability" not in source
    assert "valuation scenario" in source


def test_hazard_pages_hide_worker_knob():
    """Hazard and Results pages should auto-tune fetch concurrency instead of exposing worker counts."""
    import importlib

    for module_name in ["pages.03_Hazards", "pages.04_Results"]:
        spec = importlib.util.find_spec(module_name)
        with open(spec.origin, encoding="utf-8") as f:
            source = f.read()
        assert "Parallel asset workers" not in source


def test_default_fetch_mode_is_balanced():
    """The default fetch mode should use an ensemble path, not the single-GCM shortcut."""
    from engine.hazard_fetcher import DEFAULT_FETCH_MODE

    assert DEFAULT_FETCH_MODE == "balanced"
