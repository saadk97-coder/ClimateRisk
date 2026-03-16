# CLAUDE.md — BSR Climate Risk Intelligence Platform

## Project Overview
Streamlit multi-page app for physical climate risk quantification.
- **Run:** `streamlit run app.py`
- **GitHub:** https://github.com/saadk97-coder/ClimateRisk
- **Working dir:** `/home/user/ClimateRisk`

## Git Workflow
```bash
# Commits fail with GPG signing by default — always disable locally first:
git config --local commit.gpgsign false

# Branch naming required by stop hook:
git checkout -b claude/<description>-session_<SESSION_ID>
git push -u origin claude/<description>-session_<SESSION_ID>

# Push requires GitHub PAT (ask user each session — do NOT store here):
git remote set-url origin https://<PAT>@github.com/saadk97-coder/ClimateRisk.git
git push -u origin <branch>
git remote set-url origin https://github.com/saadk97-coder/ClimateRisk.git  # remove token after push
```

## Architecture
```
app.py                        # Home page + sidebar (session state defaults)
pages/
  00_Methodology.py           # How it works — pipeline overview, data flow diagram
  01_Portfolio.py             # Asset entry (CSV upload or manual)
  02_Scenarios.py             # Climate scenario selection
  03_Hazards.py               # Hazard data fetch + display
  04_Results.py               # Scores, EAD, EALR, stranded asset flags
  05_Map.py                   # Interactive risk map (folium + pydeck)
  06_Adaptation.py            # Adaptation ROI / cost-benefit
  07_DCF.py                   # Climate-adjusted DCF valuation
  08_Audit.py                 # Step-by-step calculation trace
  09_Vulnerability.py         # Damage function explorer
engine/
  asset_model.py              # Asset dataclass + validation + from_dict/to_dict
  scenario_model.py           # 14 scenarios, IPCC AR6 hazard scaling, regional factors
  hazard_fetcher.py           # Priority: ISIMIP3b → NASA NEX-GDDP → CHELSA → fallback
  isimip_fetcher.py           # ISIMIP3b API, GEV fitting, regional flood params
  impact_functions.py         # Vulnerability curves (HAZUS, JRC, Syphard, IEA/ILO)
  ead_calculator.py           # Trapezoidal EAD, EP curve, full [0,1] AEP extension
  damage_engine.py            # Orchestrates per-asset/hazard/scenario EAD
  uncertainty.py              # Monte Carlo (1000 draws): intensity→curve→value channels
  portfolio_aggregator.py     # Portfolio variance with correlation matrix
  annual_risk.py              # 2025–2050 EAD timeline with PV discounting
  risk_scorer.py              # Climate Exposure Score 1–10, EALR % (Expected Annual Loss Ratio)
  adaptation_engine.py        # NPV cost-benefit for 19+ measures, IRR solver
  dcf_engine.py               # Climate-adjusted DCF, terminal value, impairment %
  export_engine.py            # Multi-sheet XLSX export
  fire_weather.py             # Canadian FWI pipeline (Van Wagner 1987)
  tropical_cyclone.py         # Holland wind profile, boundary layer reduction
  coastal.py                  # Coastal proximity (10 km zone), SLR hazard
  water_stress.py             # WRI Aqueduct 4.0 API
  data_sources.py             # Hazard data fetch priority logic
  fmt.py                      # Currency formatting helpers
  insights.py                 # Narrative scenario insights
data/
  asset_types.json            # 21 asset types: HAZUS class, default material, hazard list
  vulnerability_curves/       # flood/wind/wildfire/heat/coastal_flood JSON curves
  adaptation_catalog.json     # 19+ measures: capex, opex, effectiveness, design_life
  ngfs_hazard_baseline.json   # Regional fallback intensities by scenario + RP
```

## Key Technical Concepts

### EAD Calculation
- Trapezoidal integration over the Loss EP curve (damage × asset_value vs AEP)
- EP curve extended to full [0,1] AEP range (rarest event tail + RP=1 zero anchor)
- Standard RPs: 2, 5, 10, 25, 50, 100, 250, 500, 1000 years

