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
