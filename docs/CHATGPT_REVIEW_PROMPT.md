# Review Prompt — BSR Transition Risk Engine

*Paste the block below into ChatGPT (or Claude/other). Attach the two methodology
documents (`TRANSITION_METHODOLOGY.md` and `TRANSITION_METHODOLOGY_PLAIN.md`) and, for the
code-review sections, the engine files listed at the end. If the reviewer can't take
attachments, the summary in the prompt is enough for a conceptual critique.*

---

## The prompt

You are a **senior climate-finance methodologist and quantitative code reviewer**. You have
built or audited transition-risk models at a rating agency, an asset manager, and a
climate-analytics vendor (think MSCI Climate VaR, S&P/Trucost, Ortec Finance,
riskthinking.AI). You are rigorous, sceptical, and specific. I want a **critical review** of a
screening-grade transition-risk engine — not encouragement. Assume I can take hard feedback
and want the sharpest version of it.

### What the engine is
A standalone (physical-risk-separate) transition-risk tool that estimates, per asset/entity,
per NGFS scenario, per year 2025–2050:
- annual transition **cash-flow cost**, and
- stranded-asset **impairment**,

decomposed into the four TCFD transition categories, each computed by one "layer" and routed
to exactly one financial destination (non-duplication):

1. **Layer 1 — Policy & Legal (carbon cost).** `cost = (Scope1+2) × NGFS_price × exposure`.
   Pass-through splits the bill (absorbed vs passed downstream); free allocation can create a
   windfall (net negative). Scope 3 handled via a configurable incidence. → operating cost.
2. **Layer 2 — Technology (stranding).** Wright's-Law learning curves project a challenger-vs-
   incumbent **cost crossover**; a logistic S-curve then impairs asset value (per-sector
   slope). Secondary trigger: demand-pathway collapse. Lafond log-normal bands give a
   crossover-year range. Optional: carbon-inclusive crossover (adds carbon to the incumbent).
   → revenue erosion + a separate impairment stream.
3. **Layer 3 — Market (supply chain).** A sector carbon shock is propagated through a Leontief
   inverse `(I−A)⁻¹` (20-sector world matrix, or a 20×49 EXIOBASE MRIO). The focal firm's own
   direct round is subtracted (counted once in L1). Optional partial pass-through and an
   experimental endogenous-default "cascade" (excluded from disclosure). → input cost.
4. **Layer 4 — Reputation (cost of capital).** Sautner et al. (2023) CCExposure, z-standardized
   against the published firm-year distribution, priced per standard deviation. Default routes
   the **equity premium to WACC** (the sourced elasticity); a revenue route exists but is
   labeled unsourced/manual. → WACC (or revenue, never both).

**Decision layer:** Monte-Carlo (price/pass-through/elasticity), one-at-a-time tornado (cost
and impairment targets), PCAF financed emissions, Implied Temperature Rise, PACTA-style
alignment, MACC + budget optimizer, and a Decarbonization Lever Library (sector→lever map by
value-chain position, plan-overlay gap analysis — reference, not score). A DCF hook composes
physical EAD + transition cost.

**Data:** NGFS Phase V carbon prices; EXIOBASE-3 I-O; Sautner 2023 CCExposure; IRENA 2024 /
Lazard 2025 LCOE; IPCC AR6 / IEA / Mission Possible Partnership for abatement.

### What I want you to do
Review the approach across the dimensions below. For **each finding**, give me: (a) the
specific issue, (b) why it's wrong or risky, (c) a concrete inputs→wrong-output example where
you can, and (d) a recommended fix with its trade-off. Rank findings **most-material first**.
Don't pad — if something is fine, say so briefly and move on.

**1. Methodological accuracy & theory**
- Is each layer's math a defensible screening approximation, or are there errors of
  formulation (not just precision)? Flag anywhere the functional form doesn't match the cited
  source.
- Wright's Law: is projecting cost from *cumulative capacity growth* (clamped ≥0) sound, and is
  comparing challenger vs incumbent in possibly-different functional units a real problem?
- Leontief propagation: is subtracting only the direct round (`s_j`, not `L[j,j]·s_j`) the
  right non-duplication choice? Does treating `asset_revenue` as the firm's share of sector
  output hold up?
- Layer 4: is z-standardizing sector-median CCExposure and pricing per-SD legitimate, or does
  using sector medians understate/overstate the cross-sectional signal? Are the per-SD
  elasticities (equity 50·z_total; credit 12·z_reg+6·z_phy; revenue 35·z_opp−25·z_reg) each
  defensible, and is routing equity→WACC by default correct?