### Monte Carlo Uncertainty (uncertainty.py)
Three separate channels per draw:
1. Intensity perturbed log-normally (CV=20%) → re-evaluated through vulnerability curve
2. Vulnerability curve additive noise (uniform ±15%)
3. Asset value perturbed normally (CV=10%)

### Portfolio Aggregation (portfolio_aggregator.py)
- `portfolio_ead = sum(eads)` — means add linearly
- `sigma_i = ead_i × CV_LOSS (2.0)` — derive volatility from EAD
- Correlation matrix: `SAME_REGION_CORR=0.60`, `DIFF_REGION_CORR=0.15`
- Region grouping uses `get_region_zone(asset.region)` — NOT asset_id parsing
- `var_portfolio = sigmas @ corr_matrix @ sigmas`
- Diversification benefit = undiversified sigma − portfolio sigma

### Climate Signal (damage_engine.py + annual_risk.py)
- If ISIMIP data used → `mult = 1.0` (SSP signal already in data, no double-count)
- If fallback data → `mult = get_scenario_multipliers(scenario_id, year, hazard, region_zone)`
- Region zone conversion: `get_region_zone(asset.region)` converts ISO3 → zone key (EUR, USA, etc.)
- Both `damage_engine.py` AND `annual_risk.py` now apply the ISIMIP source check

### First-Floor Height Adjustment (freeboard)
Applied in both `damage_engine.py` and `annual_risk.py`:
```python
if hazard in ("flood", "coastal_flood"):
    intens = np.clip(intens - asset.first_floor_height_m, 0.0, None)
```
**NOT ASL elevation** — `first_floor_height_m` is height above local ground (freeboard).
Typical values: 0.0–1.5m. Old `elevation_m` field was ASL (meaningless for depth reduction).

## Fixes Applied in Session 1 (all committed)
| File | Fix |
|------|-----|
| `portfolio_aggregator.py` | Portfolio variance: EAD≠sigma; use CV_LOSS=2.0; proper correlation matrix |
| `uncertainty.py` | Separate intensity/vulnerability MC channels; re-evaluate curve on perturbed intensity |
| `damage_engine.py` | ISIMIP double-counting; pass region to get_scenario_multipliers |
| `ead_calculator.py` | Extend EP curve to full [0,1] AEP range |
| `fire_weather.py` | Southern Hemisphere 6-month FWI phase shift (lat < -10) |
| `isimip_fetcher.py` | Regional flood conversion params instead of single global factor |
| `scenario_model.py` | Regional hazard scaling factors per ISO3 region |
| `annual_risk.py` | coastal_flood elevation adjustment (was only flood) |
| `water_stress.py` | Fix WRI Aqueduct API endpoints (was fabricated S3 URL) |
| `coastal.py` | Coastal zone 50 km → 10 km (EU Floods Directive / FEMA standard) |
| `tropical_cyclone.py` | 0.75× boundary layer wind reduction (Powell et al. 2003) |
| `asset_model.py` | `__post_init__` validation for lat, lon, replacement_value |
| `adaptation_engine.py` | IRR solver: multiple initial guesses, returns nan on failure |
| `dcf_engine.py` | Terminal value: handle negative FCF and WACC≈growth edge cases |
| `export_engine.py` | Dynamic currency symbol from metadata |
| `data_sources.py` | Remove dead LOCA2 code path, fix duplicate fetch_climatena call |
| `pages/00_Methodology.py` | Step card text overflow: `height:200px` → `min-height:200px;overflow:hidden` |

## Fixes Applied in Session 2 (code review integration)

