# ClimateRisk

Screening-level physical climate risk platform for analyst-operated asset and portfolio review.

## Scope

This project estimates physical climate damage using a historical baseline plus scenario-multiplier architecture. It is designed for screening, triage, and analyst challenge. It is not a substitute for hydraulic modelling, site engineering, underwriting catastrophe models, or disclosure-grade assurance without further specialist review.

## Core Workflow

1. Define a portfolio on the Portfolio page.
2. Select scenarios and financial parameters on the Scenarios page.
3. Fetch baseline hazards on the Hazards page.
4. Run annual damages on the Results page.
5. Review calculation trace on the Audit page.
6. Export results, provenance, and override records to XLSX.

## Architecture

- `engine/hazard_fetcher.py`: baseline hazard acquisition and fallback handling
- `engine/annual_risk.py`: annual damage and present-value math
- `engine/damage_engine.py`: coarse scenario/year portfolio runs
- `engine/export_engine.py`: XLSX exports
- `engine/governance.py`: runtime metadata, override records, and run-manifest helpers
- `pages/`: Streamlit control plane and analyst UI
- `tests/`: regression coverage for math, copy discipline, and control integrity

## Provenance and Controls

- Results runs now build a single run manifest containing run timestamp, methodology version, scenarios, years, currency, discount rate, fetch profile, provider failures, fallback usage, and per asset-hazard source lineage.
- Audit and XLSX exports consume the same manifest instead of assembling page-local metadata.
- Manual hazard overrides are authoritative and exported with basis, preparer, timestamp, and replaced source.
- Zone overrides remain preview-only on the Hazards page and do not change Results runs.

## Setup

```bash
py -3 -m pip install -r requirements.txt
py -3 -m streamlit run app.py
```

## Tests

```bash
py -3 -m pytest -q
```

## Limitations

See [MODEL_LIMITATIONS.md](MODEL_LIMITATIONS.md) for explicit model, aggregation, uncertainty, adaptation, and provider-usage limitations.