- Implied Temperature Rise: is a linear 1.5 °C budget with β=1.2 and a [1.2, 4.0] clamp a
  reasonable screening ITR, or misleading?

**2. Double-counting & non-duplication (be aggressive here)**
- Trace a single dollar of carbon cost through L1→L3→L4 and confirm it's charged exactly once.
- Is stranding impairment (balance sheet) ever leaking into the cash-flow cost total?
- Does the Scope-3 term in L1 overlap the upstream cost in L3? Is the `scope3_mode` auto/full
  switch a real fix or a band-aid?
- Reputation routed to WACC vs the revenue modifier — any path where both bite?

**3. Calibration & data integrity**
- Are the anchor results plausible? Coal plant ($500M, 2.5 MtCO₂): NZ2050 ≈ $266M cumulative
  impairment / 97% stranded. Oil refinery ($2B): ≈ $1.36B impairment via demand-collapse
  trigger. Office building: ≈ 0. Sanity-check the magnitudes and the scenario spread.
- NGFS prices rebased ×1.18 to USD2020 — right approach? Sector emission intensities in
  tCO₂/M$ revenue — order-of-magnitude correct?
- Where are sector-median proxies (pass-through, CCExposure, learning rates) most likely to
  mislead at the firm level, and which one would you firm up first?

**4. Code review** *(if files attached)*
- Correctness bugs, edge cases (zero revenue, missing sector, negative values, NaN handling),
  numerical stability (matrix inversion, logistic overflow, interpolation at horizon ends).
- Off-by-one / year-boundary errors in the incremental-impairment and PV loops.
- Are the "opt-in, default-to-legacy" parameters actually neutral at their defaults (i.e. do
  they preserve the anchors), or do any silently change results?
- Anything that would fail silently rather than loudly.

**5. Competitive coherence & positioning**
- How does this compare to MSCI Climate VaR, S&P/Trucost, Ortec Finance ClimateMAPS, PACTA,
  Transition Pathway Initiative, and NGFS-based bank stress tests? What does it do that they
  don't, and where is it clearly weaker?
- Is "screening-grade, transparent, four-channel, no-double-count, honestly-labeled" a
  defensible market position, or is it neither rigorous enough for regulators nor slick enough
  for corporates? Who is the buyer and what would make them choose this?
- What are the 2–3 highest-leverage additions that would move it from "credible screening tool"
  toward "market-leading"? What is genuinely bespoke vs table-stakes?

**6. Honesty & disclosure risk**
- Anywhere the tool over-claims (precision, "VaR", "insurance-grade") or under-discloses a
  limitation that a sophisticated user would catch?
- Is labeling the Monte-Carlo P5–P95 a "conditional floor" honest and sufficient, or still
  liable to be read as full uncertainty?

**7. Anything I didn't ask**
- The failure modes, structural blind spots, or reviewer red-flags I haven't listed. What would
  make you *not* trust this number if you were the risk committee?

### Output format
1. **Verdict** — 3–5 sentences: is the approach sound for its stated screening purpose?
2. **Top 5 material findings** — ranked, each with issue / why / example / fix.
3. **Dimension-by-dimension notes** — the seven areas above, terse.
4. **Positioning take** — the honest competitive read and the 2–3 highest-leverage moves.
5. **What to fix first** — a prioritized shortlist.

Be specific, cite the layer/quantity, and prefer a concrete counter-example over a general
concern. Where you're uncertain, say so and tell me what evidence would resolve it.

---

## Files to attach for the code-review sections
```
docs/TRANSITION_METHODOLOGY.md            # full technical methodology (math + provenance)
docs/TRANSITION_METHODOLOGY_PLAIN.md      # plain-language scope summary
engine/transition/carbon_pricing.py       # Layer 1
engine/transition/learning_curves.py      # Layer 2
engine/transition/network_propagation.py  # Layer 3 (world)
engine/transition/network_mrio.py         # Layer 3 (MRIO + cascade)
engine/transition/cc_exposure.py          # Layer 4
engine/transition/transition_engine.py    # orchestrator + non-duplication
engine/transition/uncertainty.py          # Monte-Carlo
engine/transition/sensitivity.py          # tornado
engine/transition/alignment.py            # PCAF / ITR / PACTA
engine/transition/transition_dcf.py       # DCF composition
data/transition/*.json                    # all calibration data (prices, curves, IO, CCE, levers)
tests/test_transition.py                  # 163 tests — the behavioural spec
```

*Tip: if the reviewer can only take a few files, send the two methodology docs +
`transition_engine.py` (to check non-duplication) + `learning_curves.py` and
`cc_exposure.py` (the two layers with the most modelling judgement).*