### P0 — Correctness fixes (produce wrong numbers)
| File | Fix |
|------|-----|
| `asset_model.py` | `elevation_m` → `first_floor_height_m` (freeboard, NOT ASL elevation) |
| `damage_engine.py` | Region mapping: `_get_region_key(asset.region)` before `get_scenario_multipliers` |
| `damage_engine.py` | Added `region` field to `AssetResult` dataclass, populated from asset |
| `annual_risk.py` | Added ISIMIP source check to prevent double-counting (was missing) |
| `annual_risk.py` | Region mapping fix (same as damage_engine) |
| `annual_risk.py` | `elevation_m` → `first_floor_height_m` |
| `portfolio_aggregator.py` | Region grouping via `_get_region_key(asset.region)` instead of `asset_id.split('_')[0]` |
| `dcf_engine.py` | Proxy mode fix: `NPV = asset_value - PV(damages)` instead of terminal value from negative CFs |

### P1 — Methodology credibility
| File | Fix |
|------|-----|
| `risk_scorer.py` | "Physical Climate VaR" → "Expected Annual Loss Ratio (EALR)" in docstrings |
| `data_sources.py` | ISIMIP flood provenance: "fldfrc from CaMa-Flood" → "derived from Rx1day" |
| `data_sources.py` | Coastal zone "50 km" → "10 km" |
| `coastal.py` | Docstring "50 km" → "10 km" |

### UI / page fixes
| File | Fix |
|------|-----|
| `pages/01_Portfolio.py` | "Elevation above sea level" → "First-floor height above ground"; defaults 0.0–1.5m |
| `pages/03_Hazards.py` | All "50 km" → "10 km" (3 occurrences) |
| `pages/08_Audit.py` | `elevation_m` → `first_floor_height_m` |
| `pages/00_Methodology.py` | "Elevation adjustment" → "First-floor height adjustment" |
| `engine/insights.py` | All `a.elevation_m` → `a.first_floor_height_m` |
| `data/sample_portfolio.csv` | Header + values updated for first_floor_height_m |

## Fixes Applied in Session 3 (second code review response)

### P0 — Correctness (changes numbers)
| File | Fix |
|------|-----|
| `pages/04_Results.py` | Hazard data fetched per scenario (SSP-keyed), not just first scenario |
| `engine/annual_risk.py` | `hazard_data_by_scenario` parameter: use correct SSP baseline per scenario |
| `engine/damage_engine.py` | `hazard_overrides_by_scenario` parameter: per-scenario overrides in run_portfolio |
| `engine/annual_risk.py` | `adjusted_intensity_rp100` now includes first-floor height reduction |
| `pages/08_Audit.py` | Audit uses engine's exact logic: ISIMIP skip, regional multipliers, flood+coastal_flood freeboard |
| `engine/impact_functions.py` | `water_stress` handler: passes through pre-computed damage fractions (was returning 0.0) |
| `engine/damage_engine.py` | `water_stress` added to `SUPPORTED_HAZARDS` |

### P1 — Architecture / methodology
| File | Fix |
|------|-----|
| `engine/asset_model.py` | Added `terrain_elevation_asl_m` field (separate from `first_floor_height_m`) |
| `engine/asset_model.py` | Old CSV `elevation_m` → `terrain_elevation_asl_m`, NOT freeboard |
| `engine/asset_model.py` | Negative `first_floor_height_m` clamped to 0.0 in `__post_init__` |
| `engine/insights.py` | Uses `terrain_elevation_asl_m` for "below sea level" / "low elevation" checks |
| `engine/*.py` | `_get_region_key()` → `get_region_zone()` (use public API everywhere) |

### UI labels
| File | Fix |
|------|-----|
| `pages/04_Results.py` | "Physical Climate VaR" → "EALR" / "Expected Annual Loss Ratio" throughout |
| `pages/05_Map.py` | "Physical Climate VaR" / "Physical VaR" → "EALR" |
| `pages/00_Methodology.py` | "Physical VaR" → "EALR" with disclaimer "not tail VaR" |

### Engineering hygiene
| File | Fix |
|------|-----|
| `.gitignore` | Added `.pytest_cache/` |
| `engine/__pycache__/` | Removed from git tracking |
| `tests/test_regression.py` | 10 regression tests covering scenario invariance, freeboard, region mapping, water stress |

