"""
Test suite for the transition risk layer (Session 8).

Covers all four layers and the DCF integration:
  L1 — carbon pricing with pass-through
  L2 — learning curves / stranding
  L3 — network propagation
  L4 — CCExposure overlay
  Orchestrator + DCF combination

The reference architecture is the BSR Climate Risk Practice memo (May 2026):
"Quantifying Transition Risk: Landscape, Frontier, and a Path Forward".
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.asset_model import Asset
from engine.dcf_engine import DCFInputs
from engine.transition.carbon_pricing import (
    compute_carbon_cost,
    get_carbon_price,
    get_pass_through,
    abatement_index,
)
from engine.transition.cc_exposure import (
    ROUTE_CASHFLOWS,
    ROUTE_WACC,
    compute_exposure_premium,
    get_sector_exposure,
)
from engine.transition.data_loader import (
    get_ngfs_region,
    list_sectors,
    load_carbon_prices,
    load_io_matrix,
    load_learning_curves,
    load_sector_pass_through,
    load_sector_pathways,
    load_sector_taxonomy,
    map_scenario_to_ngfs,
)
from engine.transition.learning_curves import (
    _project_cost,
    compute_stranding,
    find_crossover_year,
)
from engine.transition.network_propagation import (
    build_sectorwide_shock,
    get_leontief_inverse,
    propagate_carbon_shock,
)
from engine.transition.transition_engine import (
    DEFAULT_HORIZON,
    run_asset_transition,
    run_portfolio_transition,
    transition_results_to_damage_df,
)
from engine.transition.transition_dcf import compute_combined_dcf


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def coal_plant() -> Asset:
    return Asset(
        id="A1", name="Coal Plant", lat=40.0, lon=-100.0,
        asset_type="industrial_heavy", replacement_value=500_000_000,
        construction_material="concrete", year_built=2010, stories=3,
        basement=False, roof_type="flat", first_floor_height_m=0.0,
        terrain_elevation_asl_m=200.0, floor_area_m2=20000, region="USA",
        sector="power_coal",
        scope1_emissions_tco2=2_500_000.0, scope2_emissions_tco2=50_000.0,
        scope3_emissions_tco2=200_000.0, annual_revenue=300_000_000,
    )


@pytest.fixture
def office() -> Asset:
    return Asset(
        id="B1", name="Office", lat=40.7, lon=-74.0,
        asset_type="commercial_office", replacement_value=50_000_000,
        construction_material="steel", year_built=2015, stories=10,
        basement=True, roof_type="flat", first_floor_height_m=0.0,
        terrain_elevation_asl_m=10.0, floor_area_m2=6000, region="USA",
        sector="real_estate_commercial",
        scope1_emissions_tco2=200.0, scope2_emissions_tco2=800.0,
        annual_revenue=15_000_000,
    )


@pytest.fixture
def refinery() -> Asset:
    return Asset(
        id="C1", name="Refinery", lat=29.7, lon=-95.4,
        asset_type="industrial_heavy", replacement_value=2_000_000_000,
        construction_material="concrete", year_built=2005, stories=4,
        basement=False, roof_type="flat", first_floor_height_m=0.5,
        terrain_elevation_asl_m=15.0, floor_area_m2=50000, region="USA",
        sector="oil_refining",
        scope1_emissions_tco2=4_500_000.0, scope2_emissions_tco2=300_000.0,
        scope3_emissions_tco2=8_000_000.0, annual_revenue=8_000_000_000,
    )


# ---------------------------------------------------------------------------
# Asset model — extended fields
# ---------------------------------------------------------------------------


def test_asset_model_transition_fields_default_to_zero():
    a = Asset(
        id="X", name="X", lat=0, lon=0, asset_type="commercial_office",
        replacement_value=1_000_000, construction_material="steel",
        year_built=2010, stories=1, basement=False, roof_type="flat",
        first_floor_height_m=0.0, terrain_elevation_asl_m=0.0,
        floor_area_m2=100, region="USA",
    )
    assert a.sector == ""
    assert a.scope1_emissions_tco2 == 0.0
    assert a.scope2_emissions_tco2 == 0.0
    assert a.scope3_emissions_tco2 == 0.0
    assert a.annual_revenue == 0.0


def test_asset_model_negative_emissions_clamped():
    a = Asset(
        id="X", name="X", lat=0, lon=0, asset_type="commercial_office",
        replacement_value=1_000_000, construction_material="steel",
        year_built=2010, stories=1, basement=False, roof_type="flat",
        first_floor_height_m=0.0, terrain_elevation_asl_m=0.0,
        floor_area_m2=100, region="USA",
        scope1_emissions_tco2=-100.0, scope2_emissions_tco2=-50.0,
        annual_revenue=-1.0,
    )
    assert a.scope1_emissions_tco2 == 0.0
    assert a.scope2_emissions_tco2 == 0.0
    assert a.annual_revenue == 0.0


def test_asset_model_from_dict_supports_transition_fields():
    a = Asset.from_dict({
        "id": "X", "name": "X", "lat": 0, "lon": 0,
        "asset_type": "commercial_office", "replacement_value": 1e6,
        "construction_material": "steel", "year_built": 2010, "stories": 1,
        "basement": False, "roof_type": "flat", "first_floor_height_m": 0.0,
        "terrain_elevation_asl_m": 0.0, "floor_area_m2": 100, "region": "USA",
        "sector": "POWER_COAL", "scope1_emissions_tco2": 1000.0,
        "annual_revenue": 5_000_000,
    })
    assert a.sector == "power_coal"
    assert a.scope1_emissions_tco2 == 1000.0
    assert a.annual_revenue == 5_000_000.0


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def test_data_catalogues_load_without_error():
    assert load_carbon_prices()["scenarios"]
    assert load_sector_pass_through()["sectors"]
    assert load_learning_curves()["technologies"]
    assert load_sector_pathways()["sectors"]
    assert load_io_matrix()["A"]
    assert load_sector_taxonomy()["sectors"]


def test_io_matrix_is_square_and_matches_sector_order():
    raw = load_io_matrix()
    A = np.array(raw["A"])
    sectors = raw["_meta"]["sector_order"]
    assert A.shape[0] == A.shape[1] == len(sectors)


def test_io_matrix_diagonal_and_off_diag_in_realistic_ranges():
    A = np.array(load_io_matrix()["A"])
    # All entries should be in [0, 1] for a sensible direct-requirements matrix
    assert np.all(A >= 0)
    assert np.all(A <= 1)
    # Column sums should be < 1 (value added > 0)
    col_sums = A.sum(axis=0)
    assert np.all(col_sums < 1.0), f"col sums must be < 1: {col_sums}"


def test_get_ngfs_region_classification():
    assert get_ngfs_region("USA") == "advanced"
    assert get_ngfs_region("CHN") == "emerging"
    assert get_ngfs_region("ZWE") == "rest_of_world"
    assert get_ngfs_region("") == "rest_of_world"


def test_map_scenario_ipcc_fallback():
    # IPCC SSPs should map to NGFS analogs
    assert map_scenario_to_ngfs("ssp1_19") == "net_zero_2050"
    assert map_scenario_to_ngfs("ssp5_85") == "current_policies"
    # NGFS scenarios pass through
    assert map_scenario_to_ngfs("net_zero_2050") == "net_zero_2050"


# ---------------------------------------------------------------------------
# Layer 1 — carbon pricing
# ---------------------------------------------------------------------------


def test_carbon_price_advanced_higher_than_rest_of_world():
    # NGFS REMIND price differentiation: advanced economies higher than developing
    p_adv = get_carbon_price("net_zero_2050", 2050, "advanced")
    p_row = get_carbon_price("net_zero_2050", 2050, "rest_of_world")
    assert p_adv > p_row > 0


def test_carbon_price_higher_under_orderly_than_current_policies():
    p_nz = get_carbon_price("net_zero_2050", 2050, "advanced")
    p_cp = get_carbon_price("current_policies", 2050, "advanced")
    assert p_nz > 10 * p_cp, f"NZ should be >>10x current policies (got {p_nz} vs {p_cp})"


def test_carbon_price_interpolates_between_listed_years():
    p_2030 = get_carbon_price("net_zero_2050", 2030, "advanced")
    p_2035 = get_carbon_price("net_zero_2050", 2035, "advanced")
    p_2040 = get_carbon_price("net_zero_2050", 2040, "advanced")
    assert p_2030 < p_2035 < p_2040


def test_carbon_price_constant_outside_horizon():
    p_2025 = get_carbon_price("net_zero_2050", 2025, "advanced")
    p_2020 = get_carbon_price("net_zero_2050", 2020, "advanced")
    assert p_2020 == p_2025


def test_pass_through_extreme_sectors_match_literature():
    # Power: ~80% (Sijm, Fabra & Reguant)
    assert get_pass_through("power_coal")["pass_through"] >= 0.75
    # Steel: ~30% (trade-exposed, Fabra & Reguant)
    assert get_pass_through("steel")["pass_through"] <= 0.40
    # Refining: ~75% (Sijm 2012)
    assert 0.65 <= get_pass_through("oil_refining")["pass_through"] <= 0.85


def test_carbon_cost_decomposition_balances():
    """gross_cost = absorbed + passed_through (Scope 1+2 ledger)."""
    r = compute_carbon_cost(
        asset_id="t", sector="power_coal", region_iso3="USA",
        scenario_id="net_zero_2050", year=2050,
        scope1_emissions_tco2=1000.0, scope2_emissions_tco2=200.0,
        scope3_emissions_tco2=0.0,
    )
    assert abs((r.absorbed_cost_usd + r.passed_through_usd) - r.gross_cost_usd) < 1.0


def test_carbon_cost_zero_emissions_zero_cost():
    r = compute_carbon_cost(
        asset_id="t", sector="services", region_iso3="USA",
        scenario_id="net_zero_2050", year=2050,
        scope1_emissions_tco2=0.0, scope2_emissions_tco2=0.0,
    )
    assert r.gross_cost_usd == 0.0
    assert r.net_carbon_opex_usd == 0.0


def test_carbon_cost_pass_through_override_respected():
    r = compute_carbon_cost(
        asset_id="t", sector="power_coal", region_iso3="USA",
        scenario_id="net_zero_2050", year=2050,
        scope1_emissions_tco2=1000.0, scope2_emissions_tco2=0.0,
        pass_through_override=0.0,
    )
    # 0% pass-through → firm absorbs 100%
    assert abs(r.absorbed_cost_usd - r.gross_cost_usd) < 1.0
    assert r.passed_through_usd == 0.0


# ---------------------------------------------------------------------------
# Layer 2 — learning curves / stranding
# ---------------------------------------------------------------------------


def test_solar_pv_cost_declines_over_time():
    p_2025 = _project_cost("solar_pv", "net_zero_2050", 2025)
    p_2050 = _project_cost("solar_pv", "net_zero_2050", 2050)
    assert p_2050.projected_cost < p_2025.projected_cost
    # Lafond bands are multiplicative (lognormal): RELATIVE band widens with horizon
    rel_2025 = p_2025.cost_hi / p_2025.cost_lo
    rel_2050 = p_2050.cost_hi / p_2050.cost_lo
    assert rel_2050 > rel_2025


def test_coal_steam_cost_does_not_decline_under_zero_learning_rate():
    # coal_steam has LR = 0 → cost stays flat (no Wright's Law effect)
    p_2025 = _project_cost("coal_steam", "current_policies", 2025)
    p_2050 = _project_cost("coal_steam", "current_policies", 2050)
    assert abs(p_2025.projected_cost - p_2050.projected_cost) < 1.0


def test_negative_capacity_growth_does_not_inflate_incumbent_cost():
    # Negative annual_capacity_growth represents demand decline; capacity
    # cumulative is monotonic so cost should NOT rise when LR > 0.
    p_2025 = _project_cost("oil_refining", "net_zero_2050", 2025)
    p_2050 = _project_cost("oil_refining", "net_zero_2050", 2050)
    # oil_refining has LR=0.02 → small decline at most, but never an increase
    assert p_2050.projected_cost <= p_2025.projected_cost + 1


def test_solar_crosses_below_coal_immediately():
    """Solar PV is already cheaper than new-build coal in 2025."""
    cross = find_crossover_year("coal_steam", "solar_pv", "net_zero_2050")
    assert cross == 2025


def test_demand_collapse_triggers_stranding_without_cost_crossover(refinery):
    """Refinery has no cost crossover (biorefining stays > oil_refining cost)
    but oil_refining demand collapses to ~0.20 by 2050 in NZ — should still strand."""
    s = compute_stranding(
        refinery.id, refinery.sector, refinery.replacement_value,
        "net_zero_2050", DEFAULT_HORIZON,
    )
    assert s.crossover_year is not None
    assert sum(s.annual_impairment_usd.values()) > 0


def test_no_stranding_under_current_policies(refinery):
    """No demand collapse in Current Policies → no stranding."""
    s = compute_stranding(
        refinery.id, refinery.sector, refinery.replacement_value,
        "current_policies", DEFAULT_HORIZON,
    )
    assert s.crossover_year is None
    assert sum(s.annual_impairment_usd.values()) == 0


def test_stranding_scales_with_scenario_severity(coal_plant):
    """NZ2050 stranding should be larger than Current Policies."""
    s_nz = compute_stranding(coal_plant.id, coal_plant.sector,
                              coal_plant.replacement_value,
                              "net_zero_2050", DEFAULT_HORIZON)
    s_cp = compute_stranding(coal_plant.id, coal_plant.sector,
                              coal_plant.replacement_value,
                              "current_policies", DEFAULT_HORIZON)
    assert sum(s_nz.annual_impairment_usd.values()) > sum(s_cp.annual_impairment_usd.values())


def test_real_estate_does_not_strand():
    """Real estate has no fossil-dependent flag and revenue grows slightly →
    no stranding even in NZ scenarios."""
    s = compute_stranding(
        "B1", "real_estate_commercial", 50_000_000, "net_zero_2050", DEFAULT_HORIZON,
    )
    assert sum(s.annual_impairment_usd.values()) == 0


# ---------------------------------------------------------------------------
# Layer 3 — network propagation
# ---------------------------------------------------------------------------


def test_leontief_inverse_is_invertible():
    L, sectors = get_leontief_inverse()
    assert L.shape == (20, 20)
    # Diagonal should be > 1 (own + indirect)
    assert np.all(np.diag(L) > 1.0)


def test_leontief_diag_dominance():
    L, _ = get_leontief_inverse()
    # Diagonal should be largest in its column (own coefficient dominates)
    for j in range(L.shape[1]):
        assert L[j, j] >= np.max(L[:, j]) - 1e-9


def test_propagate_carbon_shock_zero_input_zero_output():
    r = propagate_carbon_shock(
        asset_id="t", sector="services", scenario_id="net_zero_2050", year=2050,
        asset_revenue=1_000_000,
        sector_carbon_costs={s: 0.0 for s in list_sectors()},
        sector_outputs=None,
    )
    assert r.total_indirect_cost_usd == 0.0


def test_sectorwide_shock_scales_with_carbon_price():
    s_low = build_sectorwide_shock(50.0)
    s_high = build_sectorwide_shock(500.0)
    # Higher carbon price → larger sector shocks
    assert sum(s_high.values()) > sum(s_low.values()) * 5


def test_high_emission_sectors_dominate_shock_vector():
    s = build_sectorwide_shock(100.0)
    # power_coal (emission_intensity 7.5 t/M$) should dominate services (0.05 t/M$)
    assert s["power_coal"] > s["services"] * 50


def test_layer3_indirect_cost_proportional_to_revenue(refinery):
    r_low = propagate_carbon_shock(
        asset_id="t", sector="oil_refining", scenario_id="net_zero_2050", year=2050,
        asset_revenue=1_000_000,
        sector_carbon_costs=build_sectorwide_shock(100.0),
        sector_outputs=None,
    )
    r_high = propagate_carbon_shock(
        asset_id="t", sector="oil_refining", scenario_id="net_zero_2050", year=2050,
        asset_revenue=10_000_000,
        sector_carbon_costs=build_sectorwide_shock(100.0),
        sector_outputs=None,
    )
    # 10x revenue → ~10x indirect cost (scales linearly)
    assert abs(r_high.total_indirect_cost_usd - 10 * r_low.total_indirect_cost_usd) / max(r_high.total_indirect_cost_usd, 1) < 0.01


# ---------------------------------------------------------------------------
# Layer 4 — CCExposure
# ---------------------------------------------------------------------------


def test_cc_exposure_routing_cashflows_no_wacc_premium():
    r = compute_exposure_premium(
        asset_id="t", sector="power_coal", scenario_id="net_zero_2050",
        annual_revenue=300_000_000, years=DEFAULT_HORIZON, routing=ROUTE_CASHFLOWS,
    )
    # When routed to CFs, the WACC premium is computed but shouldn't be applied
    # downstream — the orchestrator zeros it. Here we check the routing flag.
    assert r.routing == ROUTE_CASHFLOWS
    assert any(v != 0.0 for v in r.annual_revenue_modifier_usd.values())


def test_cc_exposure_routing_wacc_no_cashflow_modifier():
    r = compute_exposure_premium(
        asset_id="t", sector="power_coal", scenario_id="net_zero_2050",
        annual_revenue=300_000_000, years=DEFAULT_HORIZON, routing=ROUTE_WACC,
    )
    assert r.routing == ROUTE_WACC
    assert all(v == 0.0 for v in r.annual_revenue_modifier_usd.values())
    assert r.credit_spread_premium_bps > 0


def test_cc_exposure_renewable_has_revenue_uplift():
    """power_renewable has high opportunity, low regulatory → net revenue
    growth modifier should be positive."""
    r = compute_exposure_premium(
        asset_id="t", sector="power_renewable", scenario_id="net_zero_2050",
        annual_revenue=100_000_000, years=DEFAULT_HORIZON, routing=ROUTE_CASHFLOWS,
    )
    assert r.revenue_growth_modifier_bps > 0


def test_cc_exposure_coal_has_revenue_drag():
    """power_coal has high regulatory, low opportunity → net negative revenue."""
    r = compute_exposure_premium(
        asset_id="t", sector="power_coal", scenario_id="delayed_transition",
        annual_revenue=300_000_000, years=DEFAULT_HORIZON, routing=ROUTE_CASHFLOWS,
    )
    assert r.revenue_growth_modifier_bps < 0


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def test_orchestrator_produces_horizon_complete_results(coal_plant):
    r = run_asset_transition(coal_plant, "net_zero_2050")
    assert set(r.annual_total_cost_usd.keys()) == set(DEFAULT_HORIZON)


def test_orchestrator_layer_disable_zeroes_layer(coal_plant):
    r = run_asset_transition(coal_plant, "net_zero_2050", enable_layers=(1,))
    # Only Layer 1 enabled → other breakdowns should be zero
    assert all(v == 0 for v in r.layer_breakdown["L2_revenue_erosion"].values())
    assert all(v == 0 for v in r.layer_breakdown["L3_network_input_cost"].values())
    assert all(v == 0 for v in r.layer_breakdown["L4_revenue_modifier"].values())


def test_orchestrator_total_equals_sum_of_layers(coal_plant):
    r = run_asset_transition(coal_plant, "net_zero_2050")
    for y in DEFAULT_HORIZON:
        layer_sum = (
            r.layer_breakdown["L1_carbon_opex"][y]
            + r.layer_breakdown["L2_revenue_erosion"][y]
            + r.layer_breakdown["L3_network_input_cost"][y]
            + r.layer_breakdown["L4_revenue_modifier"][y]
        )
        assert abs(layer_sum - r.annual_total_cost_usd[y]) < 1.0


def test_orchestrator_skips_unsectored_assets():
    a = Asset(
        id="X", name="X", lat=0, lon=0, asset_type="commercial_office",
        replacement_value=1_000_000, construction_material="steel",
        year_built=2010, stories=1, basement=False, roof_type="flat",
        first_floor_height_m=0.0, terrain_elevation_asl_m=0.0,
        floor_area_m2=100, region="USA",
    )  # no sector
    out = run_portfolio_transition([a], ["net_zero_2050"])
    assert out["net_zero_2050"] == []


def test_orchestrator_scenario_differentiation(coal_plant):
    out = run_portfolio_transition(
        [coal_plant], ["net_zero_2050", "current_policies"]
    )
    nz_total = sum(out["net_zero_2050"][0].annual_total_cost_usd.values())
    cp_total = sum(out["current_policies"][0].annual_total_cost_usd.values())
    assert nz_total > 5 * cp_total, "NZ should be >>5x Current Policies for a coal plant"


def test_clean_asset_can_have_negative_total_cost(office):
    """An office building with low emissions in NZ scenario should see a NET
    revenue uplift from CCExposure opportunity exceeding modest carbon cost."""
    r = run_asset_transition(office, "net_zero_2050")
    # Negative cost = net benefit; not required, but L4 component should be negative
    assert r.layer_breakdown["L4_revenue_modifier"][2050] < 0


# ---------------------------------------------------------------------------
# DCF integration
# ---------------------------------------------------------------------------


def test_combined_dcf_pv_costs_decompose(coal_plant):
    transition_results = [run_asset_transition(coal_plant, "net_zero_2050")]
    # Empty physical damages df
    phys_df = pd.DataFrame({
        "year": list(range(2025, 2051)),
        "ead": [0.0] * 26,
        "scenario_id": ["net_zero_2050"] * 26,
    })
    inputs = DCFInputs(
        name="Test", base_year=2025, forecast_years=10,
        wacc=0.08, asset_value=coal_plant.replacement_value,
    )
    cdcf = compute_combined_dcf(
        inputs=inputs, physical_damages_df=phys_df,
        transition_results=transition_results, scenario_id="net_zero_2050",
    )
    # PV transition costs should be > 0 for a coal plant
    assert cdcf.total_pv_transition_costs > 0
    # Combined NPV should be lower than physical-only NPV (more damages)
    assert cdcf.combined_dcf.npv_climate < cdcf.physical_dcf.npv_climate


def test_transition_results_to_damage_df_shape(coal_plant):
    out = run_portfolio_transition([coal_plant], ["net_zero_2050", "current_policies"])
    df = transition_results_to_damage_df(out)
    assert set(df.columns) >= {"year", "ead", "scenario_id"}
    assert set(df["scenario_id"].unique()) == {"net_zero_2050", "current_policies"}


# ---------------------------------------------------------------------------
# P0 — Abatement pathway, Scope-3 mode, effective (priced) carbon price
# ---------------------------------------------------------------------------

def test_abatement_index_linear_to_target():
    idx = abatement_index(2050, 0.0, list(range(2025, 2051)))
    assert idx[2025] == 1.0
    assert idx[2050] == 0.0
    # halfway in time ~ halfway in emissions
    assert abs(idx[2037] - (1 - (2037 - 2025) / 25)) < 1e-9
    # monotonic non-increasing
    vals = [idx[y] for y in range(2025, 2051)]
    assert all(a >= b - 1e-12 for a, b in zip(vals, vals[1:]))


def test_abatement_index_disabled_when_no_target():
    idx = abatement_index(0, 0.0, list(range(2025, 2051)))
    assert all(v == 1.0 for v in idx.values())


def test_abatement_index_residual_floor():
    idx = abatement_index(2040, 20.0, list(range(2025, 2051)))
    assert abs(idx[2040] - 0.20) < 1e-9
    assert abs(idx[2050] - 0.20) < 1e-9   # flat after target


def test_abatement_reduces_l1_carbon_cost(coal_plant):
    """An asset that decarbonises pays less Layer-1 carbon cost by 2050."""
    base = run_asset_transition(coal_plant, "net_zero_2050", enable_layers=(1,))
    abated = Asset.from_dict({**coal_plant.to_dict(), "decarb_target_year": 2050,
                              "decarb_residual_pct": 0.0})
    ab = run_asset_transition(abated, "net_zero_2050", enable_layers=(1,))
    assert ab.layer_breakdown["L1_carbon_opex"][2050] < base.layer_breakdown["L1_carbon_opex"][2050]
    # 2025 (base year) unchanged
    assert abs(ab.layer_breakdown["L1_carbon_opex"][2025]
               - base.layer_breakdown["L1_carbon_opex"][2025]) < 1.0


def test_priced_fraction_scales_l1(coal_plant):
    """Free allocation / partial coverage lowers the priced carbon cost."""
    full = run_asset_transition(coal_plant, "net_zero_2050", enable_layers=(1,))
    half = Asset.from_dict({**coal_plant.to_dict(), "priced_emissions_fraction": 0.5})
    hr = run_asset_transition(half, "net_zero_2050", enable_layers=(1,))
    # Scope-1+2 gross halves; net also falls (Scope-3 term unaffected so not exactly half)
    assert hr.layer_breakdown["L1_carbon_opex"][2050] < full.layer_breakdown["L1_carbon_opex"][2050]


def test_scope3_mode_full_includes_scope3(coal_plant):
    r = run_asset_transition(coal_plant, "net_zero_2050", enable_layers=(1, 3), scope3_mode="full")
    s3 = [x.scope3_indirect_usd for x in r.layer1_results if x.year == 2050][0]
    assert s3 > 0   # coal_plant has Scope-3 emissions


def test_scope3_mode_auto_drops_l1_scope3_when_l3_on(coal_plant):
    r = run_asset_transition(coal_plant, "net_zero_2050", enable_layers=(1, 3), scope3_mode="auto")
    s3 = [x.scope3_indirect_usd for x in r.layer1_results if x.year == 2050][0]
    assert s3 == 0.0   # dropped to avoid double count with L3


def test_scope3_mode_auto_keeps_scope3_when_l3_off(coal_plant):
    r = run_asset_transition(coal_plant, "net_zero_2050", enable_layers=(1,), scope3_mode="auto")
    s3 = [x.scope3_indirect_usd for x in r.layer1_results if x.year == 2050][0]
    assert s3 > 0   # L3 not active, so Scope-3 still counted in L1


def test_asset_model_p0_fields_default_to_legacy():
    a = Asset.from_dict({"id": "x", "name": "x", "lat": 0, "lon": 0,
                         "asset_type": "t", "replacement_value": 1e6, "region": "USA"})
    assert a.decarb_target_year == 0
    assert a.decarb_residual_pct == 0.0
    assert a.priced_emissions_fraction == 1.0


# ---------------------------------------------------------------------------
# P1 — Monte-Carlo uncertainty
# ---------------------------------------------------------------------------

def test_monte_carlo_percentiles_ordered(coal_plant):
    from engine.transition.uncertainty import run_monte_carlo, MCConfig
    r = run_monte_carlo([coal_plant], "net_zero_2050", discount_rate=0.09,
                        config=MCConfig(draws=120, seed=1))
    s = r.summary()["transition_cost"]
    assert s["p5"] < s["p50"] < s["p95"]
    assert s["base"] > 0


def test_monte_carlo_is_seed_deterministic(coal_plant):
    from engine.transition.uncertainty import run_monte_carlo, MCConfig
    a = run_monte_carlo([coal_plant], "net_zero_2050", config=MCConfig(draws=80, seed=7))
    b = run_monte_carlo([coal_plant], "net_zero_2050", config=MCConfig(draws=80, seed=7))
    assert a.summary()["transition_cost"]["p50"] == b.summary()["transition_cost"]["p50"]


def test_price_scale_moves_l1_linearly(coal_plant):
    hi = run_asset_transition(coal_plant, "net_zero_2050", enable_layers=(1,), price_scale=2.0)
    base = run_asset_transition(coal_plant, "net_zero_2050", enable_layers=(1,), price_scale=1.0)
    # Layer-1 net cost scales ~linearly with the carbon price
    r = hi.layer_breakdown["L1_carbon_opex"][2050] / base.layer_breakdown["L1_carbon_opex"][2050]
    assert abs(r - 2.0) < 0.01


# ---------------------------------------------------------------------------
# P0 — Layer-4 z-base (D3) and sourced LCOE
# ---------------------------------------------------------------------------

def test_l4_zbase_low_exposure_sector_near_zero():
    """After z-standardisation, a low-exposure sector (services) carries a near-zero
    premium, not the inflated ~65bps of the raw-proxy version."""
    r = compute_exposure_premium("t", "services", "net_zero_2050", 1e8, list(DEFAULT_HORIZON))
    assert abs(r.equity_premium_bps) < 20
    coal = compute_exposure_premium("t", "power_coal", "net_zero_2050", 1e8, list(DEFAULT_HORIZON))
    # coal (high regulatory exposure) has a materially larger credit premium than services
    assert coal.credit_spread_premium_bps > r.credit_spread_premium_bps + 10


def test_l4_zbase_default_is_pooled_mean_zero():
    """The default (unmatched) exposure equals the pooled mean → z ≈ 0."""
    r = compute_exposure_premium("t", "no_such_sector", "current_policies", 1e8, list(DEFAULT_HORIZON))
    assert abs(r.cce_opportunity) < 0.5 and abs(r.cce_regulatory) < 0.5


def test_lcoe_solar_below_coal_and_units_mwh():
    lc = load_learning_curves()["technologies"]
    assert "cost_2025_usd_per_mwh" in lc["solar_pv"]
    assert "cost_2025_usd_per_mwh" in lc["coal_steam"]
    assert lc["solar_pv"]["cost_2025_usd_per_mwh"] < lc["coal_steam"]["cost_2025_usd_per_mwh"]


# ---------------------------------------------------------------------------
# P2 — Portfolio alignment metrics (financed emissions, ITR, PACTA)
# ---------------------------------------------------------------------------

def test_financed_emissions_attribution(coal_plant):
    from engine.transition.alignment import financed_emissions
    full = financed_emissions([coal_plant])
    half = financed_emissions([coal_plant], {coal_plant.id: 0.5})
    assert abs(half.total_s1_s2 - 0.5 * full.total_s1_s2) < 1.0
    assert abs(full.scope3 - coal_plant.scope3_emissions_tco2) < 1.0


def test_itr_abatement_lowers_temperature(coal_plant):
    from engine.transition.alignment import implied_temperature_rise
    from engine.asset_model import Asset
    flat = implied_temperature_rise([coal_plant])["portfolio_itr"]
    nz = Asset.from_dict({**coal_plant.to_dict(), "decarb_target_year": 2050})
    aligned = implied_temperature_rise([nz])["portfolio_itr"]
    assert aligned < flat
    assert aligned <= 1.7  # net-zero-2050 path scores near the 1.5C benchmark


def test_pathway_alignment_status(coal_plant):
    from engine.transition.alignment import pathway_alignment
    from engine.asset_model import Asset
    assert pathway_alignment(coal_plant, "net_zero_2050")["status"] == "misaligned"
    nz = Asset.from_dict({**coal_plant.to_dict(), "decarb_target_year": 2050})
    assert pathway_alignment(nz, "net_zero_2050")["status"] == "aligned"
