# Model Governance

## Purpose
This platform is a screening-level physical climate risk quantification tool for portfolio triage, prioritisation, and analyst challenge. It is not a substitute for hydraulic modelling, catastrophe underwriting, or site-specific engineering assessment.

## Version
- Methodology version: `2026.03-assurance`

## Active baseline pathways
- `ISIMIP3b` historical extraction for acute hazards where available
- `WRI Aqueduct 4.0` for chronic water stress
- `coastal_slr_baseline` for coastal flood where applicable
- `ibtracs_cyclone` as a wind amplification modifier in tropical cyclone basins
- `fallback_baseline` for built-in regional fallback

## Registry-only sources
- `nasa_nex_gddp_cmip6`
- `chelsa_cmip6`
- `loca2`
- `climatena_adaptwest`

These remain documented in the registry for transparency but are not used automatically in the current historical-baseline path.

## Key control statements
- Flood intensities are screening-level proxies, not local hydraulic depth simulations.
- Water stress uses a chronic loss pathway based on the RP50 damage fraction times replacement value.
- Manual hazard overrides require basis, evidence note, preparer, and UTC timestamp.
- Results and audit exports include run metadata, method notes, source lineage, and manual-override provenance when overrides are active.
- Vulnerability reference surfaces expose alias-resolved control points matching the engine path.

## Known limitations
- Event curves are based on discrete return periods and open-source vulnerability functions.
- Zone overrides are preview controls on the Hazards page and do not change country mapping in the Results engine.
- DCF replacement-value mode is a screening proxy, not a valuation-grade model.