### Hazard data flow (after Session 3)
```
pages/04_Results.py
  → fetch per SSP (grouped: same SSP shared across scenarios)
  → hazard_data_by_scenario = {scenario_id: {asset_id: {hazard: data}}}
  → compute_portfolio_annual_damages(hazard_data_by_scenario=...)
  → run_portfolio(hazard_overrides_by_scenario=...)
```

## Session State Keys (app.py)
- `assets` — list of `Asset` objects (may be serialized to dicts by Streamlit Cloud)
- `selected_scenarios` — list of scenario_id strings
- `selected_horizons` — list of year integers
- `discount_rate` — float (default 0.035)
- `results` — list of `AssetResult` objects
- `currency_code` — ISO currency code string (default "USD")
- `hazard_data` — `{asset_id: {hazard: data}}` — flat reference for Audit/Hazards preview
- `hazard_data_by_scenario` — REMOVED in Session 5 (baseline is now scenario-agnostic)

## Important Gotchas
1. **Streamlit Cloud serialises dataclasses to dicts** — always handle both:
   ```python
   if isinstance(asset, dict):
       asset = Asset.from_dict(asset)
   ```
2. **numpy trapezoid renamed in 2.0** — always use:
   ```python
   _trapz = getattr(np, "trapezoid", None) or getattr(np, "trapz")
   ```
3. **GPG commit signing fails** — always run before committing:
   ```python
   git config --local commit.gpgsign false
   ```
4. **Commit signing server** expects a `source` field — just disable signing instead
5. **Streamlit multipage** — each `pages/*.py` must call `st.set_page_config()` as its first command

## Data Sources
| Hazard | Primary | Fallback |
|--------|---------|---------|
| Flood/Wind/Heat/Wildfire | ISIMIP3b API (isimip-client) | `data/ngfs_hazard_baseline.json` |
| Water Stress | WRI Aqueduct 4.0 API | Built-in regional medians |
| Coastal Flood | Derived from flood + SLR | Same fallback |
| First-floor height | Manual entry (freeboard above ground) | Default 0.0m |
| Country | BigDataCloud reverse geocode | Manual entry |

## Fixes Applied in Session 4 (fourth code review response)

### P0 — Structural correctness (climate signal coherence)
| File | Fix |
|------|-----|
| `engine/damage_engine.py` | Removed ISIMIP multiplier skip; ALL sources now use IPCC AR6 multipliers (Option 1: baseline + multipliers) |
| `engine/annual_risk.py` | Same: removed `if source.startswith("isimip"): mult = 1.0` — multipliers apply uniformly |
| `pages/04_Results.py` | Changed hazard fetch period from "2041_2060" to "2021_2040" (near-term baseline, not mid-century) |
| `engine/hazard_fetcher.py` | Default `time_period` changed from "2041_2060" to "2021_2040" |
| `pages/08_Audit.py` | Audit logic updated to match: multipliers applied to all sources, additive SLR for coastal_flood |

### P0 — Zone key mapping
| File | Fix |
|------|-----|
| `engine/hazard_fetcher.py` | `get_region_zone()` now accepts zone keys directly (EUR, MEA, etc.) — not just ISO3 |
| `data/ngfs_hazard_baseline.json` | Added MEA zone data (all hazards) + MEA ISO3 mappings (SAU, ARE, QAT, etc.) |

### P0 — Water stress (chronic hazard pathway)
| File | Fix |
|------|-----|
| `engine/ead_calculator.py` | Added `CHRONIC_HAZARDS` set; water stress uses `EAD = median_frac × value` (not EP-curve integration) |
| `engine/water_stress.py` | Fixed scenario mapping: accepts both SSP labels ("SSP2-4.5") and scenario_ids ("ndcs_only") |
| `engine/water_stress.py` | `_interp_scenario()` now actually called — applies Aqueduct future projection multiplier |

