# Assurance-Led Platform Review

## Executive Verdict

### Overall assessment
The platform is **credible as a screening-level climate-risk workflow**, but it is **not yet strong enough to withstand sophisticated risk assurance without challenge**. The strongest parts of the product are its breadth of workflow coverage, the amount of methodological transparency it attempts to expose, the targeted regression suite, and the fact that several pages already try to distinguish screening outputs from insurance-grade or regulatory-grade outputs.

The main weakness is not that the underlying engine is unserious. It is that the **trust layer around the engine is inconsistent**. A sophisticated reviewer will see careful caveats in some places, then encounter materially stronger claims, incomplete override governance, and evidence surfaces that do not always match the actual calculation path. That combination creates a control problem: the buyer stops asking whether the model is directionally useful and starts asking whether the platform can be relied on at all.

### Fit-for-purpose rating
- **Screening and triage:** conditionally fit, with caveats.
- **Enterprise pre-sales / pilot deployments:** viable only after near-term trust and governance remediation.
- **Sophisticated risk assurance / formal model review:** not yet fit.

### Strengths worth preserving
- Broad workflow coverage across portfolio setup, scenarios, hazards, results, map, adaptation, DCF, audit, and vulnerability.
- Real effort toward traceability and explicit methodology rather than black-box outputs.
- A regression suite that is unusually focused on methodological regressions and overclaims.
- Adaptation analysis uses the full annual damage stream rather than a single static loss point.
- Results and home surfaces already contain important screening-level disclaimers in several places.

## Findings By Severity

### P1 - Claim integrity is inconsistent enough to undermine buyer trust
The platform makes materially different statements about its level of rigor depending on where the reviewer looks. The clearest example is the methodology hero copy, which says the platform goes "to an insurance-grade financial damage estimate" even though the home page and regression tests explicitly frame the tool as screening-level, not insurance-grade. A sophisticated reviewer will treat that as a governance failure, not just a copy issue.

- Evidence:
  - `pages/00_Methodology.py:61-62` claims "insurance-grade financial damage estimate".
  - `app.py` frames the tool as suitable for portfolio screening and explicitly says it is not a substitute for site-specific engineering or catastrophe modelling.
  - `tests/test_regression.py` includes a regression check to prevent positive insurance-grade claims in `app.py`.
- Assurance impact:
  - Weakens every other disclosure because the platform appears not to control its own claim language.
  - Raises immediate diligence questions about model governance, approval of marketing copy, and internal review standards.

### P1 - Audit and evidence surfaces are not always faithful to the model actually being run
The platform promises traceability, but several evidence surfaces misstate or incompletely represent the active calculation path. This is a core assurance blocker because auditability is one of the product's main value claims.

- Evidence:
  - `pages/08_Audit.py:106-111` correctly branches water stress into the chronic pathway.
  - `pages/08_Audit.py:161-165` still hardcodes trapezoidal EP-curve integration and catastrophe-model references for Step 7, even when the selected hazard is `water_stress`.
  - `engine/export_engine.py:154-171` hardcodes a generic "Sources & Methodology" sheet including only trapezoidal EAD language, with no hazard-specific branch for chronic hazards.
- Assurance impact:
  - An exported audit can be technically incorrect while still looking formal and well-packaged.
  - That is materially worse than having no audit surface, because it creates false confidence.

### P1 - Vulnerability evidence can diverge from the curve the engine is actually using
The vulnerability page uses `get_damage_curve()` for plotted curves, which respects alias mapping, but its raw control-point and download logic uses `_get_raw_curve()` without the alias resolution used by the engine. For aliased asset types such as `commercial_office`, `commercial_retail`, `data_center`, `mixed_use`, and `hotel_resort`, the page can therefore show "built-in values used by the engine" that are not the actual curve driving loss calculations.

- Evidence:
  - `engine/impact_functions.py` resolves alias asset types through `_CURVE_ALIAS`.
  - `pages/09_Vulnerability.py:85` uses `get_damage_curve(sel_hazard, sel_atype)` for the rendered curve.
  - `pages/09_Vulnerability.py:88-106` defines `_get_raw_curve()` using direct dictionary lookup and fallback, without alias resolution.
  - `pages/09_Vulnerability.py:155-157` tells the user these are the built-in values used by the engine.
  - `pages/09_Vulnerability.py:167-178` uses the same raw path for "Download All Curves".
- Assurance impact:
  - The review surface and export can disagree with the model.
  - That directly weakens the platform's claim that every number is traceable.

### P1 - Manual override governance is too weak for serious assurance review
Analyst intervention is allowed in a way that is operationally useful but not well governed. Override justification is optional, there is no durable capture of who made the override or when, and the override note is not carried into the formal result export layer. The control exists, but the governance around it is light.

