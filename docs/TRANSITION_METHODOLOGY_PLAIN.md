# Transition Risk, in Plain Terms
### What the tool measures, what's in scope, and how the numbers are made

*A non-technical companion to the full BSR Transition Risk Methodology. Written for a
reader who is new to climate transition risk. Screening-grade tool — not investment
advice or an assured regulatory disclosure.*

---

## 1. The one-paragraph version

As the world moves away from fossil fuels, companies face costs that have nothing to do
with storms or floods — they come from the *transition itself*: carbon prices, cheaper
clean competitors, more expensive supply chains, and shifting reputations. This tool takes
a company (or a portfolio of assets) and estimates, year by year from 2025 to 2050 and
under different climate-policy scenarios, how much money that transition could cost — and
how much of the company's asset value could be stranded (made worthless early). It breaks
the answer into **four clearly separated channels** so you can see *where* the risk comes
from, not just a single black-box number.

---

## 2. What you put in

For each entity or asset you provide a short profile:

| Input | Plain meaning |
|-------|---------------|
| **Sector** | What the business does (e.g. coal power, steel, real estate). Picks the right physics and cost curves. |
| **Emissions** (Scope 1, 2, 3) | How much CO₂ it emits directly (1), from its electricity (2), and across its value chain (3). Scope 3 is split into two: **upstream** (suppliers → supply-chain cost, Layer 3) and **use-phase** (what customers emit using its products → product-demand risk, Layer 2). |
| **Annual revenue** | Used to scale supply-chain and reputation effects. |
| **Transition plan** (optional) | Planned pivot capex and a "how well-placed today" positioning score — how the company adapts, not just how exposed it is (see Layer 2). |
| **Replacement value** | What the physical assets are worth — the thing that can be "stranded." |
| **Region** | Which carbon-price path and supply-chain structure applies. |
| **Decarbonization target** (optional) | A net-zero year, if the company has a plan to cut its own emissions. |
| **Attribution %** (optional) | For an investor/lender: what share of the asset is *yours*. |

Then you pick one or more **scenarios** — coherent stories about how fast the world
decarbonizes, from "Net Zero 2050" (fast, orderly) to "Current Policies" (slow). These are
the standard **NGFS** scenarios central banks use.

---

## 3. What comes out

- **A cost timeline** (2025–2050) for each scenario: the annual cash-flow hit from
  transition, split into the four channels.
- **A stranded-asset estimate**: how much replacement value is written off, and when.
- **A climate-adjusted valuation** (optional DCF): the company's value with vs without
  transition risk.
- **Uncertainty and sensitivity**: a range around the central number, and a ranking of
  *which assumption matters most*.
- **Alignment metrics**: financed emissions (PCAF), an Implied Temperature Rise, and how
  the portfolio tracks against a 1.5 °C pathway.
- **A decarbonization lever map**: which specific abatement options exist for each sector,
  and where the company's transition plan has gaps.

---

## 4. The four channels (this is the core idea)

The tool follows the four transition-risk categories defined by the **TCFD** (the global
climate-disclosure framework). Each is one "layer," each is computed separately, and — this
is important — **each is routed once by design**, with a couple of disclosed boundary
exceptions (see §5) rather than a blanket "counted exactly once" guarantee.

### Layer 1 — Policy & Legal risk (the carbon-price channel)
**Question it answers:** *What does it cost to emit, once emissions carry a price?*

Simple math:
```
carbon cost  =  emissions  ×  carbon price
```
But a firm rarely eats the whole bill. Two adjustments:
- **Pass-through** — a company with pricing power passes some cost to customers. That
  passed-on part isn't its loss (it becomes a supply-chain effect for others — see Layer 3).
- **Free allowances** — some emitters get free permits. Combined with pass-through, a firm
  can occasionally come out *ahead* (a "windfall") — the math allows this rather than
  hiding it.

The carbon price itself rises over time and differs by scenario and region; we read it from
the published **NGFS** price tables and interpolate between years.