### P0 — Coastal flood physics
| File | Fix |
|------|-----|
| `engine/coastal.py` | `get_coastal_flood_intensities()` now accepts `terrain_elevation_asl_m` and converts surge to depth above ground |
| `engine/scenario_model.py` | Added `COASTAL_SLR_ADDITIVE_M` table + `get_slr_additive()` — SLR is additive, not multiplicative |
| `engine/scenario_model.py` | Coastal flood multiplicative scaling reduced (now represents storminess only, not SLR) |
| `engine/damage_engine.py` | Coastal flood: additive SLR + small multiplicative storminess term |
| `engine/annual_risk.py` | Same additive SLR treatment |
| `engine/hazard_fetcher.py` | `terrain_elevation_asl_m` threaded through fetch pipeline to coastal module |

### P1 — ISIMIP ensemble median
| File | Fix |
|------|-----|
| `engine/isimip_fetcher.py` | All 4 fetch functions (heat, wind, flood, wildfire) now query ALL GCMs and return ensemble median |
| `engine/isimip_fetcher.py` | Added `_ensemble_median()` helper |

### P1 — Test suite
| File | Fix |
|------|-----|
| `tests/test_regression.py` | Rewrote with 13 tests covering: SSP differentiation, multiplier application, zone pass-through, chronic water stress, additive SLR |
| `tests/test_regression.py` | Former test_scenario_order_invariance used same scenario twice — now separate test with different SSPs |

### P1 — Documentation / terminology
| File | Fix |
|------|-----|
| `app.py` | "Physical Climate VaR" → "Expected Annual Loss Ratio (EALR %)" |
| `engine/risk_scorer.py` | Docstring "Physical Climate VaR" → "EALR" |
| `engine/scenario_model.py` | Narrative "Climate VaR and Physical VaR" → "EALR, climate exposure scores" |
| `pages/00_Methodology.py` | Baseline period clarified: "ISIMIP3b 2021–2050 projections (bias-adjusted against 1995–2014 W5E5)" |

### P1 — Hazard fetch provenance
| File | Fix |
|------|-----|
| `engine/hazard_fetcher.py` | Added `logging` throughout — all `except Exception: pass` → logged warnings |
| `engine/hazard_fetcher.py` | `fetch_all_hazards()` logs per-location provenance summary and warns on fallback usage |

### Climate signal strategy (after Session 4)
```
Option 1 (Baseline + Multipliers) — CHOSEN
  - ALL sources (ISIMIP, NEX-GDDP, fallback) treated as near-term baseline
  - IPCC AR6 hazard scaling applied uniformly for temporal evolution 2025–2050
  - Annual timeline is meaningful: multiplier grows with warming
  - Scenario comparisons are internally consistent
  - Coastal flood: additive SLR + residual multiplicative storminess
  - Water stress: chronic pathway (EAD = median_frac × value), no EP integration
```

### Coastal flood depth computation (after Session 4)
```
water_level_asl = storm_surge_above_MHWS  (regional baseline, distance-attenuated)
depth_above_ground = max(0, water_level_asl - terrain_elevation_asl_m)
depth_above_floor = max(0, depth_above_ground - first_floor_height_m)
SLR_effect = additive_slr_m  (from COASTAL_SLR_ADDITIVE_M table)
final_intensity = (depth_above_floor + SLR_effect) × storminess_multiplier
```

## Known Limitations (acknowledged, not yet addressed)
- **ISIMIP flood is a precipitation proxy** — uses Rx1day → empirical depth scaling, NOT a hydraulic model
- **ISIMIP time chunks** — hardcoded to historical 1991-2014; fewer years (~24) than ideal for GEV
- **Heat modelled as return-period EAD** — acute framing; should be chronic annual cost
- **GEV extrapolation** — fits 1000-year RP from ~30 annual samples (fragile tail)
- **Unused asset attributes** — basement, roof_type, year_built defined but not used in damage functions
- **VaR naming** — function name `climate_var_pct` retained for backward compat; UI + docstrings → EALR
- **Coastal zone accuracy** — coastline distance accuracy ~±20km vs 10km threshold; many assets borderline
- **Provenance mismatch** — ngfs_hazard_baseline.json heat uses wet-bulb °C; ISIMIP uses tasmax °C
- **Coastal datum assumption** — MHWS ≈ 0m ASL is approximate; varies by tidal regime