- Evidence:
  - `pages/03_Hazards.py:666` labels the override justification as optional.
  - `pages/03_Hazards.py:679-680` stores `source="manual_override"` and `source_note`, but no user, timestamp, approval state, or external reference identifier.
  - `pages/03_Hazards.py:689` states the override will be used in all subsequent damage calculations.
  - `pages/04_Results.py:111-121` merges overrides into the hazard data used for results.
  - `engine/export_engine.py:58-59` and `engine/export_engine.py:154-171` show no export structure for override provenance, operator identity, data lineage, or approval metadata.
- Assurance impact:
  - A reviewer cannot distinguish controlled expert override from ad hoc adjustment.
  - Results may be materially influenced by analyst intervention without export-grade provenance.

### P2 - Source-selection disclosures are internally inconsistent
The hazard layer presents NASA NEX-GDDP, CHELSA, and ClimateNA as active or available in multiple places, while the active fetch path disables them for the current baseline-plus-multipliers architecture. The repo documents both stories at once.

- Evidence:
  - `pages/03_Hazards.py:49-50` says sources are tried in priority order `ISIMIP3b -> NASA NEX-GDDP -> CHELSA -> Regional Baseline`.
  - `pages/03_Hazards.py:153-156` includes active-looking comparative rows for NASA, CHELSA, LOCA2, and ClimateNA.
  - `pages/03_Hazards.py:175-180` then states NASA, CHELSA, and ClimateNA are disabled in this release.
  - `engine/hazard_fetcher.py:198-202` still documents the broader cascade.
  - `engine/hazard_fetcher.py:284-291` actually disables those sources in the active baseline path.
- Assurance impact:
  - Reviewers will question which data source was truly eligible for use.
  - The inconsistency also makes independent replication harder.

### P2 - Reproducibility controls are not yet at assurance grade
The repository and exports are not version-tight enough for a professional assurance posture. Dependencies are only lower-bounded, result exports do not carry model/data version metadata, and the regression suite is not runnable out of the box because `pytest` is missing from the available Python environment.

- Evidence:
  - `requirements.txt` specifies only `>=` bounds with no lockfile or exact versions.
  - `engine/export_engine.py:58-59` writes generic workbook metadata but no code version, git commit, dependency snapshot, or data hash.
  - `pages/04_Results.py:551-563` passes only run date and provider metadata into the main export.
  - Runtime verification attempt:
    - `py -3 -c "import sys; print(sys.version)"` succeeded using Python 3.13.2.
    - `py -3 -m pytest -q` failed because `pytest` is not installed.
- Assurance impact:
  - Results are harder to reproduce exactly.
  - Buyers with model-risk or internal audit functions will treat this as a control deficiency.

### P2 - Input validation and ingestion governance are too light
The platform is permissive about data ingestion in a way that is convenient for prototyping but risky for commercial assurance. CSV uploads are converted directly into `Asset` objects with little schema-level validation beyond what the dataclass enforces, and the manual form retains default coordinates and country state that can be reused unintentionally.

- Evidence:
  - `pages/01_Portfolio.py:93-94` converts every CSV row directly through `Asset.from_dict`.
  - `pages/01_Portfolio.py:270-273` reads uploaded CSVs with no explicit schema validation, deduplication, or cross-field checks.
  - `pages/01_Portfolio.py:71` and `pages/01_Portfolio.py:75` default manual entry state to New York coordinates and `USA`.
  - `pages/01_Portfolio.py:437` only enforces asset name as a visible manual-form requirement.
- Assurance impact:
  - Garbage-in risk is higher than it needs to be.
  - A sophisticated buyer will ask where data quality gates, mandatory fields, and exception handling live.

### P2 - The DCF layer is useful commercially but still too loose for strong assurance claims
The DCF workflow is a good decision-support surface, but it is still a simplified overlay rather than a tightly governed finance model. The proxy mode uses replacement value as a stand-in for enterprise value, climate risk premium is a free-form user input, and scenario probabilities are manually assigned and normalized. Those are reasonable product shortcuts, but they need stronger framing.

- Evidence:
  - `pages/07_DCF.py:63-64` offers "Asset replacement value (proxy)" as a cash-flow basis.
  - `pages/07_DCF.py:73-75` allows a free-form climate risk premium.
  - `pages/07_DCF.py:98-118` uses manually entered scenario weights and normalizes them to 100%.
- Assurance impact:
  - The DCF module is directionally useful but not yet robust enough to present as a tightly controlled valuation engine.

### P3 - Some workflow controls are accurate but too easy for users to misunderstand
There are several places where the platform technically behaves correctly but is likely to confuse a serious user without stronger interface cues.

