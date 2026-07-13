"""
Adaptive Capacity / Transition Strategy layer.

Layer 2 as first written answers "what is this company's exposure if it stays
FROZEN and does nothing" — an ICE automaker loses ~100% of its product demand
with $0 recaptured from EVs. That is a *gross vulnerability* number, not a
*residual risk* number. Real companies migrate toward the low-carbon business,
capture some of the green upside, and spend capex to get there — and how well
they do that depends on where they start.

This module converts gross erosion into residual risk via three levers:

  * ambition A ∈ [0,1]     — how much the company pivots from the declining
                              incumbent activity to the growing challenger one.
                              DEFAULTED FROM THE SCENARIO NARRATIVE (Net-Zero →
                              aggressive pivot; Current Policies → minimal),
                              overridable per company.
  * positioning P ∈ [0,1]  — how well-placed it is TODAY. "Science": derived from
                              emissions intensity (vs sector), decarb-lever
                              readiness of the sector (Lever Library maturities),
                              and transition-plan strength/progress (target +
                              in-plan lever coverage). "Art": a manual override.
  * transition capex        — the cost of the pivot. Company-provided, else
                              estimated from pivot scale × sector ratio × a
                              geographic/context buffer × a positioning factor.

Non-duplication
---------------
  * capture reduces the REVENUE-erosion lens (cash flow),
  * positioning reduces the STRANDING lens (balance sheet — a firm already partly
    transitioned has less incumbent base to strand),
  * transition capex is a NEW cash-flow cost (the investment that earns capture).
Each routes exactly once.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from engine.transition.data_loader import (
    load_adaptive_capacity,
    load_lever_library,
    load_sector_taxonomy,
    map_scenario_to_ngfs,
)

_BASE_YEAR = 2025
_END_YEAR = 2050


@dataclass
class AdaptiveStrategy:
    asset_id: str
    sector: str
    scenario_id: str
    ambition: float                       # A ∈ [0,1]
    positioning: float                    # P ∈ [0,1]
    positioning_source: str               # 'override (art)' | 'derived (science)'
    positioning_components: Dict[str, float]
    capture_fraction: float               # share of gross erosion offset (steady-state)
    already_transitioned: float           # share of incumbent base already de-risked
    transition_capex_usd: float           # total (phased separately)
    capex_source: str                     # 'company-provided' | 'model-estimated'
    annual_capex_usd: Dict[int, float] = field(default_factory=dict)
    notes: str = ""


# ---------------------------------------------------------------------------
# Ambition — scenario-narrative default
# ---------------------------------------------------------------------------
def scenario_ambition(scenario_id: str, override: Optional[float] = None) -> float:
    """Default pivot ambition implied by the scenario narrative (overridable)."""
    if override is not None:
        return max(0.0, min(1.0, float(override)))
    m = load_adaptive_capacity()["scenario_ambition"]
    return float(m.get(scenario_id, m.get(map_scenario_to_ngfs(scenario_id), m["_default"])))


# ---------------------------------------------------------------------------
# Positioning — derived "science" (with manual "art" override)
# ---------------------------------------------------------------------------
def sector_lever_readiness(sector: str) -> float:
    """Adaptability of a sector's PRIMARY decarb levers, from their commercial
    maturity in the Lever Library (mature/cheap → easier pivot). 0.5 if unmapped."""
    lib = load_lever_library()
    mat_score = load_adaptive_capacity()["maturity_readiness"]
    rows = lib.get("sector_lever_map", {}).get(sector, [])
    levers = lib.get("levers", {})
    scores = []
    for r in rows:
        if r.get("relevance") != "primary":
            continue
        lv = levers.get(r.get("lever"), {})
        scores.append(float(mat_score.get(lv.get("maturity", "emerging"), 0.4)))
    return sum(scores) / len(scores) if scores else 0.5


def _plan_strength_from_target(target_year: int, residual_pct: float) -> float:
    """decarb_target_year (+ residual) → plan-strength component of positioning."""
    tbl = load_adaptive_capacity()["positioning"]["target_year_to_plan_strength"]
    if not target_year or target_year <= _BASE_YEAR:
        return float(tbl["none"])
    anchors = sorted((int(y), float(v)) for y, v in tbl.items() if y.isdigit())
    if target_year <= anchors[0][0]:
        base = anchors[0][1]
    elif target_year >= anchors[-1][0]:
        base = anchors[-1][1]
    else:
        base = anchors[-1][1]
        for (y0, v0), (y1, v1) in zip(anchors, anchors[1:]):
            if y0 <= target_year <= y1:
                base = v0 + (target_year - y0) / (y1 - y0) * (v1 - v0)
                break
    return base * (1.0 - max(0.0, min(1.0, residual_pct / 100.0)))


def _emissions_positioning(sector: str, scope12_tco2: float, revenue_usd: float) -> float:
    """Entity Scope 1+2 intensity vs the sector-typical intensity: cleaner-than-peers
    → better positioned. Returns [0,1] (1 = far below sector intensity)."""
    tax = load_sector_taxonomy()["sectors"]
    sec_int = float(tax.get(sector, {}).get("emission_intensity_t_per_revenue", 100.0))  # t/$M output
    rev_m = revenue_usd / 1e6
    if rev_m <= 0 or sec_int <= 0:
        return 0.5
    ent_int = scope12_tco2 / rev_m
    ratio = ent_int / sec_int                       # <1 = cleaner than sector
    # map ratio 0→1.0, 1→0.5, 2+→~0.2 (smooth, bounded)
    return max(0.0, min(1.0, 1.0 / (1.0 + ratio)))


def derive_positioning(
    sector: str,
    scope12_tco2: float,
    revenue_usd: float,
    target_year: int = 0,
    residual_pct: float = 0.0,
    plan_coverage: Optional[float] = None,
) -> tuple[float, Dict[str, float]]:
    """Compute the 'science' positioning score P ∈ [0,1] and its components.

    plan_coverage : share of the sector's PRIMARY Lever-Library levers the company
        has in its transition plan (0..1), supplied by the app; falls back to the
        target-derived plan strength when not provided.
    """
    w = load_adaptive_capacity()["positioning"]["weights"]
    plan_strength = _plan_strength_from_target(target_year, residual_pct)
    lever_readiness = sector_lever_readiness(sector)
    emissions_pos = _emissions_positioning(sector, scope12_tco2, revenue_usd)
    coverage = plan_strength if plan_coverage is None else max(0.0, min(1.0, plan_coverage))
    comp = {
        "plan_strength": round(plan_strength, 3),
        "lever_readiness": round(lever_readiness, 3),
        "emissions_positioning": round(emissions_pos, 3),
        "plan_coverage": round(coverage, 3),
    }
    P = (w["plan_strength"] * plan_strength + w["lever_readiness"] * lever_readiness
         + w["emissions_positioning"] * emissions_pos + w["plan_coverage"] * coverage)
    return max(0.0, min(1.0, P)), comp


# ---------------------------------------------------------------------------
# Capture & capex
# ---------------------------------------------------------------------------
def _capture_fraction(ambition: float, positioning: float,
                      challenger_headroom: float = 1.0) -> float:
    """Steady-state share of gross erosion offset by pivoting = ambition ×
    positioning_effectiveness, capped by the opportunity ceiling (challenger-market
    growth headroom)."""
    cfg = load_adaptive_capacity()["capture"]
    p_eff = positioning ** float(cfg["positioning_effectiveness_exponent"])
    ceiling = max(float(cfg["opportunity_ceiling_floor"]), min(1.0, challenger_headroom))
    return max(0.0, min(1.0, min(ambition * p_eff, ceiling)))


def _triangular_capex_phasing(total: float, start: int, end: int,
                              peak_frac: float) -> Dict[int, float]:
    """Front-loaded triangular capex profile peaking at start + peak_frac·window."""
    years = list(range(start, end + 1))
    if total <= 0 or len(years) <= 1:
        return {y: (total if y == start else 0.0) for y in years}
    peak = start + max(1, int(round(peak_frac * (end - start))))
    weights = {}
    for y in years:
        if y <= peak:
            wgt = (y - start + 1) / (peak - start + 1)
        else:
            wgt = max(0.0, (end - y) / (end - peak + 1))
        weights[y] = wgt
    s = sum(weights.values()) or 1.0
    return {y: round(total * weights[y] / s, 2) for y in years}


def estimate_transition_capex(
    sector: str, region_band: str, ambition: float, positioning: float,
    replacement_value: float,
) -> float:
    """Model estimate: ambition × replacement_value × sector_pivot_ratio ×
    region_multiplier × positioning_capex_factor (laggards pay more)."""
    cfg = load_adaptive_capacity()["transition_capex"]
    ratio = float(cfg["sector_pivot_capex_ratio"].get(
        sector, cfg["sector_pivot_capex_ratio"]["_default"]))
    region_mult = float(cfg["region_multiplier"].get(region_band, 1.0))
    pf = cfg["positioning_capex_factor"]
    # linear in P: P=0 → poor multiplier, P=1 → strong multiplier
    pos_factor = float(pf["poor"]) + (float(pf["strong"]) - float(pf["poor"])) * positioning
    return max(0.0, ambition * max(0.0, replacement_value) * ratio * region_mult * pos_factor)


def build_strategy(
    asset_id: str,
    sector: str,
    scenario_id: str,
    region_band: str,
    scope12_tco2: float,
    revenue_usd: float,
    replacement_value: float,
    horizon: List[int],
    target_year: int = 0,
    residual_pct: float = 0.0,
    ambition_override: Optional[float] = None,
    positioning_override: Optional[float] = None,
    plan_coverage: Optional[float] = None,
    transition_capex_override: Optional[float] = None,
    challenger_headroom: float = 1.0,
) -> AdaptiveStrategy:
    """Assemble the full transition strategy for one asset × scenario."""
    ambition = scenario_ambition(scenario_id, ambition_override)

    if positioning_override is not None:
        P = max(0.0, min(1.0, float(positioning_override)))
        p_src = "override (art)"
        comp = {"override": round(P, 3)}
    else:
        P, comp = derive_positioning(sector, scope12_tco2, revenue_usd,
                                     target_year, residual_pct, plan_coverage)
        p_src = "derived (science)"

    capture = _capture_fraction(ambition, P, challenger_headroom)
    already = float(load_adaptive_capacity()["positioning"]["already_transitioned_max"]) * P

    if transition_capex_override is not None and transition_capex_override > 0:
        total_capex = float(transition_capex_override)
        capex_src = "company-provided"
    else:
        total_capex = estimate_transition_capex(sector, region_band, ambition, P, replacement_value)
        capex_src = "model-estimated"

    end = max(horizon) if horizon else _END_YEAR
    tgt = target_year if (target_year and target_year > _BASE_YEAR) else end
    peak_frac = float(load_adaptive_capacity()["transition_capex"]["phasing"]["peak_fraction_of_window"])
    annual_capex = _triangular_capex_phasing(total_capex, min(horizon) if horizon else _BASE_YEAR,
                                             min(tgt, end), peak_frac)
    # ensure every horizon year has a key
    annual_capex = {y: annual_capex.get(y, 0.0) for y in horizon}

    return AdaptiveStrategy(
        asset_id=asset_id, sector=sector, scenario_id=scenario_id,
        ambition=round(ambition, 3), positioning=round(P, 3), positioning_source=p_src,
        positioning_components=comp, capture_fraction=round(capture, 3),
        already_transitioned=round(already, 3),
        transition_capex_usd=round(total_capex, 2), capex_source=capex_src,
        annual_capex_usd=annual_capex,
        notes=f"ambition={ambition:.2f} (scenario default), positioning={P:.2f} [{p_src}], "
              f"capture={capture:.2f}, capex {capex_src}",
    )
