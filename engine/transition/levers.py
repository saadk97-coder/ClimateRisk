"""
Decarbonization Lever Library — structured reference (NOT a scoring engine).

Maps a business's exposure to the specific decarbonization levers available in
its sector, positioned by value-chain stage (upstream / own operations /
downstream), so the levers can be overlaid against the entity's own transition
plan for a descriptive gap analysis.

Approach adapted from BSR's "Decarbonization Lever Library": the taxonomy
structure, value-chain positioning and nature/people impact lens are carried
over; the underlying cost / maturity / potential figures are refreshed
indicative screening ranges (see data/transition/lever_library.json _meta).

Design discipline (per the BSR framework's "do-not-automate" boundary): this
module returns *reference content* and a simple coverage count. It deliberately
does NOT emit a synthetic "transition-readiness score" — the plan overlay is a
manual analyst input and the output is a factual gap list, not a rating.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from engine.transition.data_loader import load_lever_library, load_sector_taxonomy

# Value-chain positions, in reporting order.
POSITIONS = ("upstream", "own_operations", "downstream")
POSITION_LABELS = {
    "upstream": "Upstream (suppliers / purchased inputs)",
    "own_operations": "Own operations (Scope 1+2 direct)",
    "downstream": "Downstream (products / customers / use-phase)",
}
RELEVANCE_ORDER = {"primary": 0, "secondary": 1}


@dataclass
class Lever:
    """A single decarbonization lever with its reference attributes."""
    id: str
    name: str
    domain: str
    domain_label: str
    description: str
    cost_range_usd_per_tco2: List[float]
    mitigation_potential: str
    maturity: str
    net_zero_2050_role: str
    dependencies: List[str]
    nature_people: Dict[str, str]
    applicable_sectors: List[str]
    references: List[str]

    def cost_label(self) -> str:
        lo, hi = (self.cost_range_usd_per_tco2 + [0, 0])[:2]
        return f"{lo:g} to {hi:g} $/tCO₂e"


@dataclass
class SectorLever:
    """A lever as it applies to a specific sector: value-chain position + relevance."""
    lever: Lever
    position: str
    relevance: str
    rationale: str
    in_plan: bool = False   # set by the plan overlay


@dataclass
class PlanGap:
    """Result of overlaying a transition plan onto a sector's lever map."""
    sector: str
    covered: List[SectorLever] = field(default_factory=list)      # in-plan
    gaps: List[SectorLever] = field(default_factory=list)         # applicable but not in plan
    primary_total: int = 0
    primary_covered: int = 0

    @property
    def coverage_caption(self) -> str:
        """Descriptive coverage of PRIMARY levers (factual count, not a score)."""
        if self.primary_total == 0:
            return "No primary levers mapped for this sector."
        return (f"{self.primary_covered} of {self.primary_total} primary "
                f"levers marked in-plan.")


def _domain_label(domain: str, lib: dict) -> str:
    return lib.get("domains", {}).get(domain, {}).get("label", domain)


def get_lever(lever_id: str) -> Optional[Lever]:
    """Return a fully-hydrated Lever, or None if the id is unknown."""
    lib = load_lever_library()
    raw = lib.get("levers", {}).get(lever_id)
    if not raw:
        return None
    return Lever(
        id=lever_id,
        name=raw["name"],
        domain=raw["domain"],
        domain_label=_domain_label(raw["domain"], lib),
        description=raw["description"],
        cost_range_usd_per_tco2=list(raw.get("cost_range_usd_per_tco2", [0, 0])),
        mitigation_potential=raw.get("mitigation_potential", "n/a"),
        maturity=raw.get("maturity", "n/a"),
        net_zero_2050_role=raw.get("net_zero_2050_role", ""),
        dependencies=list(raw.get("dependencies", [])),
        nature_people=dict(raw.get("nature_people", {})),
        applicable_sectors=list(raw.get("applicable_sectors", [])),
        references=list(raw.get("references", [])),
    )


def all_levers() -> List[Lever]:
    """Every lever in the library, ordered by domain then name."""
    lib = load_lever_library()
    order = {d: m.get("order", 99) for d, m in lib.get("domains", {}).items()}
    levers = [get_lever(lid) for lid in lib.get("levers", {})]
    levers = [lv for lv in levers if lv is not None]
    levers.sort(key=lambda lv: (order.get(lv.domain, 99), lv.name))
    return levers


def domains() -> Dict[str, str]:
    """Ordered {domain_id: label}."""
    lib = load_lever_library()
    items = sorted(lib.get("domains", {}).items(), key=lambda kv: kv[1].get("order", 99))
    return {d: m.get("label", d) for d, m in items}


def sector_levers(sector: str) -> List[SectorLever]:
    """
    All levers mapped to a sector, ordered by value-chain position then
    relevance (primary before secondary). Empty list if the sector is unmapped.
    """
    lib = load_lever_library()
    rows = lib.get("sector_lever_map", {}).get(sector, [])
    out: List[SectorLever] = []
    for r in rows:
        lv = get_lever(r["lever"])
        if lv is None:
            continue
        out.append(SectorLever(
            lever=lv,
            position=r.get("position", "own_operations"),
            relevance=r.get("relevance", "secondary"),
            rationale=r.get("rationale", ""),
        ))
    pos_order = {p: i for i, p in enumerate(POSITIONS)}
    out.sort(key=lambda sl: (pos_order.get(sl.position, 99),
                             RELEVANCE_ORDER.get(sl.relevance, 9),
                             sl.lever.name))
    return out


def sector_levers_by_position(sector: str) -> Dict[str, List[SectorLever]]:
    """Sector levers grouped into the three value-chain positions (ordered)."""
    grouped: Dict[str, List[SectorLever]] = {p: [] for p in POSITIONS}
    for sl in sector_levers(sector):
        grouped.setdefault(sl.position, []).append(sl)
    return grouped


def overlay_plan(sector: str, levers_in_plan: List[str]) -> PlanGap:
    """
    Overlay a transition plan (a list of lever ids the entity says it is
    pursuing) onto the sector's applicable levers.

    Returns a PlanGap with covered vs gap levers and a factual primary-lever
    coverage count. This is a descriptive reference overlay, not a score.
    """
    in_plan = set(levers_in_plan or [])
    gap = PlanGap(sector=sector)
    for sl in sector_levers(sector):
        sl.in_plan = sl.lever.id in in_plan
        if sl.relevance == "primary":
            gap.primary_total += 1
            if sl.in_plan:
                gap.primary_covered += 1
        (gap.covered if sl.in_plan else gap.gaps).append(sl)
    return gap


def applicable_sectors_for(lever_id: str) -> List[str]:
    """Sectors whose map includes this lever (from the authoritative map)."""
    lib = load_lever_library()
    out = []
    for sec, rows in lib.get("sector_lever_map", {}).items():
        if any(r.get("lever") == lever_id for r in rows):
            out.append(sec)
    return out


def sector_label(sector: str) -> str:
    return load_sector_taxonomy()["sectors"].get(sector, {}).get("label", sector)