- Examples:
  - `pages/03_Hazards.py:186-187` says zone overrides affect only the Hazards-page preview and manual override reference values, not the Results page. That is correct, but it is subtle enough that users may assume otherwise.
  - `pages/05_Map.py:93` uses raw water-stress score (`water_stress_score`) for "Colour by Water Stress", while other map options are EAD-style metrics. The page clarifies this later, but the control label itself is easy to overread.
  - `pages/09_Vulnerability.py:22` claims custom curves can be uploaded and applied, while `pages/09_Vulnerability.py:157` states custom curve editing is not wired into the engine.

## Structured Improvements

### Wave 1 - Trust blockers and misleading claims
Objective: remove the fastest paths by which a sophisticated reviewer can disqualify the platform.

- Standardize all product and methodology language to a single approved posture:
  screening-level, portfolio triage, auditable, but not insurance-grade or site-design-grade.
- Remove or rewrite unsupported feature claims:
  custom curve upload/application, active secondary hazard sources when they are actually disabled, any evidence surface that implies broader rigor than the code provides.
- Fix hazard-specific audit language so that each hazard describes its real path:
  acute perils use EP integration; chronic perils such as `water_stress` use the chronic pathway.

Acceptance criteria:
- No public-facing page or export claims unsupported insurance-grade capability.
- Audit language changes with hazard path and matches engine behavior.
- Source-selection copy matches the active fetch architecture everywhere.

### Wave 2 - Model governance and evidence hardening
Objective: make the platform defensible under buyer diligence and internal model review.

- Introduce governed override metadata:
  mandatory citation or rationale, analyst identity, timestamp, optional reviewer approval, and clear visual flagging of overridden results.
- Carry override provenance into exports and audit outputs.
- Version the evidence package:
  git commit or release version, dependency snapshot, data-source version, run timestamp, scenario set, and major configuration assumptions.
- Make vulnerability evidence exact:
  raw control points, plotted curves, and downloads must use the same alias-resolved logic as the engine.
- Strengthen input validation:
  required columns, unit checks, duplicate-ID detection, coordinate/country sanity checks, and explicit validation errors before import.

Acceptance criteria:
- An exported workbook can show whether analyst overrides were used and why.
- Vulnerability reference data is provably the same curve used in computation for aliased asset types.
- Result exports contain model, dependency, and run lineage metadata sufficient for reproduction.
- CSV import rejects materially invalid portfolios with explicit error reporting.

### Wave 3 - Competitive differentiation and workflow refinement
Objective: move from "defensible pilot" to "credible competitive platform."

- Add explicit model-governance surfaces:
  methodology version, data inventory, assumptions register, known limitations, and model-change log.
- Improve uncertainty treatment in the UI:
  if Monte Carlo is not production-ready, stop advertising it prominently; if it is kept, wire it through to outputs and audit surfaces.
- Tighten DCF framing:
  clearly separate proxy valuation mode from full cash-flow mode, and make scenario weighting and climate premium assumptions more explicitly governed.
- Improve workflow clarity around preview-only versus results-impacting controls.
- Build a formal validation pack:
  benchmark cases, sample portfolios, regression suite setup, and a one-command verification path.

Acceptance criteria:
- A new reviewer can distinguish screening outputs, valuation overlays, and analyst intervention without reading source code.
- Validation material exists outside the app itself.
- Runtime setup and test execution are documented and repeatable.

## Competitive Readiness

### What still keeps the platform below strong alternatives today
- Inconsistent trust signals across pages.
- Weak override governance and incomplete evidence packaging.
- Reproducibility posture that is not yet tight enough for disciplined enterprise review.
- Simplified valuation and stranded-asset framing that needs stronger qualification.
- Heavy reliance on live third-party data services without a clearly controlled operating mode.

### What would make it commercially credible after Waves 1-2
- A single, disciplined screening-level claim posture across the entire product.
- Audit and export surfaces that are faithful to the active model path.
- Mandatory provenance for analyst overrides.
- Versioned, reproducible evidence packages.
- Cleaner portfolio ingestion controls and better distinction between reference views and decision-grade outputs.

### What would move it into a genuinely strong competitive position after Wave 3
- A formal model-governance pack.
- Production-grade uncertainty outputs.
- Better validation and benchmark evidence.
- More rigorous DCF and decision-support framing.
- Stronger multi-user review and approval controls around analyst intervention.

## Verification Note

This review is **repo-verified, not runtime-verified end-to-end**.

- Confirmed:
  Python 3.13.2 is available through `py -3`.
- Not confirmed:
  the regression suite could not be executed because `pytest` is not installed in the available environment.

That runtime gap is itself part of the assurance finding set. A platform that aims to survive sophisticated review should have a clearly runnable validation path in a clean environment.
