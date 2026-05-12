"""
Build the Transition Risk Methodology PDF for the BSR Climate Risk Platform.

Run from the repo root:
    python docs/build_transition_methodology.py

Output:
    docs/transition_risk_methodology.pdf

The PDF is the canonical reference for the four-layer transition risk
implementation in engine/transition/ and pages/11_TransitionRisk.py.
"""

from __future__ import annotations
import os
import json
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate,
    PageTemplate,
    Frame,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
)


# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(ROOT, "data", "transition")
OUTPUT_PDF = os.path.join(ROOT, "docs", "transition_risk_methodology.pdf")

BSR_ORANGE = colors.HexColor("#F4721A")
INK = colors.HexColor("#222222")
GREY = colors.HexColor("#777777")
LIGHT_GREY = colors.HexColor("#EDEDED")


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def build_styles() -> dict:
    base = getSampleStyleSheet()
    styles = {}

    styles["title"] = ParagraphStyle(
        "title", parent=base["Title"], fontName="Helvetica-Bold",
        fontSize=22, leading=28, textColor=INK, spaceAfter=4,
    )
    styles["subtitle"] = ParagraphStyle(
        "subtitle", parent=base["Normal"], fontName="Helvetica",
        fontSize=12, leading=16, textColor=GREY, spaceAfter=24,
    )
    styles["h1"] = ParagraphStyle(
        "h1", parent=base["Heading1"], fontName="Helvetica-Bold",
        fontSize=15, leading=20, textColor=BSR_ORANGE,
        spaceBefore=18, spaceAfter=8,
    )
    styles["h2"] = ParagraphStyle(
        "h2", parent=base["Heading2"], fontName="Helvetica-Bold",
        fontSize=12, leading=15, textColor=INK,
        spaceBefore=12, spaceAfter=6,
    )
    styles["h3"] = ParagraphStyle(
        "h3", parent=base["Heading3"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=13, textColor=INK,
        spaceBefore=8, spaceAfter=4,
    )
    styles["body"] = ParagraphStyle(
        "body", parent=base["BodyText"], fontName="Helvetica",
        fontSize=10, leading=14, textColor=INK, alignment=TA_JUSTIFY,
        spaceAfter=6,
    )
    styles["bullet"] = ParagraphStyle(
        "bullet", parent=base["BodyText"], fontName="Helvetica",
        fontSize=10, leading=14, textColor=INK, leftIndent=14,
        bulletIndent=4, spaceAfter=2,
    )
    styles["math"] = ParagraphStyle(
        "math", parent=base["BodyText"], fontName="Courier",
        fontSize=9.5, leading=13, textColor=INK,
        leftIndent=14, spaceBefore=4, spaceAfter=8,
        backColor=LIGHT_GREY, borderPadding=6,
    )
    styles["caption"] = ParagraphStyle(
        "caption", parent=base["Italic"], fontName="Helvetica-Oblique",
        fontSize=9, leading=12, textColor=GREY, spaceAfter=10,
    )
    styles["footer"] = ParagraphStyle(
        "footer", parent=base["Normal"], fontName="Helvetica",
        fontSize=8, leading=10, textColor=GREY, alignment=TA_CENTER,
    )
    styles["table_cell"] = ParagraphStyle(
        "table_cell", parent=base["BodyText"], fontName="Helvetica",
        fontSize=8.5, leading=11, textColor=INK,
    )
    styles["table_cell_bold"] = ParagraphStyle(
        "table_cell_bold", parent=base["BodyText"], fontName="Helvetica-Bold",
        fontSize=8.5, leading=11, textColor=INK,
    )
    return styles


# ---------------------------------------------------------------------------
# Page header / footer
# ---------------------------------------------------------------------------

def header_footer(canvas, doc):
    canvas.saveState()
    # Header band
    canvas.setFillColor(BSR_ORANGE)
    canvas.rect(0, A4[1] - 12 * mm, A4[0], 4 * mm, stroke=0, fill=1)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.setFillColor(INK)
    canvas.drawString(2 * cm, A4[1] - 17 * mm, "BSR Climate Risk Intelligence")
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(GREY)
    canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 17 * mm, "Transition Risk Methodology")
    # Footer
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawCentredString(A4[0] / 2.0, 1.2 * cm, f"Page {doc.page}")
    canvas.drawString(2 * cm, 1.2 * cm, "Internal — BSR Climate Risk Practice")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, date.today().isoformat())
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def p(text: str, styles: dict, key: str = "body") -> Paragraph:
    return Paragraph(text, styles[key])


def bullet(text: str, styles: dict) -> Paragraph:
    return Paragraph(f"• {text}", styles["bullet"])


def table_from_rows(
    header_row: list,
    data_rows: list,
    col_widths: list,
    styles: dict,
    header_color=BSR_ORANGE,
) -> Table:
    rows = [[Paragraph(c, styles["table_cell_bold"]) for c in header_row]]
    for r in data_rows:
        rows.append([Paragraph(str(c), styles["table_cell"]) for c in r])
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.white),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, GREY),
    ]))
    return t


def load_json(name: str) -> dict:
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Document content
# ---------------------------------------------------------------------------

