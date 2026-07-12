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
| Reputation | **L4** | Sautner CCExposure (z-scored) × per-SD elasticities | Cash flow **or** WACC |

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
- **Scope-3 mode** (P0): `full` counts scope3_indirect in L1 *and* propagates upstream in L3
  (reproduces the methodology's worked examples). `auto` sets the L1 Scope-3 term to 0 whenever
  L3 is enabled, so upstream cost is counted once.

**Data:** `carbon_prices_ngfs.json` — real **NGFS Phase V** (released Nov 2024) REMIND-MAgPIE 3.3-4.8
prices pulled live from the IIASA `ngfs_phase_5` explorer, rebased ×1.18 (US GDP deflator 2010→2020)
to ~USD2020. Six scenarios carry real data; `divergent_net_zero` + three IEA scenarios retain
Appendix-D placeholders. *(Round-1 P4: the Kotz et al. 2024 retraction affects only NGFS
physical-damage variables, not the transition/price pathways — L1 uses standard REMIND-MAgPIE
transition price variables and is unaffected.)*
**Pass-through:** `sector_pass_through.json`, sector medians (Sijm 2012; Fabra & Reguant 2014; Cludius 2020).

---

## 4. Layer 2 — Technology (learning curves & stranding)

**Module:** `learning_curves.py`.

### 4.1 Wright's Law
```
Cost(Q) = Cost₀ × (Q/Q₀)^b ,   b = log₂(1 − LR)
Q/Q₀ = (1 + g)^(y − 2025) ,     g = max(0, scenario deployment growth)
```
Negative growth (demand decline) is clamped to 0 — cumulative capacity is monotonic; demand decline
is handled by the sector pathway, not the cost curve.

### 4.2 Lafond distributional band
```
σ_t = lafond_σ × √(y − 2025)
cost_lo = pred × e^(−σ_t) ,  cost_hi = pred × e^(+σ_t)
```

### 4.3 Stranding trigger (either fires)
- **Cost crossover** — first year challenger cost ≤ incumbent cost.
- **Demand collapse** (fossil-dependent sectors only) — first year the sector pathway falls below 0.5.

### 4.4 Impairment
```
frac(y)  = 1 / (1 + e^(−0.20·(y − crossover)))            logistic, slope 0.20
base     = replacement_value            if fossil-dependent
         = replacement_value × 0.5      otherwise         (only incumbent-tied value can strand)
cap      = max(0, 1 − pathway(2050)) × base               scenario-scaled ceiling
annual_impairment(y) = (frac(y) − frac(y−1)) × cap
```
Impairment is a **balance-sheet** figure, reported separately from cash flow.

### 4.5 Revenue erosion
```
revenue_index(y) = sector pathway(y)            (production index, 2025 = 1.0)
revenue_erosion(y) = max(0, revenue × (1 − index(y)))     ← cash-flow cost
```

**Data (P0 refresh):** power-sector base costs are **LCOE (USD/MWh)** from **IRENA Renewable Power
Generation Costs in 2024** and **Lazard LCOE+ 2025 v18** (coal 118, gas 76, solar 43, onshore wind 34,
storage 170). Learning rates: Way et al. 2022 / IRENA. Industrial base costs remain sector estimates.

---

## 5. Layer 3 — Market (production-network propagation)

**Modules:** `network_propagation.py` (world), `network_mrio.py` (MRIO + cascade).

### 5.1 Sectoral shock
Each sector's carbon shock as a fraction of its output:
```
sᵢ = emission_intensityᵢ × price × pass_throughᵢ × 1e−6
```
(emission_intensity in tCO₂ per M$ revenue; 1e−6 → per-USD.) Using sector-typical exposure avoids
double-counting the focal asset's own pass-through.

### 5.2 Leontief propagation
```
L = (I − A)⁻¹
total_shock_j = Σᵢ L[i,j] · sᵢ
propagated_j  = total_shock_j − own       (own = L[j,j]·s_j, already in L1)
indirect_cost = propagated_j × asset_revenue
```
**CES damping:** off-diagonal A scaled by 1/σ before inversion (σ = substitution elasticity;
Papageorgiou 2017 range 1.3–3.0). σ=1 is Cobb-Douglas.

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
equity_premium_bps = 50·z_total                       (Pricing paper: premium per 1 SD of overall exposure)
revenue_growth_bps = 35·z_opp − 25·z_reg
```
The **pooled distribution** is Sautner et al. (JoF 2023) **Table 1** (firm-year, ×10³): opp 0.391/1.344,
reg 0.049/0.264, phy 0.013/0.103, total 0.943/2.443. **Sector exposures** are anchored to Sautner
**Table 4** by SIC industry where available (utilities → power, petroleum refining, transport
equipment → autos, primary metal → steel …), estimated from adjacent industries otherwise.

Effect: average-exposure sectors carry ≈0 premium (the inflation is gone); coal keeps ~29 bps credit
/ −39 bps revenue drag; renewables +85 bps revenue uplift.

**Routing (non-duplication):** `ROUTE_CASHFLOWS` (default) applies the revenue-growth modifier to cash
flows (credit/equity are diagnostic); `ROUTE_WACC` adds credit+equity to the discount rate and zeroes
the revenue modifier. **Firm override (P2):** a licensed firm-level CCExposure feed replaces the
sector median via `firm_override`.

---

## 7. Orchestration & non-duplication

`run_asset_transition(asset, scenario, …)` composes the layers. Each channel routes once:

```
total_cf(y) = L1 net_carbon_opex
            + L2 revenue_erosion
            + L3 indirect_input_cost
            + L4 revenue_modifier (as a cost: −modifier)
impairment(y) = L2 annual_impairment            (balance-sheet, NOT in total_cf)
wacc_premium_bps = L4 credit+equity              (only if ROUTE_WACC)
```
`run_portfolio_transition` runs all assets × scenarios and returns
`{scenario: [TransitionAssetResult]}`.

**Present value & discount basis (Round-1 P2).** Carbon prices are **real** (USD2020), so PV
discounts the real cash flows at a **real** rate = nominal WACC − long-run inflation
(`PV = Σ cost / (1 + real)^(y − 2025)`). Discounting real flows at the nominal WACC would
systematically understate PV. Both are app inputs (nominal WACC default 9%, inflation 2.5% → real 6.5%).

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

### 8.2 Tornado (`sensitivity.py`)
One-at-a-time swing of each driver (carbon price ±30%, pass-through ±20%, σ 1.0–2.5, Scope-3 mode,
discount ±2pp) with all others at base; sorted by |swing|. Attributes the Monte-Carlo spread to
individual assumptions so you know which input to firm up.

---

## 9. Decision & alignment layer

### 9.1 Financed emissions — PCAF (`alignment.py`)
Attributed emissions = Σ `attribution_pct` × (Scope 1/2/3). 100% = corporate own-asset view; a
lender/investor enters their stake.

### 9.2 Implied Temperature Rise
Each entity's abated Scope 1+2 pathway vs a 1.5 °C linear-to-net-zero budget:
```
budget = 0.5 × E₀ × (2050 − 2025)                     area under a straight line to zero
ratio  = cumulative_actual / budget − 1
ITR    = clamp[1.2, 4.0]( 1.5 + 1.2 × ratio )
portfolio ITR = Scope1+2 × attribution weighted mean
```
Net-zero-by-2050 ≈ 1.5 °C; flat emissions ≈ 2.8 °C.

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

---

## 10. Data provenance & vintages

| Component | Source | Vintage |
|---|---|---|
| Carbon prices (L1) | NGFS Phase V REMIND-MAgPIE 3.3-4.8 (IIASA) | Nov 2023, ×1.18 → USD2020 |
| Pass-through (L1) | Sijm 2012; Fabra & Reguant 2014; Cludius 2020 | sector medians |
| Learning rates (L2) | Way et al. 2022; IRENA | 2022–23 |
| LCOE base costs (L2) | IRENA RPGC 2024; Lazard LCOE+ 2025 v18 | 2024–25 |
| I-O matrix (L3) | EXIOBASE-3 (Stadler et al. 2018), IOT 2019 | 2019 |
| CCExposure + z-base (L4) | Sautner et al. JoF 2023 Tables 1 & 4 | 2002–2019, 10k firms |
| Sector pathways | NGFS / IEA WEO 2023 | 2023 |
| MACC | IPCC AR6 WG3; IEA roadmaps | 2022–23 |

---

## 11. Calibration — worked examples (default settings, Scope-3 full)

- **Coal plant** ($500M, 2.5 MtCO₂): Net-Zero-2050 L1-2050 ≈ **$169M**; cumulative impairment
  **$266.1M** / 97.3% stranded (crossover 2025). Current Policies ≈ $7M / $33M.
- **Oil refinery** ($2B, 12.8 MtCO₂): stranding triggered by **demand collapse** (crossover 2039),
  not cost crossover.
- **Office** ($50M, 1k tCO₂): no stranding; small net cost / reputational uplift.

These are unchanged by the P0–P3 upgrades (abatement/priced default to legacy; world L3 default;
LCOE preserves the 2025 crossover).

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

---

## Appendix A — Sector taxonomy (20 sectors)
Key · label · incumbent → challenger · fossil-dependent · emission intensity (tCO₂/M$).
See `data/transition/sector_taxonomy.json`. 20 sectors span power (coal/gas/renewable), oil & gas
(upstream/refining/distribution), heavy industry (steel/cement/chemicals/aluminium), transport
(road ICE/EV, aviation, shipping), real estate (commercial/residential), agriculture, data centres,
general manufacturing, and services.

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
total 0.943/2.443. Per-SD elasticities (bps): equity 50·z_total; credit 12·z_reg + 6·z_phy;
revenue 35·z_opp − 25·z_reg.

## Appendix F — MACC measures
See `data/transition/macc.json`. Per-sector measures with marginal cost (USD/tCO₂) and abatement
potential (share of Scope 1+2); AR6 WG3 / IEA-informed.

## Appendix G — References
NGFS Phase V (IIASA) · Sijm 2012 · Fabra & Reguant 2014 · Cludius 2020 · Way et al. Joule 2022 ·
Lafond et al. TFSC 2018 · IRENA RPGC 2024 · Lazard LCOE+ 2025 · Stadler et al. (EXIOBASE) 2018 ·
Acemoglu et al. 2012 · Papageorgiou et al. 2017 · Reisch et al. 2025 (arXiv:2503.10644) ·
Sautner, van Lent, Vilkov, Zhang (JoF 2023; Mgmt Sci 2023) · IPCC AR6 WG3 · PCAF 2022 · SBTi · PACTA.
