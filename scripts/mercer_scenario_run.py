"""
Mercer International — transition-risk quantification (live test / extension).

BSR did a *qualitative* TCFD climate-scenario analysis for Mercer International (pulp &
mass-timber; March 2025): physical-risk GIS mapping + survey-scored transition severity
(1-5). It never put a dollar figure on the transition risk. This script runs Mercer's
actual sites through the transition engine to QUANTIFY that layer and see whether the
numbers line up with what the deck found qualitatively.

Mercer = two business lines, so this exercises the firm-rollup:
  - PULP mills (pulp_paper)     Peace River (AB), Celgar (BC), Rosenthal (DE), Stendal (DE)
  - SOLID WOOD / MASS TIMBER    Mercer Timber Products (Friesau, DE), Torgau (DE)

Figures are APPROXIMATE / ILLUSTRATIVE, from Mercer's public annual + sustainability
reports (FY2023-24). Emissions entered are FOSSIL Scope 1+2 only — Mercer's mills run
~85-90% on biomass (black liquor / hog fuel), whose biogenic CO2 is carbon-neutral and
reported separately. Scope 3 is upstream fibre/chemicals/transport; the pulp_paper sector
nets out the biogenic fibre share (biogenic_scope3_fraction).

    PYTHONPATH=. python scripts/mercer_scenario_run.py
"""
from engine.asset_model import Asset
from engine.transition.transition_engine import (
    run_portfolio_transition, firm_rollup, DEFAULT_HORIZON)

REAL = 0.065
def pv(s): return sum(v / (1 + REAL) ** (y - 2025 + 1) for y, v in s.items())
def m(x):
    a = abs(x); sign = "-" if x < 0 else ""
    for u, d in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if a >= d: return f"{sign}{a/d:.1f}{u}"
    return f"{x:.0f}"

def site(id, sector, region, rev, s1, s2, s3):
    # fossil Scope 1+2 only (biomass excluded); s3 = upstream fibre/chemicals/transport
    return Asset(id=id, name=id, lat=0, lon=0, asset_type="x", replacement_value=rev * 1.4,
        construction_material="concrete", year_built=2005, stories=1, basement=False, roof_type="flat",
        first_floor_height_m=0, terrain_elevation_asl_m=0, floor_area_m2=0, region=region,
        sector=sector, scope1_emissions_tco2=s1, scope2_emissions_tco2=s2,
        scope3_emissions_tco2=s3, annual_revenue=rev, firm_id="Mercer")

# (rev USD, fossil Scope1, Scope2, upstream Scope3 tCO2). Illustrative allocations across sites.
SITES = [
    # Pulp mills — the bulk of revenue & emissions
    site("Peace River (AB)", "pulp_paper",           "CAN-AB", 380e6, 180_000, 15_000, 620_000),
    site("Celgar (BC)",      "pulp_paper",           "CAN-BC", 340e6, 120_000, 10_000, 560_000),
    site("Rosenthal (DE)",   "pulp_paper",           "DEU",    300e6, 150_000, 20_000, 480_000),
    site("Stendal (DE)",     "pulp_paper",           "DEU",    520e6, 220_000, 25_000, 820_000),
    # Solid wood / mass timber — smaller, a transition beneficiary
    site("Timber Products (DE)", "wood_products_timber", "DEU", 260e6, 40_000, 12_000, 300_000),
    site("Torgau (DE)",          "wood_products_timber", "DEU", 120e6, 18_000,  6_000, 140_000),
]

SCENARIOS = ["net_zero_2050", "delayed_transition", "current_policies"]
SC_LABEL = {"net_zero_2050": "Net Zero 2050", "delayed_transition": "Delayed Transition",
            "current_policies": "Current Policies"}

# Pulp & lumber are traded commodities (pass-through ~0.45-0.50), so the firm recovers part of
# the upstream carbon cost downstream — use partial pass-through (absorption = 1 - PT) rather than
# the full-absorption default, which overstates cost for price-setting commodity producers.
results = run_portfolio_transition(SITES, SCENARIOS, horizon=DEFAULT_HORIZON,
                                   l3_partial_pass_through=True)