### Layer 2 — Technology risk (the "cheaper competitor" channel)
**Question it answers:** *When does the clean alternative get cheap enough to make my asset
obsolete — and how much value do I lose when it does?*

Two ideas:
1. **Learning curves (Wright's Law).** Every time the world doubles how much solar (or
   batteries, or green hydrogen) it has built, the cost drops by a fixed percentage. So we
   can project when the *challenger* technology's cost falls below the *incumbent's*. That
   year is the **crossover** — the tipping point. **And it's location-specific:** a watt in
   Texas or the Gulf is far cheaper than in Northern Europe or Japan, so those sunny/windy
   regions reach crossover — and produce green steel, ammonia and cement — *years earlier*.
   The model applies a geographic resource/cost factor by region, with **sub-national resolution
   for the US and Europe** — where a watt and a transition plan really do look different in Texas
   vs California, or Spain vs Germany. Same steel plant, green-steel cost parity: US Southwest ~2026,
   Texas ~2027, California ~2034, US Northeast ~2039; Spain ~2031, Germany ~2040, Japan ~2042.
   (Enter a region as `USA-TX`, `USA-CA`, `ESP-S`, etc. for the finer view.)

**Adaptability (this matters a lot).** A company isn't frozen — under a transition scenario it
*migrates* toward the low-carbon business. So instead of assuming an ICE carmaker simply loses all
its revenue, the model lets it **pivot**: it captures part of the green upside (offsetting the loss),
spends **transition capex** to get there, and — if it's already partly transitioned — has less to
strand. How much it offsets depends on two things: its **ambition** (defaulted from the scenario — a
Net-Zero world pulls companies into an aggressive pivot; a Current-Policies world doesn't), and its
**present positioning** (how well-placed it is today, from its emissions, the maturity of its sector's
decarbonization options, and the strength of its transition plan — with a manual override for the
judgement calls). A well-positioned, ambitious carmaker's exposure roughly halves; a poorly-positioned
laggard keeps most of the loss *and* pays more to catch up. This is "here's how the company looks if it
follows this pathway, from where it starts today" — not "here's the damage if it does nothing." The
capex is the honest price of that pivot, so a transition plan is never free.

2. **Stranding.** Once crossover hits (or demand for the old product simply collapses), the
   asset loses value along an **S-curve** — slow at first, then fast, then leveling off —
   because plants don't shut overnight. How fast depends on the sector (power flips quickly;
   heavy industry and buildings turn over slowly).

We also carry an *uncertainty band* on the crossover year (costs are forecasts, not
certainties) and can optionally make the crossover happen sooner when the carbon price makes
the dirty option more expensive.

**Products that emit when customers use them.** For a company that *makes* carbon-emitting
products — diesel engines, construction machinery, petrol cars, fuels — the biggest risk isn't
its own factories; it's that its *customers* face carbon costs and switch to cleaner
alternatives, so demand for the dirty product line falls. If a company reports these
"use-of-sold-products" emissions, we translate a slice of that future customer carbon burden
into demand-and-margin pressure on the maker. For Caterpillar this is the single largest
effect — correctly flagging that its diesel machinery line is what's exposed, even though its
own plants are relatively clean.

### Layer 3 — Market risk (the supply-chain channel)
**Question it answers:** *Even if I'm clean, how much do my inputs cost more because my
suppliers are paying for carbon?*

We use a standard tool from economics — an **input-output table** (who buys from whom across
20 sectors) — and the **Leontief inverse**, which traces a cost increase in one sector
through *all* the ripples it causes upstream. If steel gets more expensive, carmakers feel
it; if power gets more expensive, everyone feels it. We add up the ripples that land on your
sector. (Optionally the firm passes part of this cost on again, so only its net share
counts.) A higher-resolution version splits this across 49 world regions using the
**EXIOBASE** global trade database.

**If a company reports its own supply-chain emissions** (upstream Scope 3), we price *that*
disclosed number directly instead of estimating it — so BASF's 90-million-tonne value chain
or Nike's 9.5 million tonnes drives the cost, not a generic sector average. The estimated
version is the fallback for firms that don't report.