def build_story(styles: dict) -> list:
    s = []

    # ── Title block ────────────────────────────────────────────────────────
    s.append(Spacer(1, 12 * mm))
    s.append(p(
        "<font color='#F4721A'>BSR</font> Transition Risk Layer",
        styles, "title",
    ))
    s.append(p("Methodology Reference — Implementation v1 (Session 8)", styles, "subtitle"))
    s.append(p(
        "This document specifies the four-layer transition risk model implemented in "
        "<font face='Courier'>engine/transition/</font> and surfaced via "
        "<font face='Courier'>pages/11_TransitionRisk.py</font>. It is the canonical "
        "reference for the methodology, calibration choices, and known limitations "
        "of the BSR Climate Risk Intelligence Platform's transition module.",
        styles, "body",
    ))
    s.append(p(
        "<b>Reference architecture:</b> BSR Climate Risk Practice memo "
        "<i>“Quantifying Transition Risk: Landscape, Frontier, and a Path Forward”</i> "
        "(internal, May 2026). The four layers below productise Path A of that memo: "
        "a reusable Python toolkit for sector-specific, channel-decomposed, DCF-integrable "
        "transition risk analysis.",
        styles, "body",
    ))

    # ── 1. Overview ────────────────────────────────────────────────────────
    s.append(p("1. Overview", styles, "h1"))
    s.append(p(
        "The transition risk module decomposes the financial impact of decarbonisation on "
        "an asset (or a portfolio of assets) into four channels. Each channel maps to a "
        "specific empirical or theoretical literature, routes to exactly one financial "
        "destination (cash flow, asset value, or discount rate), and is independently "
        "calibratable. The four channels can be enabled or disabled individually.",
        styles, "body",
    ))

    s.append(table_from_rows(
        ["Layer", "Channel", "Mechanism", "Routes to"],
        [
            ["L1", "Carbon cost",
             "Scope 1+2 emissions × NGFS scenario carbon price × (1 − pass-through)",
             "Cash flow OpEx"],
            ["L2", "Technology / stranding",
             "Wright's Law cost crossover (or sector demand collapse) → logistic impairment",
             "Cash flow + asset value"],
            ["L3", "Network propagation",
             "Sector-typical shock vector → Leontief inverse → focal sector input cost",
             "Cash flow input cost"],
            ["L4", "Reputational / capital",
             "Sautner CCExposure × empirical elasticities (credit / equity / revenue)",
             "Cash flow OR WACC (one only)"],
        ],
        col_widths=[1.0 * cm, 3.0 * cm, 8.0 * cm, 4.5 * cm],
        styles=styles,
    ))
    s.append(Spacer(1, 6))
    s.append(p(
        "<b>Non-duplication rule.</b> Each channel routes exactly once. Layer 4 is the only "
        "layer with a configurable destination (cash flow vs WACC); the orchestrator zeros "
        "out the alternative path so the same financial impact is never counted twice. "
        "Stranded-asset impairment from Layer 2 is reported separately from the cash-flow "
        "stream — consistent with the BSR framework's distinction between operating-cost "
        "adjustment and balance-sheet impairment.",
        styles, "body",
    ))

    # ── 2. Layer 1 — Carbon cost ───────────────────────────────────────────
    s.append(p("2. Layer 1 — Direct Carbon Cost with Pass-Through", styles, "h1"))

    s.append(p("2.1 Mathematics", styles, "h2"))
    s.append(p(
        "For each (scenario, region, year, sector), the layer computes a four-way decomposition "
        "of the firm's carbon cost:",
        styles, "body",
    ))
    s.append(p(
        "gross_cost      = (scope1 + scope2) × carbon_price<br/>"
        "absorbed        = gross_cost × (1 − pass_through)        ← margin compression<br/>"
        "passed_through  = gross_cost × pass_through              ← becomes Layer-3 shock<br/>"
        "scope3_indirect = scope3 × carbon_price × (1 − pass_through)<br/>"
        "net_carbon_opex = absorbed + scope3_indirect             ← what hits the firm CFs",
        styles, "math",
    ))
    s.append(p(
        "The pass-through coefficient encodes the empirical observation that downstream price "
        "elasticity, supply elasticity, market structure, and trade exposure determine how much "
        "of a carbon cost can be passed to customers. The remainder compresses producer margins. "
        "Two firms with identical Scope 1+2 emissions in the same scenario can experience very "
        "different financial impacts depending on these structural parameters.",
        styles, "body",
    ))

    s.append(p("2.2 Data", styles, "h2"))
    s.append(p(
        "<b>Carbon prices</b> — NGFS Phase V REMIND-MAgPIE 3.2 outputs (Nov 2023), regionalised "
        "into three groups (advanced, emerging, rest-of-world) consistent with the REMIND model "
        "regions. Stored in <font face='Courier'>data/transition/carbon_prices_ngfs.json</font>. "
        "IPCC SSP scenarios fall back to their closest NGFS analog.",
        styles, "body",
    ))
    s.append(p(
        "<b>Pass-through coefficients</b> — Sector-median values from the published empirical "
        "literature on emissions cost incidence. Stored in "
        "<font face='Courier'>data/transition/sector_pass_through.json</font> with per-sector "
        "demand elasticity, market structure tag, and trade-exposure flag.",
        styles, "body",
    ))

    s.append(p("2.3 Sources", styles, "h2"))
    s.append(bullet(
        "Sijm, Hers, Lise, Wetzelaer (2012). “CO2 Cost Pass-Through and Windfall Profits in the "
        "Power Sector.” <i>Energy Policy</i>. — Power 60–100% pass-through.", styles))
    s.append(bullet(
        "Fabra & Reguant (2014). “Pass-Through of Emissions Costs in Electricity Markets.” "
        "<i>American Economic Review</i> 104(9). — Empirical merit-order test.", styles))
    s.append(bullet(
        "Cludius, Hermann, Matthes, Graichen (2020). “The merit order effect of wind and "
        "photovoltaic electricity generation in Germany 2008-2016.” <i>Energy Economics</i>.", styles))
    s.append(bullet(
        "Frankovic (2022). “The impact of carbon pricing in a multi-region production network "
        "model.” Bundesbank Discussion Paper 06/2022.", styles))
    s.append(bullet(
        "Devulder & Lisack (2020). “Carbon tax in a production network.” Banque de France WP #813.", styles))

    # ── 3. Layer 2 — Technology disruption ─────────────────────────────────
    s.append(p("3. Layer 2 — Technology Disruption (Learning Curves)", styles, "h1"))

    s.append(p("3.1 Wright's Law", styles, "h2"))
    s.append(p(
        "Each technology has a learning rate (LR), the fractional cost reduction per doubling "
        "of cumulative installed capacity. Cost evolves as:",
        styles, "body",
    ))
    s.append(p(
        "Cost(Q) = Cost(Q₀) × (Q / Q₀) ^ b<br/>"
        "where b = log₂(1 − LR)",
        styles, "math",
    ))
    s.append(p(
        "Cumulative capacity index Q/Q₀ is computed from a scenario-specific compound growth "
        "rate. Negative growth values in the data (representing demand decline) are clamped to "
        "zero — cumulative capacity is monotonic non-decreasing; demand-side decline is captured "
        "via the sector pathway, not the technology cost curve.",
        styles, "body",
    ))

    s.append(p("3.2 Lafond Distributional Forecast", styles, "h2"))
    s.append(p(
        "The point estimate above is wrapped in a log-normal forecast band per Lafond et al. "
        "(2018). One-sigma bounds at horizon t are:",
        styles, "body",
    ))
    s.append(p(
        "log Cost_t ~ Normal( μ = log Cost_pred(t), σ = lafond_σ × √t )<br/>"
        "cost_lo = pred × exp(−σ_t)     cost_hi = pred × exp(+σ_t)",
        styles, "math",
    ))
    s.append(p(
        "lafond_σ values are calibrated from the Santa Fe Performance Curve Database. "
        "Mature technologies (solar PV, lithium-ion batteries) have tighter bands than "
        "emerging ones (electrolysers, H2-DRI steel).",
        styles, "body",
    ))

    s.append(p("3.3 Stranding Trigger", styles, "h2"))
    s.append(p(
        "An asset is flagged for stranding when one of two triggers fires within the analysis "
        "horizon:",
        styles, "body",
    ))
    s.append(bullet(
        "<b>Cost crossover</b> — challenger technology's projected cost ≤ incumbent's. Detected "
        "by year-by-year comparison along the Wright's Law trajectories.", styles))
    s.append(bullet(
        "<b>Demand collapse</b> (fossil-dependent sectors only) — sector pathway falls below 0.5 "
        "(50% demand reduction relative to 2025 baseline). Captures stranding from demand decline "
        "alone, e.g. refineries when oil demand falls regardless of biorefining cost.", styles))

    s.append(p(
        "Once triggered, impairment follows a logistic curve centred on the trigger year:",
        styles, "body",
    ))
    s.append(p(
        "frac(y) = 1 / (1 + exp(−slope × (y − y_crossover)))    where slope = 0.20<br/>"
        "annual_impairment(y) = (frac(y) − frac(y−1)) × cap<br/>"
        "cap = max(0, 1 − pathway(2050)) × replacement_value × λ<br/>"
        "λ = 1.0 if fossil_dependent else 0.5",
        styles, "math",
    ))
    s.append(p(
        "The slope of 0.20 produces ~50% impairment at the trigger year and ~95% completion "
        "after 15 years — empirically consistent with typical fossil-asset response times once "
        "a challenger reaches cost parity. The cap scales by the scenario-specific demand "
        "collapse so the same trigger year produces different stranded shares under different "
        "scenarios. Non-fossil sectors cap at 50% of replacement value (only the share tied to "
        "the incumbent technology can strand).",
        styles, "body",
    ))

    s.append(p("3.4 Sources", styles, "h2"))
    s.append(bullet(
        "Way, Ives, Mealy, Farmer (2022). “Empirically grounded technology forecasts and the "
        "energy transition.” <i>Joule</i> 6(9). — Canonical Wright's Law application to NGFS.", styles))
    s.append(bullet(
        "Lafond, Bailey, Bakker, Rebois, Zadourian, McSharry, Farmer (2018). “How well do "
        "experience curves predict technological progress?” <i>TFSC</i> 128. — Distributional "
        "forecast methodology.", styles))
    s.append(bullet(
        "Ziegler & Trancik (2021). “Re-examining rates of lithium-ion battery technology "
        "improvement and cost decline.” <i>Energy &amp; Environmental Science</i> 14.", styles))
    s.append(bullet(
        "IRENA (2023). <i>Renewable Power Generation Costs in 2022.</i>", styles))

    # ── 4. Layer 3 — Network propagation ───────────────────────────────────
    s.append(p("4. Layer 3 — Production Network Propagation", styles, "h1"))

    s.append(p("4.1 Leontief Inverse", styles, "h2"))
    s.append(p(
        "Sectoral cost shocks propagate through input-output linkages. Given the direct "
        "requirements matrix A — element A[i,j] = USD of input from sector i required to "
        "produce 1 USD of sector j's output — the Leontief inverse L = (I − A)⁻¹ aggregates "
        "all rounds of indirect input requirements.",
        styles, "body",
    ))
    s.append(p(
        "Under a Cobb-Douglas production assumption (substitution elasticity σ = 1), the total "
        "cost shock absorbed by sector j is:",
        styles, "body",
    ))
    s.append(p(
        "total_shock_j = Σᵢ L[i, j] × s_i<br/>"
        "where s_i = passed-through cost in sector i (fraction of sector i's output)",
        styles, "math",
    ))

    s.append(p("4.2 Sectoral Shock Vector", styles, "h2"))
    s.append(p(
        "For a per-asset analysis, the shock vector is built from sector-typical exposure rather "
        "than the focal asset's own pass-through (which would double-count). For each sector i:",
        styles, "body",
    ))
    s.append(p(
        "s_i = emission_intensity_i × carbon_price × pass_through_i × 10⁻⁶<br/>"
        "(emission_intensity is in tCO₂ per million USD revenue; the 10⁻⁶ converts to per-USD)",
        styles, "math",
    ))
    s.append(p(
        "The focal asset's indirect cost is then propagated × asset_revenue, less the asset's "
        "own diagonal contribution (which is already captured by Layer 1). The output also "
        "lists the top-5 upstream sectors by contribution — useful for supply-chain attribution.",
        styles, "body",
    ))

    s.append(p("4.3 Substitution Elasticity (CES Damping)", styles, "h2"))
    s.append(p(
        "The default Cobb-Douglas case (σ=1) is conservative but rigid. The implementation "
        "supports a CES-style damping: off-diagonal entries of A are scaled by 1/σ before "
        "inversion, capturing the empirical observation that intermediate-input substitution "
        "moderates shock propagation. Empirical estimates cluster σ ∈ [1.3, 3.0] (Papageorgiou "
        "et al. 2017).",
        styles, "body",
    ))

    s.append(p("4.4 Limitations", styles, "h2"))
    s.append(p(
        "The shipped I-O matrix is a 20-sector single-region aggregation calibrated against "
        "EXIOBASE-3 world totals (2019). For production use — the bespoke add-on path in the "
        "memo — replace with the full multi-regional MRIO (200 sectors × 49 regions). The "
        "current formulation also does not include endogenous default thresholds; Reisch et al. "
        "(2025) is the natural extension.",
        styles, "body",
    ))

    s.append(p("4.5 Sources", styles, "h2"))
    s.append(bullet(
        "Stadler, Wood, Bulavskaya et al. (2018). “EXIOBASE 3.” <i>Journal of Industrial "
        "Ecology</i> 22(3). — Underlying I-O calibration.", styles))
    s.append(bullet(
        "Acemoglu, Carvalho, Ozdaglar, Tahbaz-Salehi (2012). “The Network Origins of Aggregate "
        "Fluctuations.” <i>Econometrica</i> 80(5). — Theoretical foundation.", styles))
    s.append(bullet(
        "Reisch, Diem, Pichler, Stangl, Thurner (2025). “Combined climate stress testing of "
        "supply-chain networks and the financial system.” arXiv:2503.10644 — Endogenous-default "
        "extension.", styles))
    s.append(bullet(
        "Papageorgiou, Saam, Schulte (2017). “Substitution between Clean and Dirty Energy "
        "Inputs.” <i>REStat</i> 99(2). — Substitution elasticity calibration.", styles))

    # ── 5. Layer 4 — CCExposure ────────────────────────────────────────────
    s.append(p("5. Layer 4 — Reputational and Capital-Access Overlay", styles, "h1"))

    s.append(p("5.1 CCExposure Decomposition", styles, "h2"))
    s.append(p(
        "Sautner, van Lent, Vilkov, Zhang (2023) measure firm-level Climate Change Exposure "
        "from earnings-call transcripts and decompose it into three sub-measures:",
        styles, "body",
    ))
    s.append(bullet("<b>Opportunity</b> — positive narrative; revenue-uplift signal.", styles))
    s.append(bullet("<b>Regulatory</b> — policy / legal exposure; cost and spread signal.", styles))
    s.append(bullet("<b>Physical</b> — climate-physical-impact discussion; cost and spread signal.", styles))
    s.append(p(
        "The shipped proxy uses sector medians from the published 2010–2020 dataset. For "
        "production use, override <font face='Courier'>firm_override</font> in "
        "<font face='Courier'>compute_exposure_premium()</font> with the licensed firm-level "
        "Sautner data.",
        styles, "body",
    ))

    s.append(p("5.2 Empirical Elasticities", styles, "h2"))
    s.append(p(
        "Per-unit pricing impacts from Sautner et al. (2023, <i>Management Science</i>):",
        styles, "body",
    ))
    s.append(p(
        "credit_spread_Δbps   = 12 × CCE_regulatory + 6 × CCE_physical<br/>"
        "equity_premium_Δbps  = 50 × (CCE_opportunity + CCE_regulatory + CCE_physical)<br/>"
        "revenue_growth_Δbps  = 35 × CCE_opportunity − 25 × CCE_regulatory",
        styles, "math",
    ))
    s.append(p(
        "Scenario modifiers amplify or dampen the three sub-measures so that disorderly "
        "transitions widen the regulatory channel, ordered transitions widen the opportunity "
        "channel, and high-warming scenarios widen the physical channel.",
        styles, "body",
    ))

    s.append(p("5.3 Routing Rule", styles, "h2"))
    s.append(p(
        "Layer 4 is the only layer with a configurable destination. The routing parameter must "
        "be set explicitly to one of:",
        styles, "body",
    ))
    s.append(bullet(
        "<font face='Courier'>ROUTE_CASHFLOWS</font> (default) — apply the revenue growth "
        "modifier to the cash-flow stream; the WACC-side credit/equity premiums are computed "
        "for diagnostic display only.", styles))
    s.append(bullet(
        "<font face='Courier'>ROUTE_WACC</font> — apply the credit + equity premium to the "
        "discount rate; revenue modifier is zeroed. Useful when modelling firm-systematic "
        "exposure rather than idiosyncratic revenue dynamics.", styles))

    s.append(p("5.4 Sources", styles, "h2"))
    s.append(bullet(
        "Sautner, van Lent, Vilkov, Zhang (2023). “Firm-Level Climate Change Exposure.” "
        "<i>Journal of Finance</i> 78(3). — CCExposure construction.", styles))
    s.append(bullet(
        "Sautner et al. (2023). “Pricing Climate Change Exposure.” "
        "<i>Management Science</i> (forthcoming). — Empirical elasticities.", styles))
    s.append(bullet(
        "Engle, Giglio, Kelly, Lee, Stroebel (2020). “Hedging Climate Change News.” "
        "<i>RFS</i> 33(3). — Climate news beta as triangulation.", styles))

    # ── 6. Orchestration ───────────────────────────────────────────────────
    s.append(p("6. Orchestration and DCF Integration", styles, "h1"))

    s.append(p(
        "<font face='Courier'>engine.transition.transition_engine.run_asset_transition()</font> "
        "computes one asset × scenario × horizon. Per-asset outputs feed the existing "
        "<font face='Courier'>engine.dcf_engine.compute_climate_dcf()</font> via the long-form "
        "damage DataFrame produced by "
        "<font face='Courier'>transition_results_to_damage_df()</font>. The combined DCF "
        "(physical + transition) is exposed as "
        "<font face='Courier'>engine.transition.transition_dcf.compute_combined_dcf()</font> "
        "and returns three side-by-side NPVs:",
        styles, "body",
    ))
    s.append(table_from_rows(
        ["NPV", "Damage stream", "Use"],
        [
            ["Physical-only", "EAD timeline from physical engine",
             "Physical-risk-only DCF impairment"],
            ["Transition-only", "L1+L2+L3+L4 cash-flow cost stream",
             "Transition-risk attribution"],
            ["Combined", "Sum of physical and transition by year",
             "Headline climate-adjusted NPV"],
        ],
        col_widths=[3.0 * cm, 6.5 * cm, 7.0 * cm],
        styles=styles,
    ))
    s.append(Spacer(1, 6))
    s.append(p(
        "Stranded-asset PV impairment is computed independently (sum of "
        "annual_impairment_usd discounted at WACC) and reported as "
        "<font face='Courier'>total_pv_stranded_impairment</font> — separate from the cash-flow "
        "stream so users can isolate value impairment from operating-cost adjustment.",
        styles, "body",
    ))

    # ── 7. Worked examples ─────────────────────────────────────────────────
    s.append(PageBreak())
    s.append(p("7. Calibration — Worked Examples", styles, "h1"))
    s.append(p(
        "All figures from a fresh run of "
        "<font face='Courier'>run_asset_transition()</font> at the default settings (all four "
        "layers enabled, Layer-4 routing to cash flows, σ = 1.0). Currency is USD₂₀₂₀.",
        styles, "body",
    ))

    s.append(p("7.1 Coal-Fired Power Plant — USA", styles, "h2"))
    s.append(p(
        "Inputs: $500M replacement value, 2.5 MtCO₂/yr Scope 1, 50 ktCO₂/yr Scope 2, "
        "200 ktCO₂/yr Scope 3, $300M annual revenue, sector = power_coal.",
        styles, "body",
    ))
    s.append(table_from_rows(
        ["Scenario", "L1 2050", "L2 rev 2050", "L3 2050", "L4 2050", "Total CF 2050", "Cum. impairment 2025–50"],
        [
            ["Net Zero 2050",     "$169M", "$294M", "$0.1M", "$31.7M", "$495M", "$266M"],
            ["Current Policies",  "$7M",   "$36M",  "$0.0M", "$15.4M", "$59M",  "$33M"],
            ["Fragmented World",  "$92M",  "$ —",   "$0.1M", "$ —",    "$377M", "$168M"],
        ],
        col_widths=[3.5*cm, 1.7*cm, 1.9*cm, 1.6*cm, 1.7*cm, 2.2*cm, 3.4*cm],
        styles=styles,
    ))
    s.append(Spacer(1, 6))
    s.append(p(
        "Stranding crossover is 2025 across all scenarios because solar PV is already cheaper "
        "than new-build coal. The scenario differentiation comes from (a) the Layer-1 carbon "
        "cost, which scales linearly with the regional carbon price, and (b) the Layer-2 "
        "impairment cap, which scales with the scenario-specific demand collapse "
        "(power_coal pathway: 0.02 in NZ2050, 0.88 in Current Policies).",
        styles, "body",
    ))

    s.append(p("7.2 Oil Refinery — USA", styles, "h2"))
    s.append(p(
        "Inputs: $2B replacement value, 4.5 MtCO₂/yr Scope 1, 0.3 MtCO₂/yr Scope 2, "
        "8 MtCO₂/yr Scope 3, $8B revenue, sector = oil_refining.",
        styles, "body",
    ))
    s.append(table_from_rows(
        ["Scenario", "L1 2050", "L2 rev 2050", "Total CF 2050", "Cum. impairment 2025–50", "Crossover"],
        [
            ["Net Zero 2050",     "$1.3B",  "$6.4B",  "$8.4B",  "$1.36B",  "2039"],
            ["Delayed Transition","$1.2B",  "$5.6B",  "$8.0B",  "$1.05B",  "2044"],
            ["Current Policies",  "$58M",   "$640M",  "$1.0B",  "$0",      "no trigger"],
        ],
        col_widths=[3.6*cm, 1.7*cm, 1.9*cm, 2.2*cm, 3.0*cm, 2.6*cm],
        styles=styles,
    ))
    s.append(Spacer(1, 6))
    s.append(p(
        "Refining has no cost crossover (biorefining stays more expensive through 2050), but "
        "the demand-collapse trigger fires when the oil_refining pathway crosses below 0.5 — "
        "in NZ2050 that happens around 2039. Under Current Policies, demand stays above 0.92 "
        "and no impairment is triggered. The Layer-2 revenue erosion ($6.4B in NZ2050) is the "
        "dominant component because the firm has $8B revenue and the pathway falls to 0.20.",
        styles, "body",
    ))

    s.append(p("7.3 Commercial Office Building — USA", styles, "h2"))
    s.append(p(
        "Inputs: $50M replacement value, 200 tCO₂/yr Scope 1, 800 tCO₂/yr Scope 2, "
        "$15M revenue, sector = real_estate_commercial.",
        styles, "body",
    ))
    s.append(table_from_rows(
        ["Scenario", "L1 2050", "L4 2050", "Total CF 2050", "Cum. impairment"],
        [
            ["Net Zero 2050",    "$0.29M",  "−$0.52M", "−$0.22M", "$0"],
            ["Current Policies", "$0.01M",  "−$0.38M", "−$0.36M", "$0"],
        ],
        col_widths=[3.6*cm, 2.2*cm, 2.2*cm, 2.4*cm, 2.6*cm],
        styles=styles,
    ))
    s.append(Spacer(1, 6))
    s.append(p(
        "An office building with a low-carbon footprint shows a small net <i>positive</i> "
        "transition outcome under both scenarios — the Layer-4 opportunity premium "
        "(real_estate_commercial CCE opportunity = 0.85; growth bps = +35×0.85 − 25×0.95 ≈ −0.50 "
        "after scenario modifiers, but cumulative compounding pushes the dollar revenue uplift "
        "ahead of the modest Layer-1 carbon cost). No stranding because real estate has no "
        "fossil-dependent flag and the sector pathway is mildly positive in all scenarios.",
        styles, "body",
    ))

    # ── 8. Limitations ─────────────────────────────────────────────────────
    s.append(p("8. Known Limitations", styles, "h1"))
    s.append(bullet(
        "<b>I-O resolution.</b> The shipped 20-sector single-region matrix is a screening tool. "
        "Production deployments should swap in EXIOBASE-3 MRIO (200 × 49) — the bespoke add-on "
        "path in the memo. The Leontief solver in network_propagation.py works on any square "
        "matrix; only the data file changes.", styles))
    s.append(bullet(
        "<b>CCExposure data.</b> Sector medians stand in for firm-level scores. The firm-level "
        "Sautner et al. dataset is licensed separately; pass it through "
        "<font face='Courier'>firm_override</font>.", styles))
    s.append(bullet(
        "<b>Carbon-price snapshot.</b> Values approximate published NGFS Phase V REMIND-MAgPIE "
        "outputs as of November 2023. Refresh from the NGFS Scenarios Portal for regulatory "
        "disclosures — phase updates change values materially.", styles))
    s.append(bullet(
        "<b>Pass-through.</b> Sector-median values; firm-specific values vary materially with "
        "market power, contract structure, and trade exposure. Override per-asset via "
        "<font face='Courier'>pass_through_override</font>.", styles))
    s.append(bullet(
        "<b>No endogenous default.</b> Layer 3 propagates linearly through the IO network; "
        "the Reisch et al. (2025) endogenous-default extension is not implemented.", styles))
    s.append(bullet(
        "<b>Scope 3 simplification.</b> Scope 3 is treated as a single number absorbed by the "
        "(1 − pass_through) coefficient. A full upstream Scope 3 decomposition would be "
        "category-by-category (purchased goods, transport, use-of-sold-products) and route "
        "through Layer 3 explicitly.", styles))

    # ── 9. Implementation pointers ─────────────────────────────────────────
    s.append(p("9. Implementation Pointers", styles, "h1"))
    s.append(table_from_rows(
        ["Component", "Path"],
        [
            ["Orchestrator entry", "engine.transition.transition_engine.run_asset_transition"],
            ["Portfolio orchestrator", "engine.transition.transition_engine.run_portfolio_transition"],
            ["DCF integration", "engine.transition.transition_dcf.compute_combined_dcf"],
            ["Layer 1", "engine.transition.carbon_pricing.compute_carbon_cost"],
            ["Layer 2", "engine.transition.learning_curves.compute_stranding"],
            ["Layer 3", "engine.transition.network_propagation.propagate_carbon_shock"],
            ["Layer 4", "engine.transition.cc_exposure.compute_exposure_premium"],
            ["Streamlit UI", "pages/11_TransitionRisk.py"],
            ["Test suite", "tests/test_transition.py (42 tests)"],
            ["Carbon prices", "data/transition/carbon_prices_ngfs.json"],
            ["Pass-through table", "data/transition/sector_pass_through.json"],
            ["Learning curves", "data/transition/learning_curves.json"],
            ["Sector pathways", "data/transition/sector_pathways.json"],
            ["CCExposure proxy", "data/transition/cc_exposure_proxy.json"],
            ["I-O matrix", "data/transition/io_matrix.json"],
            ["Sector taxonomy", "data/transition/sector_taxonomy.json"],
        ],
        col_widths=[5.0 * cm, 11.5 * cm],
        styles=styles,
    ))

    # ── Appendix A: Sector taxonomy ────────────────────────────────────────
    s.append(PageBreak())
    s.append(p("Appendix A — Sector Taxonomy", styles, "h1"))
    s.append(p(
        "Sectors implemented in the transition module. Emission intensity is in tCO₂ per "
        "million USD of revenue (sector-typical).",
        styles, "body",
    ))
    tax = load_json("sector_taxonomy.json")["sectors"]
    rows = []
    for k, v in tax.items():
        rows.append([
            k,
            v.get("label", ""),
            v.get("primary_technology", "—"),
            v.get("challenger_technology") or "—",
            "✓" if v.get("fossil_dependent") else "—",
            f"{v.get('emission_intensity_t_per_revenue', 0):.2f}",
        ])
    s.append(table_from_rows(
        ["Key", "Label", "Incumbent tech", "Challenger tech", "Fossil-dep.", "EI (t/M$)"],
        rows,
        col_widths=[2.7*cm, 4.2*cm, 3.0*cm, 3.0*cm, 1.4*cm, 1.6*cm],
        styles=styles,
    ))

    # ── Appendix B: Pass-through table ─────────────────────────────────────
    s.append(PageBreak())
    s.append(p("Appendix B — Pass-Through Coefficients", styles, "h1"))
    s.append(p(
        "Sector-median values drawn from the published empirical literature. Demand elasticity "
        "is short-run own-price (Marshallian).",
        styles, "body",
    ))
    spt = load_json("sector_pass_through.json")["sectors"]
    rows = []
    for k, v in spt.items():
        rows.append([
            k,
            f"{v['pass_through']*100:.0f}%",
            f"{v['demand_elasticity']:+.2f}",
            v["market_structure"],
            "✓" if v["trade_exposed"] else "—",
            v.get("source_ref", ""),
        ])
    s.append(table_from_rows(
        ["Sector", "PT", "Demand-η", "Market structure", "Trade", "Source"],
        rows,
        col_widths=[2.7*cm, 1.2*cm, 1.5*cm, 3.5*cm, 1.0*cm, 6.0*cm],
        styles=styles,
    ))

    # ── Appendix C: Learning rates ─────────────────────────────────────────
    s.append(PageBreak())
    s.append(p("Appendix C — Technology Learning Rates", styles, "h1"))
    s.append(p(
        "Learning rate = fractional cost reduction per doubling of cumulative installed "
        "capacity. Lafond σ controls the width of the log-normal forecast band.",
        styles, "body",
    ))
    lc = load_json("learning_curves.json")["technologies"]
    challengers = []
    incumbents = []
    for k, v in lc.items():
        row = [
            v.get("label", k),
            f"{v['learning_rate']*100:.1f}%",
            f"{v.get('lafond_sigma', 0):.3f}",
            v.get("source_ref", ""),
        ]
        (challengers if v.get("category") == "challenger" else incumbents).append(row)
    s.append(p("Challenger technologies", styles, "h3"))
    s.append(table_from_rows(
        ["Technology", "LR", "Lafond σ", "Source"],
        challengers,
        col_widths=[5.0*cm, 1.2*cm, 1.5*cm, 8.2*cm],
        styles=styles,
    ))
    s.append(Spacer(1, 8))
    s.append(p("Incumbent technologies", styles, "h3"))
    s.append(table_from_rows(
        ["Technology", "LR", "Lafond σ", "Source"],
        incumbents,
        col_widths=[5.0*cm, 1.2*cm, 1.5*cm, 8.2*cm],
        styles=styles,
    ))

    # ── Appendix D: Carbon prices ──────────────────────────────────────────
    s.append(PageBreak())
    s.append(p("Appendix D — NGFS Carbon Prices (USD/tCO₂)", styles, "h1"))
    s.append(p(
        "NGFS Phase V REMIND-MAgPIE 3.2 carbon-price trajectories, sampled at 5-year intervals. "
        "Region groups: <b>advanced</b> (USA, EU, JPN, AUS, CAN, KOR, SGP, ISR), "
        "<b>emerging</b> (CHN, IND, BRA, MEX, IDN, RUS, ZAF, TUR…), "
        "<b>rest-of-world</b> (default).",
        styles, "body",
    ))
    cp = load_json("carbon_prices_ngfs.json")["scenarios"]
    for region in ("advanced", "emerging", "rest_of_world"):
        s.append(p(f"Region: {region.replace('_', ' ').title()}", styles, "h3"))
        rows = []
        for sc_id, scen in cp.items():
            curve = scen.get(region, {})
            rows.append([
                scen.get("label", sc_id),
                f"${curve.get('2025', 0):.0f}",
                f"${curve.get('2030', 0):.0f}",
                f"${curve.get('2035', 0):.0f}",
                f"${curve.get('2040', 0):.0f}",
                f"${curve.get('2045', 0):.0f}",
                f"${curve.get('2050', 0):.0f}",
            ])
        s.append(table_from_rows(
            ["Scenario", "2025", "2030", "2035", "2040", "2045", "2050"],
            rows,
            col_widths=[5.0*cm, 1.7*cm, 1.7*cm, 1.7*cm, 1.7*cm, 1.7*cm, 1.8*cm],
            styles=styles,
        ))
        s.append(Spacer(1, 8))

    # ── Appendix E: Bibliography ───────────────────────────────────────────
    s.append(PageBreak())
    s.append(p("Appendix E — Bibliography", styles, "h1"))

    s.append(p("Architecture and framework", styles, "h3"))
    s.append(bullet(
        "BSR Climate Risk Practice (May 2026). <i>Quantifying Transition Risk: Landscape, "
        "Frontier, and a Path Forward.</i> Internal memo.", styles))
    s.append(bullet(
        "BSR. <i>From Climate Science to Corporate Strategy.</i> "
        "https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf", styles))

    s.append(p("Pass-through (Layer 1)", styles, "h3"))
    s.append(bullet(
        "Sijm, Hers, Lise, Wetzelaer (2012). <i>Energy Policy</i>. "
        "DOI: 10.1016/j.enpol.2007.10.027", styles))
    s.append(bullet(
        "Fabra & Reguant (2014). <i>American Economic Review</i> 104(9). "
        "DOI: 10.1257/aer.104.9.2872", styles))
    s.append(bullet(
        "Cludius, Hermann, Matthes, Graichen (2020). <i>Energy Economics</i>.", styles))
    s.append(bullet(
        "Frankovic (2022). Bundesbank Discussion Paper 06/2022.", styles))
    s.append(bullet(
        "Devulder & Lisack (2020). Banque de France WP #813.", styles))

    s.append(p("Learning curves (Layer 2)", styles, "h3"))
    s.append(bullet(
        "Way, Ives, Mealy, Farmer (2022). <i>Joule</i> 6(9). "
        "DOI: 10.1016/j.joule.2022.08.009", styles))
    s.append(bullet(
        "Lafond, Bailey, Bakker, Rebois, Zadourian, McSharry, Farmer (2018). "
        "<i>Tech Forecasting &amp; Social Change</i> 128. "
        "DOI: 10.1016/j.techfore.2017.11.001", styles))
    s.append(bullet(
        "Ziegler & Trancik (2021). <i>Energy &amp; Environmental Science</i> 14.", styles))
    s.append(bullet(
        "IRENA (2023). <i>Renewable Power Generation Costs in 2022.</i>", styles))

    s.append(p("I-O networks (Layer 3)", styles, "h3"))
    s.append(bullet(
        "Stadler, Wood, Bulavskaya et al. (2018). <i>Journal of Industrial Ecology</i> 22(3). "
        "DOI: 10.1111/jiec.12715", styles))
    s.append(bullet(
        "Acemoglu, Carvalho, Ozdaglar, Tahbaz-Salehi (2012). <i>Econometrica</i> 80(5).", styles))
    s.append(bullet(
        "Reisch, Diem, Pichler, Stangl, Thurner (2025). arXiv:2503.10644.", styles))
    s.append(bullet(
        "Papageorgiou, Saam, Schulte (2017). <i>Review of Economics &amp; Statistics</i> 99(2).", styles))

    s.append(p("CCExposure (Layer 4)", styles, "h3"))
    s.append(bullet(
        "Sautner, van Lent, Vilkov, Zhang (2023). <i>Journal of Finance</i> 78(3). "
        "DOI: 10.1111/jofi.13219", styles))
    s.append(bullet(
        "Sautner et al. (2023). <i>Management Science</i> (forthcoming).", styles))
    s.append(bullet(
        "Engle, Giglio, Kelly, Lee, Stroebel (2020). <i>RFS</i> 33(3).", styles))

    s.append(p("Scenarios", styles, "h3"))
    s.append(bullet(
        "NGFS Phase V Scenarios Portal: https://www.ngfs.net/ngfs-scenarios-portal/", styles))
    s.append(bullet(
        "IEA World Energy Outlook 2023: "
        "https://www.iea.org/reports/world-energy-outlook-2023", styles))
    s.append(bullet(
        "IPCC AR6 WG1 SPM: "
        "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/", styles))

    return s


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_pdf(output_path: str = OUTPUT_PDF) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    doc = BaseDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.0 * cm,
        title="BSR Transition Risk Methodology",
        author="BSR Climate Risk Intelligence Platform",
    )

    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        showBoundary=0,
    )
    template = PageTemplate(id="default", frames=[frame], onPage=header_footer)
    doc.addPageTemplates([template])

    styles = build_styles()
    story = build_story(styles)

    doc.build(story)
    return output_path


if __name__ == "__main__":
    out = build_pdf()
    print(f"Wrote: {out}")