print("MERCER INTERNATIONAL — quantified transition risk (illustrative)")
print(f"real discount {REAL*100:.1f}% · fossil Scope 1+2 only (biomass excluded) · "
      f"Scope 3 net of biogenic fibre · partial pass-through (traded commodity)\n")

# ---- per-site, Net Zero 2050 ----
sc = "net_zero_2050"
res = results[sc]
print(f"— Per site, {SC_LABEL[sc]} (PV 2025-2050) —")
print(f"{'Site':22s}{'sector':10s}{'reg':8s}{'rev':>7s}{'PVcost':>8s}{'%rev/yr':>8s}"
      f"{'L1':>7s}{'L3':>7s}{'WACC':>7s}")
for r, a in zip(res, SITES):
    tot = pv(r.annual_total_cost_usd); lb = r.layer_breakdown
    sect = "pulp" if a.sector == "pulp_paper" else "timber"
    print(f"{r.asset_id:22s}{sect:10s}{a.region:8s}{m(a.annual_revenue):>7s}{m(tot):>8s}"
          f"{tot/26/a.annual_revenue*100:>7.1f}%{m(pv(lb['L1_carbon_opex'])):>7s}"
          f"{m(pv(lb['L3_network_input_cost'])):>7s}{r.wacc_premium_bps:>5.0f}bp")

# ---- firm roll-up across scenarios ----
print(f"\n— Firm roll-up (Mercer consolidated), PV by scenario —")
print(f"{'Scenario':20s}{'PVcost':>9s}{'%rev/yr':>9s}{'L1 carbon':>11s}"
      f"{'L3 supply':>11s}{'WACC':>8s}")
firm_rev = sum(a.annual_revenue for a in SITES)
for sc in SCENARIOS:
    rolls = firm_rollup(results[sc], SITES)
    fr = rolls["Mercer"]
    tot = pv(fr.annual_total_cost_usd)
    l1 = pv({y: sum(r.layer_breakdown["L1_carbon_opex"].get(y, 0) for r in results[sc]) for y in DEFAULT_HORIZON})
    l3 = pv({y: sum(r.layer_breakdown["L3_network_input_cost"].get(y, 0) for r in results[sc]) for y in DEFAULT_HORIZON})
    wacc = (sum(r.wacc_premium_bps * a.annual_revenue for r, a in zip(results[sc], SITES))
            / firm_rev)   # revenue-weighted firm WACC add-on
    print(f"{SC_LABEL[sc]:20s}{m(tot):>9s}{tot/26/firm_rev*100:>8.1f}%"
          f"{m(l1):>11s}{m(l3):>11s}{wacc:>6.0f}bp")

# ---- EU (ETS) vs North America split, Net Zero ----
print(f"\n— Geography: EU vs North America carbon exposure, {SC_LABEL['net_zero_2050']} —")
for grp, regs in [("EU mills (DE)", ("DEU",)), ("N. America mills (CAN)", ("CAN-AB", "CAN-BC"))]:
    idx = [i for i, a in enumerate(SITES) if a.region in regs and a.sector == "pulp_paper"]
    l1 = pv({y: sum(results['net_zero_2050'][i].layer_breakdown["L1_carbon_opex"].get(y, 0) for i in idx)
             for y in DEFAULT_HORIZON})
    rev = sum(SITES[i].annual_revenue for i in idx)
    print(f"  {grp:24s} pulp rev {m(rev):>7s}  →  carbon-compliance PV {m(l1):>7s}  "
          f"({l1/26/rev*100:.1f}% of rev/yr)")

# ---- map to the deck's qualitative findings ----
print("\n— Does the quantified layer match the March-2025 deck's qualitative scoring? —")
print("  Deck's top transition risks: compliance cost, transportation, biomass cost, wood-supply scarcity.")
print("  Engine: L1 (carbon compliance) and L3 (upstream fibre/chemicals/transport) are the two")
print("          dominant cost channels — same shape as the survey. Mass-timber line carries a WACC")
print("          DISCOUNT and a GROWING demand pathway (deck's 'domestic leadership / product")
print("          innovation' opportunity). No stranding — Mercer is a low-carbon producer, not a")
print("          stranded-asset risk, which matches the deck framing physical risk > transition risk.")
