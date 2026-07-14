"""
Stress-test the lever-level CAPITAL PLAN against two real published transition plans:

  Mercedes-Benz Group (auto, ICE→EV)   Ambition 2039 — fleet net-neutral by 2039
  ArcelorMittal        (steel, BF→DRI)  ~$10bn decarb roadmap, site-level DRI/EAF capex

Figures are public FY2023 (sustainability / climate transition action plans, SEC 20-F,
SteelWatch). Purpose: does the model's seeded capital plan resemble what these companies
actually say they will spend, and where does it need refining?

    PYTHONPATH=. python scripts/transition_plan_stress.py

Sources:
  Mercedes-Benz Climate Transition Action Plan 2023; tracenable GHG data (S1 0.538 Mt,
    S2 0.083 Mt, S3 119.52 Mt, ~78% use-phase); FY23 revenue ~$165.7bn.
  ArcelorMittal FY2023 20-F / Basis of Reporting (S1+2 114.3 Mt excl JV/India, rev $68.3bn);
    ~$10bn gross decarb capital cost for the 2030 intensity target (Gijón €1bn, Ghent €1.1bn).
"""
from engine.asset_model import Asset
from engine.transition.adaptive_capacity import build_strategy, scenario_ambition
from engine.transition.data_loader import get_ngfs_region
from engine.transition.estimation import estimate_scope12_from_revenue, estimate_emissions_if_missing
from engine.transition.opportunity import estimate_opportunity_capex
from engine.transition.lever_planner import (
    default_lever_plan, build_capex_schedule, plan_total_capex, plan_total_abatement)

SC = "net_zero_2050"

def m(x):
    a = abs(x)
    for u, d in (("bn", 1e9), ("M", 1e6), ("k", 1e3)):
        if a >= d:
            return f"${x/d:.1f}{u}"
    return f"${x:.0f}"

def company(name, sector, region, rev, s1, s2, s3_up, s3_use, repl, target, published):
    a = Asset(id=name, name=name, lat=0, lon=0, asset_type="x", replacement_value=repl,
        construction_material="concrete", year_built=2005, stories=1, basement=False, roof_type="flat",
        first_floor_height_m=0, terrain_elevation_asl_m=0, floor_area_m2=0, region=region, sector=sector,
        scope1_emissions_tco2=s1, scope2_emissions_tco2=s2, scope3_emissions_tco2=s3_up,
        scope3_use_phase_tco2=s3_use, annual_revenue=rev, decarb_target_year=target)
    amb = scenario_ambition(SC)
    strat = build_strategy(asset_id=a.id, sector=sector, scenario_id=SC,
                           region_band=get_ngfs_region(region),
                           scope12_tco2=s1 + s2, revenue_usd=rev, replacement_value=repl,
                           horizon=list(range(2025, 2051)), target_year=target)
    rows = default_lever_plan(sector, s1 + s2, s3_up, s3_use, strat.transition_capex_usd,
                              amb, list(range(2025, 2051)), target_year=target)
    sched = build_capex_schedule(rows, list(range(2025, 2051)))
    print(f"\n{'='*78}\n{name}  ·  {sector}  ·  {region}  ·  rev {m(rev)}  ·  "
          f"S1+2 {(s1+s2)/1e6:.1f} Mt · S3up {s3_up/1e6:.0f} Mt · S3use {s3_use/1e6:.0f} Mt")
    print(f"  positioning {strat.positioning:.2f} · ambition {amb:.2f} · "
          f"model top-down capex {m(strat.transition_capex_usd)}")
    print(f"  {'Lever':34s}{'stage':10s}{'now':>5s}{'tgt':>5s}{'addr Mt':>9s}{'capex':>9s}")
    for r in sorted(rows, key=lambda r: -r.capex_usd):
        print(f"  {r.name[:33]:34s}{r.position.replace('own_operations','own'):10s}"
              f"{r.adoption_now*100:>4.0f}%{r.adoption_target*100:>4.0f}%"
              f"{r.addressable_tco2/1e6:>9.1f}{m(r.capex_usd):>9s}")
    print(f"  → bottom-up capex {m(plan_total_capex(rows))} · "
          f"abatement@target {plan_total_abatement(rows)/1e6:.0f} Mt/yr")
    opp = estimate_opportunity_capex(sector, repl, SC)
    if opp.is_beneficiary:
        print(f"  OPPORTUNITY LENS — transition BENEFICIARY (NZ demand +{opp.nz_growth:.0%} vs "
              f"baseline +{opp.baseline_growth:.0%}): ~{m(opp.opportunity_capex_usd)} GROWTH capital "
              f"to expand the low-carbon business (separate from the decarb-risk capex above)")
    print(f"  REALITY CHECK — company says: {published}")

