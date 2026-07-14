"""
Stress test the transition methodology against FIVE real public companies, using
figures from their FY2023 sustainability / annual reports (approximate, public).

  BASF        chemical    DE   — huge Scope 1+2, net-zero 2050
  Pfizer      pharma      US   — modest emissions, net-zero 2040
  Caterpillar industrial  US   — small own ops, MASSIVE use-of-sold-products Scope 3
  Nike        apparel     US   — Scope 3 = 99% of footprint, asset-light
  Microsoft   technology  US   — data-centre buildout, carbon-negative-2030 (emissions rising)

Purpose: see where the methodology tracks reality and where it breaks. Not a product feature.
    python scripts/stress_test_real_companies.py
"""
from engine.asset_model import Asset
from engine.transition.transition_engine import run_portfolio_transition, DEFAULT_HORIZON

REAL = 0.065
def pv(s): return sum(v / (1 + REAL) ** (y - 2025 + 1) for y, v in s.items())
def m(x):
    a = abs(x)
    for u, d in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if a >= d:
            return f"{x/d:.1f}{u}"
    return f"{x:.0f}"

def A(id, sector, region, rev, s1, s2, s3, repl, target=0, s3_use=0.0):
    # s3 = UPSTREAM value-chain Scope 3 (cat 1-9) → L3 report-anchored input cost.
    # s3_use = DOWNSTREAM use-of-sold-products (cat 11) → product-demand risk (equipment/engine makers).
    return Asset(id=id, name=id, lat=0, lon=0, asset_type="x", replacement_value=repl,
        construction_material="concrete", year_built=2010, stories=1, basement=False, roof_type="flat",
        first_floor_height_m=0, terrain_elevation_asl_m=0, floor_area_m2=0, region=region, sector=sector,
        scope1_emissions_tco2=s1, scope2_emissions_tco2=s2, scope3_emissions_tco2=s3,
        scope3_use_phase_tco2=s3_use, annual_revenue=rev, decarb_target_year=target)

# (rev, Scope1, Scope2, Scope3-upstream tCO2, replacement/PP&E $, target[, use-phase]). Sources in the write-up.
CO = [
    A("BASF (chem)",        "chemicals",             "DEU", 74e9, 14.3e6, 2.3e6, 90e6,  45e9, target=2050),
    A("Pfizer (pharma)",    "healthcare",            "USA", 58e9, 0.6e6,  0.5e6, 4e6,   20e9, target=2040),
    # Caterpillar's ~400 Mt Scope 3 is dominated by use-of-sold-products (diesel machinery in the
    # field); only ~40 Mt is genuine upstream supply chain. New industrial_equipment sector.
    A("Caterpillar (ind.)", "industrial_equipment",  "USA", 67e9, 1.4e6,  1.0e6, 40e6,  15e9, target=0, s3_use=360e6),
    A("Nike (apparel)",     "apparel_textiles",      "USA", 51e9, 0.05e6, 0.23e6, 9.5e6, 6e9,  target=2050),
    A("Microsoft (tech)",   "data_center",           "USA", 212e9, 0.145e6, 0.393e6, 17.1e6, 100e9, target=2030),
]

scen = "net_zero_2050"
res = run_portfolio_transition(CO, [scen], horizon=DEFAULT_HORIZON)[scen]

print(f"NET-ZERO-2050 scenario, real discount {REAL*100:.1f}%\n")
print(f"{'Company':20s}{'S1+2 Mt':>8s}{'S3up Mt':>8s}{'S3use Mt':>9s}{'PVcost':>8s}{'%ofRev/yr':>10s}"
      f"{'L1':>7s}{'L3':>7s}{'useph':>7s}{'impair':>8s}{'WACC':>6s}")
for r, a in zip(res, CO):
    lb = r.layer_breakdown
    tot = pv(r.annual_total_cost_usd)
    pct = tot / 26 / a.annual_revenue * 100
    print(f"{r.asset_id:20s}{(a.scope1_emissions_tco2+a.scope2_emissions_tco2)/1e6:>8.1f}"
          f"{a.scope3_emissions_tco2/1e6:>8.0f}{a.scope3_use_phase_tco2/1e6:>9.0f}"
          f"{m(tot):>8s}{pct:>9.1f}%"
          f"{m(pv(lb['L1_carbon_opex'])):>7s}{m(pv(lb['L3_network_input_cost'])):>7s}"
          f"{m(pv(lb['L2_product_use_phase'])):>7s}{m(sum(r.annual_impairment_usd.values())):>8s}"
          f"{r.wacc_premium_bps:>5.0f}bp")

print("\n--- Reality checks (does the model see what the reports say?) ---")
for r, a in zip(res, CO):
    s = r.strategy; l2 = r.layer2_result
    s3_ratio = a.scope3_emissions_tco2 / max(a.scope1_emissions_tco2 + a.scope2_emissions_tco2, 1)
    xover = l2.crossover_year if (l2 and l2.crossover_year) else "none"
    print(f"  {r.asset_id:20s} Scope3/Scope12 = {s3_ratio:>5.0f}×  crossover={xover}  "
          f"positioning={s.positioning:.2f}  stranded={r.strategy and sum(r.annual_impairment_usd.values())>0}")