## Fixes Applied in Session 5 (fifth code review — architecture standardisation)

### P0 — Climate signal double-counting (baseline + multipliers standardisation)
| File | Fix |
|------|-----|
| `engine/isimip_fetcher.py` | `_BASELINE_SSP = "historical"`, `_TIME_CHUNKS` → `["1991_2000", "2001_2010", "2011_2014"]`. All 4 fetch functions ignore SSP parameter — scenario-agnostic baseline |
| `engine/hazard_fetcher.py` | Removed `scenario_ssp` from ISIMIP calls; added `asset_type` parameter for water stress threading |
| `pages/04_Results.py` | Removed per-SSP fetch grouping; fetches baseline ONCE for all scenarios; removed `hazard_data_by_scenario` |
| `pages/03_Hazards.py` | Updated ISIMIP comparison table: "2021–2050 (SSP projections)" → "Historical (1991–2014)" |
| `pages/00_Methodology.py` | "5-GCM ensemble" → "4-GCM ensemble median"; "2021–2050 projections" → "historical experiment" |

### P0 — Water stress fixes
| File | Fix |
|------|-----|
| `engine/water_stress.py` | `"data_centre"` → `"data_center"` in `_ASSET_TYPE_WATER_SENSITIVITY` (match asset_types.json) |
| `engine/water_stress.py` | Removed embedded `_interp_scenario()` multiplier from fetch — engine handles temporal evolution |
| `engine/water_stress.py` | `_get_region_key` → `get_region_zone` (public API) |
| `engine/hazard_fetcher.py` | `asset_type` threaded through `fetch_all_hazards` → `fetch_hazard_intensities` → `fetch_water_stress_profile` |
| `pages/08_Audit.py` | Chronic pathway for water_stress EAD: `median_frac × value` instead of `calc_ead()` |

### P0 — Coastal SLR regional factor double-counting
| File | Fix |
|------|-----|
| `engine/scenario_model.py` | `get_slr_additive()` returns raw global SLR — no regional factor (handled by `get_scenario_multipliers`) |

### P0 — Negative terrain ignored
| File | Fix |
|------|-----|
| `engine/coastal.py` | `if terrain_elevation_asl_m > 0:` → unconditional `surge = np.clip(surge - terrain_elevation_asl_m, 0.0, None)` |
| `pages/03_Hazards.py` | Added `terrain_elevation_asl_m` to `fetch_all_hazards` call |

### P0 — CHELSA/NASA mapping errors
| File | Fix |
|------|-----|
| `engine/data_sources.py` | `_CHELSA_SSP_MAP`: `"SSP2-4.5": "ssp370"` → `"ssp245"`; added `"SSP3-7.0": "ssp370"` |
| `engine/data_sources.py` | `fetch_best_available`: wind support (`"heat"` → `("heat", "wind")`); CHELSA uses `tasmax` |

### P1 — Documentation / UI consistency
| File | Fix |
|------|-----|
| `pages/05_Map.py` | BWS label: "Water Stress (BWS):" → "Water Stress (raw BWS indicator):"; `_get_region_key` → `get_region_zone` |
| `engine/coastal.py` | `_get_region_key` → `get_region_zone` |

### Test coverage (20 tests)
| File | Fix |
|------|-----|
| `tests/test_regression.py` | Added 7 new tests (14–20): SLR no regional factor, ISIMIP historical baseline, data_center spelling, negative terrain, CHELSA mapping, water stress sensitivity, wind in fetch_best_available |

### Hazard data flow (after Session 5)
```
pages/04_Results.py
  → fetch baseline ONCE (scenario-agnostic)
  → hazard_data = {asset_id: {hazard: data}}  (flat, no per-scenario keys)
  → compute_portfolio_annual_damages(hazard_data=...)
  → run_portfolio(hazard_overrides=hazard_data)
  → engine applies IPCC AR6 multipliers for scenario/year differentiation
```
