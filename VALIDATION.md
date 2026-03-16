# Validation Guide

## Recommended checks
1. Install runtime and dev dependencies.
2. Run `py -3 -m pytest -q`.
3. Run `py -3 -m compileall .`.
4. Smoke-test the sample workflow:
   Portfolio -> Scenarios -> Hazards -> Results -> Audit -> Vulnerability -> DCF -> Governance
5. Export the Results and Audit workbooks and confirm:
   - run metadata is present
   - source lineage reflects the actual data sources used
   - method notes distinguish acute and chronic pathways
   - manual override provenance is present when overrides are active

## Minimum assurance review
- Confirm no page claims insurance-grade outputs.
- Confirm vulnerability control points match the alias-resolved engine curves.
- Confirm DCF scenario weights must total 100%.
- Confirm CSV import blocks invalid schema, duplicate IDs, and bad ISO3 codes.

## Environment note
If `pytest` is not installed in the current environment, the platform can still be syntax-checked with `py -3 -m compileall .`, but that is not a substitute for the regression suite.