**Biogenic inputs aren't fossil.** For forest-products firms (pulp, paper, timber), much of the
upstream footprint is *biogenic* — carbon in sustainably-managed wood fibre that the forest
re-absorbs — not fossil carbon. We net that share out before pricing, so a pulp mill's wood
supply isn't charged as if it were steel or cement.

### Layer 4 — Reputation risk (the cost-of-capital channel)
**Question it answers:** *Do investors and lenders charge me more because of my climate
exposure?*

Academic research (**Sautner et al., 2023**) measured how a company's "climate change
exposure" is priced into its cost of capital. We map each sector to that measure and translate
it into an adjustment to the discount rate. Crucially, the sign cuts both ways: a company with
high **downside** exposure (regulatory + physical risk, e.g. a coal utility) pays *more* for
capital (≈ +27 bps), while a climate **winner** with high opportunity exposure (e.g. a renewables
developer) is financed *more cheaply* (≈ −33 bps) — consistent with the "green premium" evidence
that low-carbon firms enjoy a lower cost of capital. By default we route this to the cost of
capital, because that's the part the research supports; the revenue route is a clearly-labeled
*manual* overlay.

---

## 5. The golden rule: route each risk once (with two disclosed exceptions)

The biggest way climate models mislead is by **double-counting** — charging the same dollar
twice. The architecture routes each channel to one destination, with two honestly-flagged
boundary cases rather than a blanket guarantee:

| Channel | Where it lands (once) |
|---------|-----------------------|
| Layer 1 — carbon | Operating cost |
| Layer 2 — technology | Revenue erosion **+** a *separate* asset write-down |
| Layer 3 — supply chain | Input cost |
| Layer 4 — reputation | Cost of capital **or** revenue — never both |

For example, the carbon a firm passes on to customers is removed from *its* cost (Layer 1)
and only enters the supply chain (Layer 3) — never both. Stranded value (a balance-sheet
write-down) is kept in its own column and never added into the cash-flow cost total. And a
company's **purchased-electricity carbon (Scope 2)** is charged only once — through the higher
power prices in Layer 3, not also as a direct Layer-1 bill (unless it actually pays an explicit
carbon charge on that electricity).

**The two disclosed exceptions.** (1) A demand collapse shows up as *both* eroded revenue
(cash flow) and a stranded write-down (balance sheet) — these are two **lenses on the same
loss**, shown side by side and never summed. (2) The "% stranded" figure is defined as the
write-down actually recognised by 2050, so it always matches the dollar impairment; a separate
"strandable ceiling" shows the theoretical maximum.

---

## 6. Turning it into a value, and putting a range on it

- **Discounting.** A cost in 2045 hurts less than the same cost today, so future costs are
  discounted back to present value — using a *real* (inflation-adjusted) rate so we don't
  mix nominal cash flows with real ones.
- **Uncertainty (Monte-Carlo).** We re-run the model hundreds of times, each time nudging
  the carbon price, pass-through, and supply-chain elasticity, to get a P5–P95 range. This
  range is deliberately labeled a **conditional floor**: it's the spread *within* a chosen
  scenario, not the full uncertainty (which also includes *which* scenario comes true).
- **Sensitivity (tornado).** We swing each assumption one at a time to see which one moves
  the answer most — so you know which input is worth improving. There are two views: one for
  the cash-flow cost, one for the stranding (which is driven by different assumptions:
  trigger year, S-curve speed).

---

## 7. Beyond the number: the decision layer

The tool doesn't stop at "here's the cost." It also helps answer *what to do*:

- **Financed emissions & a temperature score** — *screening indicators* that approximate the
  shape of PCAF financed emissions and an Implied Temperature Rise (1.5 °C benchmark). They are
  **not** the certified PCAF / SBTi / PACTA metrics and shouldn't be reported as compliant with
  them.
- **Marginal Abatement Cost Curves + optimizer** — given a budget, which emission cuts buy
  the most reduction per dollar (cheapest-first).
