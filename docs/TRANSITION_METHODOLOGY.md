# BSR Transition Risk — Methodology

**Reflects the code as built through P0–P3.** This document specifies the flow, mathematics, and
logic of the standalone transition-risk engine (`engine/transition/`) and app (`transition_app/`).
It is generated to be marked up: each section states what the code does, the exact formula, the
data behind it, and the judgment parameters you can challenge.

Companion to the physical-risk methodology. Screening-grade throughout — not a regulatory
disclosure without specialist review.

---

## 1. Overview

The engine decomposes the financial impact of decarbonisation on an asset or portfolio into **four
channels**, each mapped to one **TCFD transition-risk category**, quantified by one **engine layer**,
and routed to exactly one **financial destination** (the *non-duplication* rule):

| TCFD category | Layer | Mechanism | Routes to |
|---|:--:|---|---|
| Policy & Legal | **L1** | (Scope 1+2) × NGFS carbon price × (1 − pass-through) | Cash-flow OpEx |
| Technology | **L2** | Wright's-Law cost crossover / demand collapse → logistic impairment | Cash flow + asset value |
| Market | **L3** | Sector shock → Leontief inverse → focal input cost | Cash-flow input cost |
| Reputation | **L4** | Sautner CCExposure (z-scored) × per-SD elasticities | WACC (default) **or** cash flow |

On top of the four layers sit a **decision & assurance layer**: Monte-Carlo uncertainty, tornado
sensitivity, PCAF financed emissions, Implied Temperature Rise, PACTA-style alignment, peer
benchmarking, marginal-abatement-cost economics, a budget optimizer, and an IFRS S2 / ESRS E1
disclosure export.

### How to run
```bash
pip install streamlit pandas numpy plotly openpyxl
streamlit run transition_app/Home.py            # the app
python -m pytest tests/test_transition.py -q     # the tests (all green)
```
The engine + tests need only numpy/pandas/openpyxl/pytest. `pyam` and `pymrio` are only for the
data-refresh scripts (NGFS prices, EXIOBASE MRIO).

---

## 2. Architecture & module map

```
engine/transition/
  data_loader.py        cached JSON loaders; ISO3→NGFS region; scenario→NGFS mapping
  carbon_pricing.py     L1 — carbon cost, pass-through, abatement pathway, priced fraction
  learning_curves.py    L2 — Wright's law, Lafond bands, crossover, logistic impairment
  adaptive_capacity.py  L2 modifier — ambition / positioning / capture / transition capex (residual risk)
  network_propagation.py L3 — world 20×20 Leontief propagation
  network_mrio.py       L3 — 20×49 EXIOBASE MRIO + Reisch endogenous-default cascade
  cc_exposure.py        L4 — z-standardised CCExposure × per-SD elasticities + routing
  transition_engine.py  orchestrator: run_asset_transition / run_portfolio_transition
  transition_dcf.py     combined physical+transition DCF hook
  uncertainty.py        Monte-Carlo over price / pass-through / elasticity
  sensitivity.py        one-at-a-time tornado
  alignment.py          financed emissions, ITR, pathway alignment, peer benchmark
  macc.py               marginal abatement cost curves (decarbonise vs pay)
  optimizer.py          budget-constrained merit-order abatement allocation
  levers.py             decarbonization lever library — sector→lever map + plan overlay (reference)

data/transition/
  carbon_prices_ngfs.json      NGFS Phase V REMIND-MAgPIE (real, ×1.18 → USD2020)
  sector_pass_through.json     sector-median pass-through
  learning_curves.json         learning rates + LCOE base costs (IRENA 2024 / Lazard 2025)
  sector_pathways.json         demand pathways (production index, 2025=1.0)
  cc_exposure_proxy.json       sector CCExposure (real ×10³ scale) + pooled z-base + elasticities
  io_matrix.json               20×20 world direct-requirements matrix (EXIOBASE world totals)
  io_matrix_mrio.npz + meta     20×49 EXIOBASE MRIO (980×980)
  sector_taxonomy.json         20 sectors: tech pairs, fossil flag, emission intensity
  macc.json                    per-sector abatement measures (AR6 WG3 / IEA-informed)
  lever_library.json           29 decarbonization levers × 5 domains + sector→lever value-chain map
  adaptive_capacity.json       scenario→ambition, lever→readiness, sector pivot-capex ratios, region buffers
  region_factors.json          geographic resource/cost zones → region-aware LCOE (renewable / green-H2 / fossil)
```

### Execution flow
```
① Data Entry  →  intake per entity: sector, Scope 1/2/3, replacement value, revenue,
                 target_year, priced_pct, attribution_pct
        │
        ▼
   run_portfolio_transition(assets, scenarios, …settings…)
        │  for each (scenario, asset):
        │    L1 carbon_cost_timeline(...)          → net_carbon_opex[y]
        │    L2 compute_stranding(...)             → impairment[y], revenue_erosion[y]
        │    L3 propagate (world | mrio+cascade)   → indirect_input_cost[y]
        │    L4 compute_exposure_premium(...)      → revenue_modifier[y] OR wacc_bps
        │    total_cf[y] = L1 + L2_rev + L3 + L4 ;  impairment separate
        ▼
   Results / category pages / Alignment / Abatement / Audit
        →  PV, Monte-Carlo P5–P95, tornado, ITR, PCAF, MACC, XLSX + IFRS S2 export
```