# ---- Mercedes-Benz: use-phase dominates; EV pivot is the capital story ----
company("Mercedes-Benz", "road_transport_ice", "DEU", 165.7e9, 0.538e6, 0.083e6,
        26e6, 93e6, repl=40e9, target=2039,
        published="~€40bn into BEV/electrification to 2030 (R&D+capex); "
                  "fleet net-neutral 2039; ops already 47% renewable")

# ---- ArcelorMittal: Scope-1-heavy; DRI/EAF conversion is the capital story ----
company("ArcelorMittal", "steel", "FRA", 68.3e9, 108e6, 6.3e6,
        50e6, 0.0, repl=38e9, target=2050,
        published="~$10bn gross decarb roadmap for the 2030 intensity target; "
                  "Gijón €1bn H2-DRI, Ghent €1.1bn DRI+EAF, Canada DRI 2Mt+EAF 2.4Mt")

# ---- Iberdrola: clean-growth utility — decarb-PIVOT capex is low by design ----
company("Iberdrola", "power_renewable", "ESP", 53e9, 11e6, 1e6,
        8e6, 0.0, repl=120e9, target=2030,
        published="~€47bn 2023-25 (networks €27bn + renewables €17bn) — GROWTH capital, "
                  "not a decarb pivot; already ~49-77 gCO2/kWh. Note the scope difference.")

# ===========================================================================
# Opaque entity — no disclosure; estimate everything from {sector, region, revenue}
# ===========================================================================
print(f"\n{'#'*78}\nLOW-DISCLOSURE CASE — estimate from our own inputs (no reported data)\n{'#'*78}")

def opaque(name, sector, region, revenue, repl):
    # ONLY sector + region + revenue are known — no emissions, no plan, no capex.
    raw = Asset(id=name, name=name, lat=0, lon=0, asset_type="x", replacement_value=repl,
        construction_material="concrete", year_built=2005, stories=1, basement=False, roof_type="flat",
        first_floor_height_m=0, terrain_elevation_asl_m=0, floor_area_m2=0, region=region, sector=sector,
        annual_revenue=revenue)   # scope1/2/3 default to 0 (undisclosed)
    a, estimated = estimate_emissions_if_missing(raw)
    amb = scenario_ambition(SC)
    strat = build_strategy(asset_id=a.id, sector=sector, scenario_id=SC,
                           region_band=get_ngfs_region(region),
                           scope12_tco2=a.scope1_emissions_tco2 + a.scope2_emissions_tco2,
                           revenue_usd=revenue, replacement_value=repl,
                           horizon=list(range(2025, 2051)), target_year=0)
    rows = default_lever_plan(sector, a.scope1_emissions_tco2 + a.scope2_emissions_tco2, 0.0, 0.0,
                              strat.transition_capex_usd, amb, list(range(2025, 2051)))
    print(f"\n{name}  ·  {sector}  ·  {region}  ·  rev {m(revenue)}  (only sector+region+revenue known)")
    print(f"  ESTIMATED Scope 1+2 = {a.scope1_emissions_tco2/1e6:.1f} Mt  "
          f"(sector intensity {estimate_scope12_from_revenue(sector, 1e6)*1e6/1e6:.0f} t/$M × revenue) "
          f"[{'estimated' if estimated else 'reported'}]")
    print(f"  derived positioning {strat.positioning:.2f} · model-estimated capex {m(strat.transition_capex_usd)}")
    print(f"  {'Lever':32s}{'tgt':>5s}{'addr Mt':>9s}{'capex':>9s}")
    for r in sorted(rows, key=lambda r: -r.capex_usd)[:5]:
        print(f"  {r.name[:31]:32s}{r.adoption_target*100:>4.0f}%{r.addressable_tco2/1e6:>9.1f}{m(r.capex_usd):>9s}")
    print(f"  → capital plan total {m(plan_total_capex(rows))} · everything is a screening default, "
          f"flagged data_quality='degraded'.")

# An unlisted regional cement producer in an emerging market with no ESG disclosure.
opaque("Regional Cement Co (unlisted)", "cement", "IND", 2.5e9, repl=3.5e9)
