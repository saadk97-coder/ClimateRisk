# Model Limitations

## Positioning

This platform is a screening-level physical climate risk tool for analyst review, prioritisation, challenge, and early-stage adaptation screening. It does not provide insurer catastrophe modelling, engineering design support, or disclosure-ready assurance on its own.

## Hazard Modelling

- Flood remains a screening proxy derived from gridded climate and hydrological inputs. It is not a local hydraulic inundation-depth model.
- Coastal flood remains screening-level. Effective coastal depth is approximated as `max(0, base_surge * storm_mult + slr_additive - terrain_elevation - freeboard)`.
- Coastal classification is sensitive near the coast threshold and can misclassify near-threshold sites because the coastline screen is simplified.
- Heat outputs use temperature-based screening proxies. They should not be described as wet-bulb, labour physiology, plant-process, or full chronic health models unless those methods are explicitly added.
- Wildfire is strongest in the full ISIMIP pathway. In balanced mode, wildfire can still fall back to the screening baseline.

## Tail Risk And Uncertainty

- Standard analyst views stop at RP500. RP1000 remains an advanced high-uncertainty screening tail, not a default decision surface.
- When generated, GEV bands in Results, Audit, and exports are conditional parameter-uncertainty bands from bootstrap refits around the fitted return-level curve.
- Those bands do not include total uncertainty. They exclude model-form, climate-model, exposure, vulnerability, and decision uncertainty.
- Scenario comparison shows scenario range across selected pathways. It should not be described as a statistical uncertainty interval.
- Long return-period tails remain fragile because they extrapolate from relatively short annual-maxima samples.

## Scenario Architecture

- Results use a shared historical baseline across scenarios and apply scenario multipliers through time.
- Scenario outputs should not be described as probability-weighted unless explicit weighting logic is implemented and surfaced.

## Portfolio Aggregation

- Portfolio diversification diagnostics now use hazard-specific distance-decay correlations. They remain screening approximations, not institution-grade dependence modelling.
- Displayed portfolio EAD remains additive expected loss. Diversification diagnostics do not convert the platform into a stochastic portfolio tail model.
- Cross-hazard dependence is simplified. The current implementation aggregates hazard variances separately and then combines them with a screening independence assumption across hazards.

## Adaptation

- Standalone measure economics compare each measure with the original hazard baseline.
- Bundled results sequence selected measures on residual hazard loss so overlapping savings are not simply summed.
- Bundle order still matters. Cross-hazard interactions and mechanism overlap remain approximate, so bundled outputs are still screening-level decision support rather than engineered programme design.

## Provenance And Providers

- Exact asset coordinates may be sent to external providers during geocoding, hazard refresh, and optional map overlays.
- When a provider fails, the platform can fall back to the built-in regional baseline. Those runs remain useful for screening but should be treated as degraded-mode outputs.
- Map overlays are not automatically run-faithful evidence surfaces unless they explicitly consume the stored run manifest.

## Operational Use

- Exports are only as faithful as the active run in session. A fresh Results run should be executed before using exported workbooks as review evidence.
- Manual overrides require analyst judgment and evidence quality control. They improve authority only when the supporting evidence is sound.