---

## 3. Layer 1 — Policy & Legal (direct carbon cost)

**Module:** `carbon_pricing.py`. For each (scenario, region, year, sector):

### 3.1 Carbon price
`get_carbon_price(scenario, year, band)` linearly interpolates the NGFS trajectory and holds it
flat outside 2025–2050, then multiplies by a Monte-Carlo perturbation `price_scale` (1.0 = base):

```
price(y) = interp(NGFS[scenario][band], y) × price_scale
```
Region **band** ∈ {advanced, emerging, rest_of_world} from `get_ngfs_region(ISO3)`. IPCC SSP
scenarios map to their closest NGFS analog.

### 3.2 Abatement pathway (P0)
An entity with a Scope 1+2 net-zero **target_year** decarbonises linearly; carbon cost then applies
only to the declining residual:
```
abatement_mult(y) = 1.0                              if no target or y ≤ 2025
                  = residual                          if y ≥ target_year          (residual = residual_pct/100)
                  = 1 + (y−2025)/(target−2025)·(residual−1)   otherwise
```

### 3.3 Cost decomposition
```
direct       = (Scope1 + Scope2) × abatement_mult(y)
pass_through = min(1, sector_PT × pt_scale)          (or per-asset override)
opportunity  = direct × price                        full carbon opportunity cost
passed_through = opportunity × pass_through           ← L3 market shock (undiminished by free allocation)
net_compliance = opportunity × priced_fraction        allowances the firm actually buys
absorbed     = net_compliance − passed_through        firm's net margin impact (windfall if < 0)
scope3_indirect = Scope3 × price × (1 − pass_through)
net_carbon_opex = absorbed + scope3_indirect          ← what hits the firm's cash flow
```

- **Windfall economics (Round-1 P5).** The marginal carbon price sets the pass-through opportunity
  cost regardless of free allocation (Sijm 2012), so pass-through — and the L3 shock — are based on
  the **full opportunity cost**; `priced_fraction` reduces only the firm's own compliance leg. With
  generous free allocation and high pass-through, `absorbed` goes **negative** (a windfall gain). At
  the default `priced_fraction = 1` this reduces to `absorbed = opportunity × (1 − PT)` (legacy).
- **priced_fraction** models free allocation / partial ETS coverage (P0). Default 1.0.
- **Scope-2 & Scope-3 incidence (external review).** Purchased-electricity carbon (Scope 2) and
  upstream Scope 3 are *supplier* costs that reach the firm through prices, which Layer 3 already
  models. Charging them again as a direct L1 liability double-counts, so **`scope2_mode` and
  `scope3_mode` now default to `auto`**: both are dropped from L1 whenever Layer 3 is enabled —
  Scope 2 unless the firm pays an explicit carbon charge on its electricity (`scope2_mode="direct"`).
  `full` keeps them in L1 and should be used only with Layer 3 off. `scope3_incidence` (R3) lets
  the analyst set the supplier-to-buyer pass-through directly.

**Data:** `carbon_prices_ngfs.json` — real **NGFS Phase V** (released Nov 2024) REMIND-MAgPIE 3.3-4.8
prices pulled live from the IIASA `ngfs_phase_5` explorer, rebased ×1.18 (US GDP deflator 2010→2020)
to ~USD2020. Six scenarios carry real data; `divergent_net_zero` + three IEA scenarios retain
Appendix-D placeholders. *(Round-1 P4: the Kotz et al. 2024 retraction affects only NGFS
physical-damage variables, not the transition/price pathways — L1 uses standard REMIND-MAgPIE
transition price variables and is unaffected.)*
**Pass-through:** `sector_pass_through.json`, sector medians (Sijm 2012; Fabra & Reguant 2014; Cludius 2020).

---

## 4. Layer 2 — Technology (learning curves & stranding)

**Module:** `learning_curves.py`. The projection and its uncertainty band implement the
**Farmer–Lafond** empirically-grounded experience-curve forecast (Farmer & Lafond 2016; Way, Ives,
Mealy & Farmer 2022): a geometric random walk with drift on log-cost, whose forecast error grows as
σ·√(horizon). Way et al. (2022)'s central finding — clean tech on persistent exponential decline while
fossil stays flat, so a **fast transition is the low-cost path** — grounds both the crossover logic
here and the scenario-narrative ambition defaults in §4.6. Learning rates and base costs are from
primary datasets (IRENA 2024, Lazard 2025 v18, the Oxford/Way 2022 dataset, BNEF 2024, Ziegler &
Trancik 2021) — **not** the BSR lever library.

### 4.1 Wright's Law
```
Cost(Q) = Cost₀ × (Q/Q₀)^b ,   b = log₂(1 − LR)
Q/Q₀ = (1 + g)^(y − 2025) ,     g = max(0, scenario deployment growth)
```
Negative growth (demand decline) is clamped to 0 — cumulative capacity is monotonic; demand decline
is handled by the sector pathway, not the cost curve.

### 4.2 Farmer–Lafond distributional band
```
σ_t = lafond_σ × √(y − 2025)
cost_lo = pred × e^(−σ_t) ,  cost_hi = pred × e^(+σ_t)
```

