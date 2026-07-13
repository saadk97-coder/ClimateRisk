"""
Diagnostic: run representative companies from every BSR Decarbonization Lever
Library sector, with varied transition-plan quality and geographic spread
(including a diversified multi-line, multi-region firm). Used to surface
limitations, gaps and distortions — not a product feature.

    python scripts/diagnostic_runs.py
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

def A(id, sector, region, rev, s1, s2, s3, repl, target=0, pos=-1.0, capex=0.0):
    return Asset(id=id, name=id, lat=0, lon=0, asset_type="x", replacement_value=repl,
        construction_material="concrete", year_built=2010, stories=1, basement=False, roof_type="flat",
        first_floor_height_m=0, terrain_elevation_asl_m=0, floor_area_m2=0, region=region, sector=sector,
        scope1_emissions_tco2=s1, scope2_emissions_tco2=s2, scope3_emissions_tco2=s3, annual_revenue=rev,
        decarb_target_year=target, positioning_override=pos, transition_capex_usd=capex)

# BSR sector → taxonomy mapping shown in [] ; varied geography + plan quality
COMPANIES = [
    # ---- one per BSR lever-library sector (mapped to taxonomy) ----
    A("APPAREL [manuf]",       "manufacturing_general", "VNM", 5e9, 2e5, 8e5, 20e6, 3e9),
    A("AUTO-ICE [ice]",        "road_transport_ice",    "DEU", 80e9, 1e6, 2e6, 350e6, 35e9, target=2035),
    A("AVIATION [aviation]",   "aviation",              "USA", 40e9, 30e6, 3e5, 5e6, 30e9),
    A("BUILDING [re_comm]",    "real_estate_commercial","GBR", 4e9, 3e4, 1.2e5, 8e5, 30e9),
    A("TELECOM [data_ctr]",    "data_center",           "USA-CA", 60e9, 5e4, 5e6, 3e6, 40e9),
    A("CONSUMER [manuf]",      "manufacturing_general", "CHN", 30e9, 8e5, 4e6, 40e6, 15e9),
    A("CHEMICALS [chem]",      "chemicals",             "USA-TX", 25e9, 12e6, 2e6, 15e6, 20e9, target=2045),
    A("POWER-COAL [coal]",     "power_coal",            "IND", 6e9, 25e6, 2e5, 1e6, 12e9),
    A("OIL-REF [oil_ref]",     "oil_refining",          "SAU", 40e9, 6e6, 5e5, 60e6, 10e9),
    A("FINSERV [services]",    "services",              "GBR", 20e9, 5e3, 4e4, 2e6, 3e9),
    A("FOOD-BEV [agri]",       "agriculture",           "BRA", 15e9, 8e6, 5e5, 3e6, 10e9),
    A("GEN-MANUF [manuf]",     "manufacturing_general", "USA", 20e9, 2e6, 3e6, 10e6, 15e9),
    A("HEALTHCARE [services]", "services",              "USA", 30e9, 1e5, 6e5, 4e6, 20e9),
    A("IT [data_ctr]",         "data_center",           "USA-TX", 100e9, 3e4, 8e6, 5e6, 50e9, target=2030, pos=0.85),
    A("SHIPPING [shipping]",   "shipping",              "SGP", 20e9, 25e6, 3e5, 2e6, 15e9),
    A("MINING [oil_up]",       "oil_upstream",          "AUS", 30e9, 15e6, 5e6, 8e6, 25e9),
    A("STEEL [steel]",         "steel",                 "KOR", 25e9, 40e6, 4e6, 12e6, 18e9),
    A("CEMENT [cement]",       "cement",                "IND", 12e9, 25e6, 1e6, 2e6, 10e9),

    # ---- plan-quality contrast: same steel plant, three plans ----
    A("STEEL-strong",          "steel", "DEU", 20e9, 30e6, 3e6, 10e6, 15e9, target=2035, pos=0.85, capex=8e9),
    A("STEEL-weak",            "steel", "DEU", 20e9, 30e6, 3e6, 10e6, 15e9, target=2050),
    A("STEEL-none",            "steel", "DEU", 20e9, 30e6, 3e6, 10e6, 15e9, pos=0.15),

    # ---- diversified multi-line, multi-region firm (4 business lines) ----
    A("CONGLOM/steel-DE",      "steel",                 "DEU",   10e9, 15e6, 1.5e6, 5e6, 8e9,  target=2040),
    A("CONGLOM/chem-TX",       "chemicals",             "USA-TX", 8e9, 4e6, 8e5, 5e6, 6e9,     target=2040),
    A("CONGLOM/datactr-CA",    "data_center",           "USA-CA", 5e9, 1e4, 1.5e6, 1e6, 4e9,   target=2040),
    A("CONGLOM/coal-IN",       "power_coal",            "IND",    3e9, 12e6, 1e5, 5e5, 5e9,     target=2040),
]

scen = "net_zero_2050"
res = run_portfolio_transition(COMPANIES, [scen], horizon=DEFAULT_HORIZON)[scen]
byid = {r.asset_id: r for r in res}

print(f"{'Company':22s}{'reg':>7s}{'PVcost':>8s}{'L1':>7s}{'L2ero':>7s}{'capex':>7s}{'L3':>7s}"
      f"{'impair':>8s}{'A':>5s}{'P':>5s}{'capt':>6s}{'WACC':>6s} {'quality'}")
for r in res:
    lb = r.layer_breakdown; s = r.strategy
    print(f"{r.asset_id:22s}{r.region:>7s}{m(pv(r.annual_total_cost_usd)):>8s}"
          f"{m(pv(lb['L1_carbon_opex'])):>7s}{m(pv(lb['L2_revenue_erosion'])):>7s}"
          f"{m(pv(lb['L2_transition_capex'])):>7s}{m(pv(lb['L3_network_input_cost'])):>7s}"
          f"{m(sum(r.annual_impairment_usd.values())):>8s}"
          f"{s.ambition:>5.2f}{s.positioning:>5.2f}{s.capture_fraction:>6.2f}"
          f"{r.wacc_premium_bps:>6.0f} {r.data_quality}")

print("\n--- Diversified firm (CONGLOM) aggregate ---")
cong = [r for r in res if r.asset_id.startswith("CONGLOM")]
tot = sum(pv(r.annual_total_cost_usd) for r in cong)
imp = sum(sum(r.annual_impairment_usd.values()) for r in cong)
print(f"4 business lines, 3 regions: total PV transition cost = {m(tot)}, cumulative impairment = {m(imp)}")
print("Note: assets summed independently — no firm-level correlation, shared plan, or portfolio effects.")

print("\n--- Plan-quality contrast (same DE steel plant) ---")
for k in ("STEEL-strong", "STEEL-weak", "STEEL-none"):
    r = byid[k]; s = r.strategy
    print(f"  {k:14s}: PVcost={m(pv(r.annual_total_cost_usd)):>7s} capex={m(pv(r.layer_breakdown['L2_transition_capex'])):>7s} "
          f"P={s.positioning:.2f} capture={s.capture_fraction:.2f} L1={m(pv(r.layer_breakdown['L1_carbon_opex'])):>7s}")

print("\n--- Sector-lumping check (BSR sectors sharing one taxonomy bucket) ---")
for bucket in ("manufacturing_general", "services", "data_center"):
    same = [r for r in res if r.sector == bucket]
    if len(same) > 1:
        print(f"  {bucket}: {', '.join(r.asset_id.split(' ')[0] for r in same)} — all use identical sector params")