- **Decarbonization Lever Library** — for each sector, the concrete options to cut emissions
  (renewables, heat pumps, green hydrogen, CCUS, regenerative agriculture…), positioned by
  where they sit in the value chain (your suppliers / your operations / your customers), with
  a "just transition" note on nature-and-people impacts. Overlay a company's actual plan to
  see which core levers are missing. This is a **structured reference**, not a score.
- **Disclosure export** — a report structured against **IFRS S2** and **ESRS E1**, the two
  main climate-disclosure standards. (The experimental supply-chain "contagion" amplifier is
  deliberately excluded from this export.)

---

## 8. Where the data comes from

| Piece | Source |
|-------|--------|
| Carbon prices by scenario/region/year | **NGFS Phase V** (the central-bank scenario set) |
| Technology cost/learning rates | **IRENA 2024**, **Lazard 2025 v18**, **BNEF 2024**; forecast method from **Farmer & Lafond** (2016) and **Way, Ives, Mealy & Farmer** (2022, Oxford) |
| Supply-chain structure | **EXIOBASE-3** global input-output database |
| Reputation → cost of capital | **Sautner et al. 2023** (*Journal of Finance*) |
| Sector abatement options & costs | **IPCC AR6**, **IEA**, Mission Possible Partnership |

---

## 9. What this is — and honestly isn't

**It is:** a transparent, scenario-based *screening* tool that separates the four transition
channels, avoids double-counting, shows its working, and ranges its answers.

**It isn't:**
- A precise firm-level forecast. Many inputs are sector medians (pass-through, reputation
  exposure), not company-specific — the tool flags where firm data would sharpen the answer.
- A physical-climate model. Floods and heat are a *separate* tool; this one is transition
  only.
- A tail-risk / Value-at-Risk engine. The uncertainty range is a conditional floor, and we
  label it as such rather than dressing it up as full VaR.
- A finished regulatory disclosure. It structures the output against IFRS S2 / ESRS E1, but
  a real filing needs specialist review and assured data.
- A full real-estate transition model. Buildings show near-zero here because only carbon
  pricing is modelled; performance standards, retrofit capex, and green-vs-brown rent effects
  are not yet built — so a low real-estate number is *not* a clean bill of health.
- A free-decarbonization model. Setting a net-zero target lowers future carbon cost, but the
  **capital and operating cost of the abatement** to get there is analysed separately (in the
  abatement/MACC view) and is not automatically netted into the headline — treat a target as
  reducing gross exposure, not as costless.
- A technology-equivalence oracle. Layer 2 compares a challenger's cost to an incumbent's, but
  those costs aren't always like-for-like (e.g. solar power vs coal power ignores firming/grid
  value) — the crossover year is indicative, not a dispatch-accurate parity date.
- A group-consolidation model. A diversified firm (multiple business lines) is rolled up as the
  **sum** of its lines — each line correctly transitions on its own sector/geography, but group-level
  correlation, cross-subsidy and a single optimised group plan are not modelled.

The tool covers **30 sectors** — the 20 core plus seven from the BSR lever library (apparel, consumer
goods, financial services, healthcare, professional services, telecom, and metals & mining),
industrial & construction equipment (a diesel-machinery maker whose risk is the use-phase of its
products), and two forest-products sectors — **pulp & paper** (a biomass-powered low-carbon producer)
and **solid wood / mass timber** (a transition **winner** — mass timber displaces steel and cement,
so demand grows). Metals & mining and mass timber are treated as transition **winners** (demand grows,
cheaper capital), not stranding risks. Supply-chain (Layer 3) cost is scaled to a firm's actual
**bought-in inputs**, so an asset-light, high-revenue business (a bank) no longer shows an implausible
supply-chain carbon bill.

The guiding principle throughout: **be useful and be honest about the limits.** Every place
where a figure is a proxy, an assumption, or an opt-in refinement is labeled as such — in the
tool, the audit trail, and the full methodology document. Every engine result also carries a
**data-quality flag** (firm / sector-proxy / degraded) so a number built on placeholders is
never mistaken for one built on company data.