### 4.3 Stranding trigger (either fires)
- **Cost crossover** — first year challenger cost ≤ incumbent cost.
- **Demand collapse** (fossil-dependent sectors only) — first year the sector pathway falls below 0.5.
- **Tech-substitution stranding (diagnostic fix #3).** Even where DEMAND holds (steel, cement), a cost
  crossover obsoletes the incumbent asset (blast furnace, wet kiln) and it is written off. The
  carbon-specific share (`TECH_SUBSTITUTION_SHARE ≈ 0.45`) strands in proportion to how much the firm
  transitions (ambition), paired with the capex that builds the replacement. Cap =
  `max(demand_cap, tech_cap) × base`. Steel now shows ~$4B stranding on a $18B works (was $0);
  cement/chemicals stay ~$0 (no cost crossover — they need costly CCUS, not obsoletion by a cheaper tech).
- **P6 — carbon-inclusive crossover (opt-in).** When enabled, the incumbent's effective cost adds its
  carbon cost `carbon_price(scenario, region, y) × carbon_ef_per_unit` (Scope-1 emission factor in the
  tech's cost unit; fossil incumbents only). A rising carbon price then pulls the crossover — and
  stranding — earlier. Off by default → pure-LCOE crossover, preserving anchors.
- **R6 — crossover band.** The Lafond ±1σ bands give an *early* (challenger-low vs incumbent-high) and
  *late* (challenger-high vs incumbent-low) crossover year that bracket the central estimate; surfaced
  as a crossover range in the Technology page and as an impairment tornado driver.

### 4.4 Impairment
```
frac(y)  = 1 / (1 + e^(−slope·(y − crossover)))          logistic
slope    = per-sector (R7; default 0.20)                 e.g. power_coal 0.20 (anchor), ICE autos 0.22
base     = replacement_value            if fossil-dependent
         = replacement_value × f        otherwise, f = non_fossil_base_fraction (R1; default 0.5)
cap      = max(0, 1 − pathway(2050)) × base               scenario-scaled ceiling
annual_impairment(y) = (frac(y) − frac(y−1)) × cap
```
Impairment is a **balance-sheet** figure, reported separately from cash flow.
**% stranded = recognised, not the ceiling (external review finding 1).** The headline
`stranded_fraction_2050` is the *recognised* cumulative impairment over 2025–50 ÷ replacement value,
so it always equals the dollar impairment (e.g. coal ≈ **53%** = $266M ÷ $500M). The logistic *level*
at 2050 (which includes pre-2025 stranding never booked) is reported separately as the
`strandable_ceiling` (coal ≈ 98%). The two must not be conflated.
**R7 — per-sector slope** is read from `sector_taxonomy.stranding_slope` (calibrated to asset-turnover
speed; power fast, heavy industry & networks slow); the two documented calibration anchors (power_coal,
oil_refining) are held at the legacy 0.20. **R1 — non-fossil base fraction** is configurable in the UI.

### 4.5 Revenue erosion
```
revenue_index(y) = sector pathway(y)            (production index, 2025 = 1.0)
revenue_erosion(y) = max(0, revenue × (1 − index(y)))     ← cash-flow cost
```

**Data (P0 refresh):** power-sector base costs are **LCOE (USD/MWh)** from **IRENA Renewable Power
Generation Costs in 2024** and **Lazard LCOE+ 2025 v18** (coal 118, gas 76, solar 43, onshore wind 34,
storage 170). Learning rates: Way et al. 2022 / IRENA. Industrial base costs remain sector estimates.

### 4.6 Adaptive capacity — gross exposure → residual risk
**Module:** `adaptive_capacity.py` + `adaptive_capacity.json`. §4.5 as written erodes ~100% of the
incumbent product's revenue — a *frozen* company that captures nothing from the low-carbon business
(an ICE automaker losing all revenue with $0 from EVs). That is **gross vulnerability**, not residual
risk. This layer (**ON by default**) converts it into "how the company looks if it follows the scenario
pathway, given where it starts." Approach follows BSR's *Decarbonization Lever Library: Mapped Sectoral
Transition Pathways* (Nov 2025) — business-transformation / systemic-adaptability framing.

Three levers:
```
ambition A ∈ [0,1]     default from the SCENARIO NARRATIVE (NZ-2050 ≈ 0.90, Current Policies ≈ 0.20);
                        overridable. Also implies an emissions pathway (residual = 1−A) that lowers L1
                        when no explicit decarbonisation target is set — so the pivot is never free.
positioning P ∈ [0,1]  "science": 0.35·plan_strength(target+in-plan lever coverage) + 0.30·sector
                        lever readiness (Lever-Library maturities) + 0.20·emissions-vs-sector
                        + 0.15·plan coverage. "art": a manual override on Data Entry.
capture  = min(A · P^1.15, opportunity_ceiling)     share of gross erosion offset by pivoting
```
Effects (each routes once):
```
net_revenue_erosion(y) = gross_erosion(y) × (1 − capture)          ← CASH FLOW (reduced)
transition_capex(y)    = phased[ A · replacement_value · sector_pivot_ratio                ← CASH FLOW (new)
                                 · region_multiplier · positioning_capex_factor ]           (company-provided, else estimated)
strandable_base       ×= (1 − already_transitioned),  already = 0.5·P                       ← BALANCE SHEET (less to strand)
```
Transition capex is company-provided (they know their plan), else estimated from pivot scale × sector
ratio × a **geographic/context buffer** (advanced 1.0, emerging 1.1, RoW 1.2) × a positioning factor
(laggards pay up to 1.6×, movers 0.8×). Worked example — automaker ($100B rev) under NZ-2050:
gross $791B PV → **$318B** if strongly positioned & ambitious (80% capture, $14B capex, less stranding),
vs **$740B** if a poorly-positioned laggard (10% capture, $24B capex). Present positioning drives the
outcome. Positioning derivation is a screening heuristic — the "art" override exists for exactly the
cases it cannot cleanly quantify.

### 4.7 Geography — region-aware technology costs
**Data:** `region_factors.json`. The learning-curve LCOEs are world averages, but a watt in Texas or
MENA is far cheaper than in Northern Europe or Japan, and green steel / ammonia / cement is cheapest
where clean power is cheap. Each ISO3 maps to a **resource zone** carrying three multipliers on a
technology's LCOE before the crossover comparison:
```
clean power   (renewable_lcoe_factor)  → solar, wind, storage, PPAs
green H2 etc. (green_h2_factor)        → electrolyser, H2-DRI steel, green ammonia, SAF, biorefining
fossil        (fossil_lcoe_factor)     → REGIONALLY-PRICED energy only: natural gas + grid electricity
```
`_project_cost` multiplies by the zone factor, so `find_crossover_year` and stranding are **region-aware**.
Only regionally-priced fossil energy (gas, grid power) carries a factor; globally-traded commodities
(coking coal, crude oil, and the coal/oil-based incumbents — blast furnace, cement, refining, jet/bunker
fuel) stay at 1.0, so the **green challenger's** regional cost drives the crossover — green steel is
earliest where clean power / green H₂ is cheapest (the intuitive result). Factors follow IRENA regional
LCOE dispersion (best solar ~$0.03/kWh in MENA/sunbelt/Chile/Australia/Iberia vs ~$0.06–0.09 in N.
Europe/Japan) and regional gas prices; the USA-national / global-average zone is the 1.0 reference, so
the world-average curves and worked-example anchors are unchanged.

**Sub-national resolution (US & Europe — highest-importance markets).** Enter the region as an
ISO3-prefixed code — `USA-TX`, `USA-CA`, `USA-SW`, `ESP-S`, `ITA-N` … — resolved sub-national → country
→ global, and stripped to the country for the carbon-price band. US grid/resource zones: Texas (ERCOT),
Southwest, Midwest wind belt, California, Southeast, Northeast, Pacific NW. Europe is country-resolved
into UK & Ireland, N. Europe, Nordics, Iberia, S. Europe, C./E. Europe. Effect — **green-steel (H2-DRI)
crossover: US Southwest 2026 · Texas 2027 · California 2034 · US-national 2036 · US Northeast 2039;
Spain 2031 · UK 2038 · Germany 2040 · Japan 2042** (same plant). A watt in Texas ≠ one in California;
green steel in Iberia ≠ in Germany. *Limitation:* US is resolved to ~7 grid regions and Europe to
country/macro-region — not to individual states/provinces or specific balancing authorities yet.

---

## 5. Layer 3 — Market (production-network propagation)

**Modules:** `network_propagation.py` (world), `network_mrio.py` (MRIO + cascade).

### 5.1 Sectoral shock
Each sector's carbon shock as a fraction of its output:
```
sᵢ = min(1.0, emission_intensityᵢ × price × pass_throughᵢ × 1e−6)
```
(emission_intensity in tCO₂ per **M$ of sector gross output**; 1e−6 → per-USD.) **Scale correction
(external review finding 3):** the intensities were ~1000× too low (implied t/$k), which made L3
invisible; they are now realistic EEIO/EXIOBASE-informed direct Scope-1 intensities (fossil sectors
O(1000s) tCO₂/M$, services O(10s)), verified against the fixtures by a unit test. Each sector shock is
**clamped to 1.0** — carbon cost cannot inflate a sector's output price by more than 100% in the linear
Leontief basis; beyond that the sector is stranding (Layer 2), not passing input cost. The shock also
responds to the Monte-Carlo `price_scale` and `pass_through_scale` in both the world and MRIO paths.
Using sector-typical exposure avoids
double-counting the focal asset's own pass-through.

### 5.2 Leontief propagation
```
L = (I − A)⁻¹
total_shock_j = Σᵢ L[i,j] · sᵢ
propagated_j  = total_shock_j − own       (own = s_j, the single L1 direct round — P3)
indirect_cost = propagated_j × (asset_revenue × intermediate_input_share) × absorption
```
**Input-share basis (diagnostic fix #1).** L3 scales by the firm's carbon-EXPOSED input base —
`revenue × intermediate_input_share` (bought-in intermediate inputs, 1 − value-added) — NOT total
revenue. Previously a labour/margin-heavy firm (financial services 96%-of-cost L3, ~$7B on a bank)
booked an implausible supply-chain carbon cost; with the input-share basis (finance ≈ 0.28, refining
≈ 0.85) that collapses to ~$2B and heavy processors keep a large, legitimate L3.
**CES damping:** off-diagonal A scaled by 1/σ before inversion (σ = substitution elasticity;
Papageorgiou 2017 range 1.3–3.0). σ=1 is Cobb-Douglas.

**R2 — partial pass-through (opt-in).** `absorption` is the share of the propagated upstream cost the
focal firm *absorbs* rather than passing to its own customers. Default 1.0 (full absorption, legacy).
When enabled it is set to `1 − pass_through_j`, so sectors with pricing power recover part of the
input-cost shock downstream and their net margin impact falls.

### 5.3 Resolution (P2)
- **World** (default): 20×20 single-region matrix (EXIOBASE-3 world totals, `io_matrix.json`).
- **Multi-region**: full **20 sectors × 49 regions = 980×980** EXIOBASE MRIO (`io_matrix_mrio.npz`).
  Cross-border supply chains are explicit and each region's sectors pay carbon on **that region's
  price band**, so an EU refiner's indirect cost reflects emerging-market upstream at a different
  carbon price. Leontief inverts in ~0.1 s.

### 5.4 Endogenous-default cascade (P2, Reisch et al. 2025)
Beyond linear Leontief, nodes absorbing input-cost shock above threshold **θ** pass an amplified
shock downstream, iterated to convergence:
```
s_eff = s
repeat:  total = L · s_eff ;  over = max(0, total − θ) ;  s_eff = s + contagion · over
```
Default off; triggers only for the most-exposed nodes under stress (θ≈0.02 → ~1.25× for CHN steel;
θ=0.01 → ~6.8×).

---

## 6. Layer 4 — Reputation (CCExposure, z-standardised)

**Module:** `cc_exposure.py`. **P0 fix (D3):** raw 0–2 proxies inflated elasticities ~500–1000×; the
engine now consumes **z-scores** against the real Sautner distribution and prices **per standard
deviation**.

```
rawₓ = sector_exposureₓ × scenario_modifierₓ          x ∈ {opp, reg, phy}
zₓ   = (rawₓ − pooled_meanₓ) / pooled_sdₓ
z_total = (Σ rawₓ − pooled_mean_total) / pooled_sd_total

credit_spread_bps = 12·z_reg + 6·z_phy
equity_premium_bps = 18·z_reg + 9·z_phy − 25·z_opp     (downside raises cost of equity; opportunity is a DISCOUNT)
revenue_growth_bps = 35·z_opp − 25·z_reg
```
**Sign fix (trial-run finding).** The equity premium previously used `50·z_total`, which lumps
opportunity in with downside — so a renewables firm (high opportunity) got a *higher* cost of capital
for being a climate winner, and the WACC and cash-flow routes disagreed in sign. It now prices the
**downside** components (regulatory + physical) positively and the **opportunity** component as a
**discount**, consistent with the carbon-premium / greenium literature (Bolton & Kacperczyk 2021;
Zerbib 2019). Result: renewables ≈ **−33 bps** ΔWACC (cheaper capital), coal ≈ **+27 bps** (penalty),
neutral sectors ≈ 0.
The **pooled distribution** is Sautner et al. (JoF 2023) **Table 1** (firm-year, ×10³): opp 0.391/1.344,
reg 0.049/0.264, phy 0.013/0.103, total 0.943/2.443. **Sector exposures** are anchored to Sautner
**Table 4** by SIC industry where available (utilities → power, petroleum refining, transport
equipment → autos, primary metal → steel …), estimated from adjacent industries otherwise.

Effect: average-exposure sectors carry ≈0 premium; coal keeps ~29 bps credit and a **+27 bps WACC
penalty**; renewables now receive a **−33 bps WACC discount** (and, on the cash-flow route, a revenue
uplift) — a climate winner is financed more cheaply, not penalised.

**Routing (non-duplication):** `ROUTE_WACC` (**default, R5**) adds the equity premium to the discount
rate and zeroes the revenue modifier; `ROUTE_CASHFLOWS` applies the revenue-growth modifier to cash
flows instead. **Firm override (P2):** a licensed firm-level CCExposure feed replaces the sector
median via `firm_override`.

**R5 — elasticity provenance (which coefficient is real).** Only one of the three L4 elasticities is
sourced, and the default routing reflects that:

| Coefficient | Value | Provenance | Route |
|-------------|-------|-----------|-------|
| **equity → WACC** | 18·z_reg + 9·z_phy − 25·z_opp bps | **SOURCED (downside)** — Sautner Pricing: cost-of-capital premium concentrated in regulatory/physical exposure; opportunity **discount** informed by the greenium literature | **WACC (default)** |
| credit spread | 12·z_reg + 6·z_phy bps | **UNSOURCED placeholder** — plausible sign/magnitude, not fitted | diagnostic only |
| revenue growth | 35·z_opp − 25·z_reg bps | **UNSOURCED** — market-opportunity judgement, not an estimated elasticity | manual cash-flow overlay |

Because the equity→WACC channel is the only empirically grounded one, `ROUTE_WACC` is the default and
the cash-flow revenue route is presented in the UI as a **manual analyst overlay**, not a model output.
The credit-spread figures are shown for diagnostics but never routed into headline numbers.

---

## 7. Orchestration & non-duplication

`run_asset_transition(asset, scenario, …)` composes the layers. Each channel routes once:

```
total_cf(y) = L1 net_carbon_opex
            + L2 revenue_erosion
            + L3 indirect_input_cost
            + L4 revenue_modifier (as a cost: −modifier)    (only if ROUTE_CASHFLOWS)
impairment(y) = L2 annual_impairment            (balance-sheet, NOT in total_cf)
ΔWACC_bps  = equity_weight·equity_premium + debt_weight·credit_spread·(1−tax)   (only if ROUTE_WACC)
```
**Capital-structure-weighted WACC (external review finding 4).** The L4 premium is no longer
`credit + equity` added one-for-one; the equity premium enters the cost of equity and the credit
spread the after-tax cost of debt, weighted by capital structure (default 60/40, 25% tax). It is now
**actually applied** in `transition_dcf.compute_combined_dcf` (added to `climate_risk_premium` for the
transition and combined DCFs) — previously it was computed but never discounted, so L4→WACC had no
valuation effect. `run_portfolio_transition` runs all assets × scenarios and returns
`{scenario: [TransitionAssetResult]}`, each tagged with a **data-quality flag** (firm / sector-proxy /
degraded) that surfaces on the Audit page.

**Firm-level roll-up (diagnostic fix #4).** Assets sharing a `firm_id` roll up into one diversified
company via `firm_rollup()` — a multi-line, multi-region firm gets one consolidated cost/impairment
view across its business lines (surfaced on the Results page). Each line keeps its own sector- and
region-specific positioning (correct: a steel division and a data-centre division transition
differently). This is an INDEPENDENT sum — group-level correlation, cross-subsidy, shared capital and
a single optimised group plan are **not** modelled (documented limitation).

**Present value & discount basis (Round-1 P2 + external review).** Carbon prices are **real**
(USD2020), so PV discounts the real cash flows at a **real** rate = nominal WACC − long-run inflation.
Discounting real flows at the nominal WACC would systematically understate PV. Both are app inputs
(nominal WACC default 9%, inflation 2.5% → real 6.5%). **One timing convention** is now used everywhere —
end-of-year `PV = Σ cost / (1 + real)^(y − 2025 + 1)` — across the DCF engine, Monte-Carlo, tornado,
disclosure export and the stranded-impairment PV (previously these mixed `y−2025` and `y−2025+1`).

**Impairment vs cash-flow cost are NOT additive (Round-1 P1).** L2 stranded impairment is the PV
writedown of the same future cash flows whose erosion already feeds the cash-flow cost. They are two
**lenses on one loss** — reported side by side, never summed into a combined total (enforced in the
dashboard, XLSX, and disclosure export; guarded by a test).

---

## 8. Uncertainty & sensitivity

### 8.1 Monte-Carlo (`uncertainty.py`)
Re-runs the four layers over N draws (default 400), perturbing:
```
price_scale        ~ LogNormal(0, 0.20)      carbon-price / policy path
pass_through_scale ~ Normal(1, 0.10)         cost incidence
elasticity σ       ~ Uniform(1.0, 2.5)       network substitution
```
Returns P5 / P50 / P95 of PV transition cost and stranded impairment. Seed-deterministic.

**U1 — the P5–P95 range is a *conditional floor*, not full uncertainty.** It is conditional on the
selected scenario and varies only the three sampled parameters — it excludes scenario/policy-path
uncertainty, the L2 stranding trigger-year and the demand pathway. The UI labels the P95 accordingly
and points to the tornado for the excluded drivers.

### 8.2 Tornado (`sensitivity.py`)
One-at-a-time swing of each driver, all others at base, sorted by |swing|. Two targets (U1):
- **Cash-flow cost** — carbon price ±30%, pass-through ±20%, L3 input-cost pass-through (R2),
  σ 1.0–2.5, Scope-3 mode, discount ±2pp.
- **Stranded impairment** — crossover trigger (pure-LCOE vs carbon-inclusive, R6/P6), stranding slope
  0.12–0.35 (R7), non-fossil base share 0.25–0.75 (R1), carbon price ±30%, discount ±2pp. This view
  surfaces the trigger-year and base assumptions that dominate stranding but are invisible to the
  cash-flow tornado and to the Monte-Carlo floor.

---

## 9. Decision & alignment layer

### 9.1 Financed emissions — PCAF (`alignment.py`)
Attributed emissions = Σ `attribution_pct` × (Scope 1/2/3). 100% = corporate own-asset view; a
lender/investor enters their stake.

### 9.2 Emissions-budget temperature score (screening ITR proxy)
A **screening indicator**, NOT a standard-compliant Implied Temperature Rise (SBTi / CDP-WWF
temperature scoring). Each entity's abated Scope 1+2 pathway vs a 1.5 °C linear-to-net-zero budget:
```
budget = 0.5 × E₀ × (2050 − 2025)                     area under a straight line to zero
ratio  = cumulative_actual / budget − 1
score  = clamp[1.5, 4.0]( 1.5 + 1.2 × ratio )         floored at 1.5 °C best case
portfolio score = Scope1+2 × attribution weighted mean
```
Net-zero-by-2050 ≈ 1.5 °C; flat emissions ≈ 2.8 °C. **External review:** the old 1.2 °C lower bound
implied sub-1.5 alignment and was not defensible — the floor is now the 1.5 °C best case. Report this
as a screening score, not a certified ITR.

### 9.3 Pathway alignment (PACTA-style)
Compares the entity's Scope 1+2 decline by 2050 to the scenario's sector demand pathway;
gap ≤ 0.05 → aligned, ≤ 0.25 → lagging, else misaligned.

### 9.4 Peer benchmarking
Entity economic intensity (tCO₂ Scope 1+2 / $M revenue) vs the **real Sautner firm-level Carbon
Intensity distribution** (JoF 2023 Table 1: median 11, p75 84.6 across ~10k firms) → quartile position.

### 9.5 Marginal abatement cost curves (`macc.py`)
Per-sector measures (cost USD/tCO₂, potential share of Scope 1+2). At carbon price P, all measures
with cost ≤ P are cost-effective:
```
abated_frac = Σ potential (cost ≤ P) ,  capped at 1
abatement_cost = Σ cost × potential × emissions
carbon_cost_avoided = abated × P ,  net_benefit = avoided − cost
```

### 9.6 Budget optimizer (`optimizer.py`)
Merit-order greedy: sort all measures across the portfolio by $/tCO₂; fund no-regret (negative-cost)
measures always, then buy cheapest-first until the budget is exhausted. Returns abated tonnes, net
spend, marginal-cost frontier, residual carbon cost, and per-asset allocation. Optimal for max
tonnes per dollar under a linear MACC.

### 9.7 Disclosure export
`build_disclosure_report` generates a Governance → Strategy → Risk Management → Metrics report mapped
to **IFRS S2** clauses and **ESRS E1** datapoints, plus a provenance-stamped multi-sheet XLSX.
**U2 — the experimental endogenous-default cascade (§5.4) is hard-excluded from the disclosure in
code:** the report recomputes its figures with `cascade=False` regardless of the UI toggle, and states
the exclusion, so a research amplification can never leak into a regulatory-style export.

### 9.8 Decarbonization Lever Library (structured reference — NOT a score)
`engine/transition/levers.py` + `data/transition/lever_library.json`. Approach adapted from **BSR's
Decarbonization Lever Library**: for each entity, map its *sector* to the specific decarbonization
levers available to it, positioned by **value-chain stage** — upstream (purchased inputs/suppliers),
own operations (Scope 1+2), downstream (products/customers/use-phase) — then overlay the entity's own
**transition plan** to expose coverage and gaps.

- **29 levers in 5 domains** (Electricity & Energy, Transport, Industry, Buildings, FLAG & Water). Each
  lever carries: indicative abatement-cost band ($/tCO₂e), global mitigation potential (high/med/low),
  commercial maturity (mature→frontier), 2050 role, key dependencies, a **nature & people** ("just
  transition") note at each value-chain stage, applicable sectors, and sources.
- **`sector_lever_map`** links all 20 taxonomy sectors to their levers, each tagged with value-chain
  position and relevance (primary/secondary) plus a rationale.
- **Plan overlay** (`overlay_plan`) is a **manual analyst input** — the analyst ticks which levers are
  in the plan — and returns a *factual* count (primary levers covered / total) and a gap list. It
  deliberately emits **no synthetic readiness score** (BSR "do-not-automate" boundary): the value is in
  surfacing which core abatement routes are unaddressed, not in rating the plan.
- **Data discipline:** the *mapping and value-chain logic* are carried over from BSR; the underlying
  cost/maturity/potential figures are **refreshed** indicative screening ranges (IEA NZE 2023, WEO
  2024; IPCC AR6 WG3; IRENA 2024; Lazard 2025; Mission Possible Partnership) — not lifted from the
  original report.

Surfaced in the app as page **⑪ Levers** (entity lever map + plan overlay + full-library reference,
CSV export).

---

## 10. Data provenance & vintages

| Component | Source | Vintage |
|---|---|---|
| Carbon prices (L1) | NGFS Phase V REMIND-MAgPIE 3.3-4.8 (IIASA), published Nov 2024 | US$2010 series ×1.18 (US GDP deflator) → US$2020 |
| Pass-through (L1) | Sijm 2012; Fabra & Reguant 2014; Cludius 2020 | sector medians |
| Learning rates (L2) | Way et al. 2022; IRENA | 2022–23 |
| LCOE base costs (L2) | IRENA RPGC 2024; Lazard LCOE+ 2025 v18 | 2024–25 |
| I-O matrix (L3) | EXIOBASE-3 (Stadler et al. 2018), IOT 2019 | 2019 |
| CCExposure + z-base (L4) | Sautner et al. JoF 2023 Tables 1 & 4 | 2002–2019, 10k firms |
| Sector pathways | NGFS / IEA WEO 2023 | 2023 |
| MACC | IPCC AR6 WG3; IEA roadmaps | 2022–23 |

---

## 11. Calibration — worked examples (default settings)

- **Coal plant** ($500M, 2.5 MtCO₂): Net-Zero-2050 cumulative impairment **$266.1M** — now reported as
  **53% recognised** stranded (= $266M ÷ $500M), against a **98% strandable ceiling** (crossover 2025).
  Current Policies ≈ $33M.
- **Oil refinery** ($2B, 12.8 MtCO₂): stranding triggered by **demand collapse** (crossover 2039), not
  cost crossover; cumulative impairment ≈ $1.36B.
- **Office** ($50M, 1k tCO₂): no stranding; small net cost / reputational uplift.

Impairment dollars are unchanged by the upgrades (abatement/priced default to legacy; anchor sectors
hold slope 0.20). What changed at the external-review stage: the **% stranded label** now reports the
recognised figure (53%) not the ceiling (98%); L1 cash-flow cost is lower where Scope 2/3 shift to L3
under the new `auto` default; and L3 is now materially larger after the emission-intensity scale
correction.

---

## 12. Known limitations (challenge these)

- **Pass-through** is a static sector median; firm-specific values vary with market power and trade
  exposure. Override per asset.
- **CCExposure** sector exposures are anchored to published SIC-industry means, estimated for sectors
  not in Table 4; the licensed firm-level feed is the fix.
- **MRIO twin sectors** (`road_transport_ev`, `real_estate_residential`) are supply-split from their
  siblings (EXIOBASE has no separate EV / residential-RE industry).
- **Cascade θ / contagion** are judgment parameters; the linear result is the default.
- **ITR / MACC / peer benchmark** are screening approximations aligned to SBTi/PACTA/PCAF/AR6 in
  spirit, not certified implementations.
- **Carbon-price vintage** is NGFS Phase V (Nov 2024); refresh for disclosure.
- Emissions decarbonise only if a target is set; without one, Scope 1+2 are held flat.
- **Structural simplifications (Round-1 U3):** (i) IAM shadow prices are treated as *realised*
  carbon prices — a first-best assumption that overstates cost where policy underdelivers;
  (ii) the default world 20×20 matrix carries I-O aggregation bias; (iii) three price bands
  (advanced/emerging/RoW) proxy NGFS's ~12 model regions (the 20×49 MRIO mode relaxes this).
- **Endogenous-default cascade (Round-1 U2)** rests on Reisch et al. 2025, an un-peer-reviewed
  preprint — research-grade only; default-off and excluded from the disclosure export.
- **Firm-level roll-up (diagnostic fix #4)** is an independent sum of business lines — no group
  correlation, cross-subsidy, shared capital, or single optimised group transition plan.
- **`io_proxy` sectors (diagnostic fix #5/#6):** the 7 sectors added after the 20×20 matrix
  (apparel, consumer goods, financial services, healthcare, professional services, telecom, metals
  mining) borrow an existing matrix row for Layer-3 propagation; a native row needs an I-O rebuild.
- **`intermediate_input_share` (diagnostic fix #1)** is a sector-median value-added split; firm-level
  COGS/input structure would sharpen L3.

---

## Appendix A — Sector taxonomy (27 sectors)
Key · label · incumbent → challenger · fossil-dependent · emission intensity (tCO₂/M$) ·
intermediate-input share · io_proxy (where applicable). See `data/transition/sector_taxonomy.json`.
The **20 core** sectors span power (coal/gas/renewable), oil & gas (upstream/refining/distribution),
heavy industry (steel/cement/chemicals/aluminium), transport (road ICE/EV, aviation, shipping), real
estate (commercial/residential), agriculture, data centres, general manufacturing, and services.
**+7 BSR lever-library sectors (diagnostic fix #5/#6)** added via `io_proxy`: apparel & textiles,
consumer goods, financial services, healthcare, professional services, telecommunications, and metals
& mining (a transition **beneficiary** — demand grows, no product-demand stranding).

## Appendix B — Pass-through coefficients
See `data/transition/sector_pass_through.json` (pass-through, demand elasticity, market structure,
trade exposure, source).

## Appendix C — Learning rates & LCOE
See `data/transition/learning_curves.json`. Power LCOE (USD/MWh): coal 118, gas 76, solar 43,
onshore wind 34, storage 170 (IRENA 2024 / Lazard 2025).

## Appendix D — NGFS carbon prices
See `data/transition/carbon_prices_ngfs.json`. Real REMIND-MAgPIE, three bands, 2025–2050.

## Appendix E — Layer-4 z-base & elasticities
Pooled distribution (Sautner Table 1, ×10³): opp 0.391/1.344 · reg 0.049/0.264 · phy 0.013/0.103 ·
total 0.943/2.443. Per-SD elasticities (bps): equity 18·z_reg + 9·z_phy − 25·z_opp (downside premium +
opportunity discount); credit 12·z_reg + 6·z_phy; revenue 35·z_opp − 25·z_reg.

## Appendix F — MACC measures
See `data/transition/macc.json`. Per-sector measures with marginal cost (USD/tCO₂) and abatement
potential (share of Scope 1+2); AR6 WG3 / IEA-informed.

## Appendix G — References
NGFS Phase V (IIASA) · Sijm 2012 · Fabra & Reguant 2014 · Cludius 2020 · **Farmer & Lafond, Research
Policy 2016** · **Way, Ives, Mealy & Farmer, Joule 2022** · Lafond et al. TFSC 2018 · IRENA RPGC 2024 ·
Lazard LCOE+ 2025 v18 · BloombergNEF 2024 · Ziegler & Trancik 2021 · Stadler et al. (EXIOBASE) 2018 ·
Acemoglu et al. 2012 · Papageorgiou et al. 2017 · Reisch et al. 2025 (arXiv:2503.10644) ·
Sautner, van Lent, Vilkov, Zhang (JoF 2023; Mgmt Sci 2023) · Bolton & Kacperczyk (JFE 2021) ·
Zerbib (Rev. Finance 2019) · BSR *Decarbonization Lever Library* (Nov 2025) · IPCC AR6 WG3 · PCAF 2022 ·
SBTi · PACTA.
