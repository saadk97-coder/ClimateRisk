"""
Lever-level capital plan — a bottom-up build of transition capex from the
specific decarbonization levers an entity is exposed to.

The adaptive-capacity layer (adaptive_capacity.py) estimates transition capex
TOP-DOWN as a single sector ratio. This module DECOMPOSES that into the
entity's applicable levers so an analyst can see and edit, per lever:

  * current ADOPTION / utilisation           (0-1, how much they already do it)
  * a TARGET adoption by the plan horizon     (0-1, where the plan gets to)
  * the ADDRESSABLE abatement the lever can reach for THIS entity (tCO2/yr)
  * the FORWARD CAPEX to close the adoption gap (USD)  ← the "build for costs"
  * optional ongoing OPEX (USD/yr)
  * capital-planning PHASING (start_year → end_year)

Design discipline
-----------------
By default the per-lever forward capex SEEDS by decomposing the calibrated
top-down total across levers, weighted by (adoption-gap × addressable abatement
× relevance) — so the aggregate is unchanged until the analyst edits it. Every
field is editable; `build_capex_schedule` re-aggregates the edited rows into an
annual capex schedule that replaces the top-down triangular phasing in
`adaptive_capacity.build_strategy` (via `capex_schedule_override`).

This is a planning/reference construct, not an automated optimiser: it seeds
sensible defaults and then gets out of the analyst's way.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from engine.transition.levers import sector_levers, SectorLever

# Share of an emissions base a lever of each global-potential class can address
# for a single entity (screening heuristic; editable per row downstream).
POTENTIAL_WEIGHT = {"high": 0.40, "medium": 0.20, "low": 0.10, "n/a": 0.15}
RELEVANCE_WEIGHT = {"primary": 1.0, "secondary": 0.5}

# Which emissions base a lever's value-chain position abates.
POSITION_BASE = {
    "own_operations": "scope12",
    "upstream": "scope3_up",
    "downstream": "scope3_use",
}

# Default seed adoption levels (editable in the UI).
_ADOPT_NOW_IN_PLAN = 0.40      # already pursuing it (marked in the transition plan)
_ADOPT_NOW_DEFAULT = 0.12      # baseline utilisation otherwise
_BASE_YEAR = 2025

# Capital-intensity weighting of the capex allocation. A lever's marginal abatement cost
# (MAC, $/tCO2) proxies how capital-heavy it is per tonne: a hydrogen-DRI or CCUS plant (high
# positive MAC) needs far more capex per tonne abated than material/energy efficiency
# (near-zero or negative MAC). Without this, cheap high-volume levers (efficiency) soak up most
# of the transition capex — which is wrong: the capital goes into the expensive switch. Maps a
# MAC midpoint to an intensity multiplier (floored so cheap levers still get some capex).
_MAC_INTENSITY_OFFSET = 100.0
_MAC_INTENSITY_SCALE = 250.0
_MAC_INTENSITY_FLOOR = 0.25
_MAC_INTENSITY_CAP = 1.6


@dataclass
class LeverPlanRow:
    """One lever in an entity's capital plan — all fields editable downstream."""
    lever_id: str
    name: str
    domain_label: str
    position: str
    relevance: str
    mac_low: float                     # $/tCO2e (reference, from the library)
    mac_high: float
    addressable_tco2: float            # annual tonnes this lever can abate for the entity
    adoption_now: float                # 0..1
    adoption_target: float             # 0..1
    capex_usd: float                   # forward capex to close the gap
    opex_usd_per_year: float
    start_year: int
    end_year: int

    @property
    def gap(self) -> float:
        return max(0.0, self.adoption_target - self.adoption_now)

    @property
    def abatement_tco2(self) -> float:
        """Annual abatement delivered by closing the adoption gap."""
        return self.addressable_tco2 * self.gap

    def mac_label(self) -> str:
        return f"{self.mac_low:g} to {self.mac_high:g}"


def addressable_abatement(position: str, potential: str,
                          scope12: float, scope3_up: float, scope3_use: float) -> float:
    """Annual tCO2 a lever at this value-chain position can address for the entity."""
    base_key = POSITION_BASE.get(position, "scope12")
    base = {"scope12": scope12, "scope3_up": scope3_up, "scope3_use": scope3_use}.get(base_key, 0.0)
    return POTENTIAL_WEIGHT.get(potential, POTENTIAL_WEIGHT["n/a"]) * max(0.0, base)


def capex_intensity(mac_low: float, mac_high: float) -> float:
    """Capital intensity multiplier for a lever from its MAC range — high-MAC levers
    (H2-DRI, CCUS) are capital-heavy per tonne; low/negative-MAC levers (efficiency) are
    capital-light. Floored so cheap levers still receive some capex."""
    mid = (float(mac_low) + float(mac_high)) / 2.0
    v = (mid + _MAC_INTENSITY_OFFSET) / _MAC_INTENSITY_SCALE
    return max(_MAC_INTENSITY_FLOOR, min(_MAC_INTENSITY_CAP, v))


def _seed_target(relevance: str, ambition: float) -> float:
    """Default target adoption — primary levers pushed harder, scaled by scenario ambition."""
    if relevance == "primary":
        return min(1.0, 0.55 + 0.40 * ambition)
    return min(1.0, 0.35 + 0.35 * ambition)


def default_lever_plan(
    sector: str,
    scope12_tco2: float,
    scope3_up_tco2: float,
    scope3_use_tco2: float,
    total_capex_usd: float,
    ambition: float,
    horizon: List[int],
    in_plan_lever_ids: Optional[List[str]] = None,
    target_year: int = 0,
) -> List[LeverPlanRow]:
    """Seed a per-lever capital plan for an entity's sector.

    `total_capex_usd` is the calibrated top-down transition-capex estimate; it is
    allocated across levers by (gap × addressable abatement × relevance) so the
    rows sum back to it. Everything is a starting point for the analyst to edit.
    """
    in_plan = set(in_plan_lever_ids or [])
    sls: List[SectorLever] = sector_levers(sector)
    if not sls:
        return []

    start = (min(horizon) + 1) if horizon else (_BASE_YEAR + 1)
    end = target_year if target_year and target_year > start else (max(horizon) if horizon else _BASE_YEAR + 15)
    end = max(end, start)

    rows: List[LeverPlanRow] = []
    for sl in sls:
        lv = sl.lever
        now = _ADOPT_NOW_IN_PLAN if lv.id in in_plan else _ADOPT_NOW_DEFAULT
        target = max(now, _seed_target(sl.relevance, ambition))
        mac = (lv.cost_range_usd_per_tco2 + [0.0, 0.0])[:2]
        addr = addressable_abatement(sl.position, lv.mitigation_potential,
                                     scope12_tco2, scope3_up_tco2, scope3_use_tco2)
        rows.append(LeverPlanRow(
            lever_id=lv.id, name=lv.name, domain_label=lv.domain_label,
            position=sl.position, relevance=sl.relevance,
            mac_low=float(mac[0]), mac_high=float(mac[1]),
            addressable_tco2=round(addr, 1),
            adoption_now=now, adoption_target=round(target, 2),
            capex_usd=0.0, opex_usd_per_year=0.0,
            start_year=int(start), end_year=int(end),
        ))

    # Allocate the top-down total by (abatement × relevance × capital-intensity), so the
    # capex concentrates on the capital-heavy switch (DRI/CCUS/electrification) rather than on
    # cheap high-volume levers (efficiency) that address many tonnes for little capital. Fall
    # back to (potential × relevance × gap × intensity) when there is no addressable base.
    def _weight(r: LeverPlanRow) -> float:
        rel = RELEVANCE_WEIGHT.get(r.relevance, 0.5)
        ci = capex_intensity(r.mac_low, r.mac_high)
        w = r.abatement_tco2 * rel * ci
        if w > 0:
            return w
        return POTENTIAL_WEIGHT.get(_pot_of(r, sls), 0.15) * rel * r.gap * ci

    weights = {r.lever_id: _weight(r) for r in rows}
    wsum = sum(weights.values())
    if total_capex_usd > 0 and wsum > 0:
        for r in rows:
            r.capex_usd = round(total_capex_usd * weights[r.lever_id] / wsum, 2)
    return rows


def _pot_of(row: LeverPlanRow, sls: List[SectorLever]) -> str:
    for sl in sls:
        if sl.lever.id == row.lever_id:
            return sl.lever.mitigation_potential
    return "n/a"


def build_capex_schedule(rows: List[LeverPlanRow],
                         horizon: List[int]) -> Dict[int, float]:
    """Aggregate the per-lever forward capex into an annual schedule (USD/year),
    spreading each lever's capex evenly across its start→end window (level
    phasing — transparent for a capital planner). Years are clamped to horizon."""
    sched: Dict[int, float] = {y: 0.0 for y in horizon}
    if not horizon:
        return sched
    lo, hi = min(horizon), max(horizon)
    for r in rows:
        cx = max(0.0, float(r.capex_usd))
        if cx <= 0:
            continue
        s = max(lo, int(r.start_year))
        e = min(hi, int(r.end_year))
        if e < s:
            s = e = max(lo, min(hi, int(r.start_year)))
        n = e - s + 1
        per = cx / n
        for y in range(s, e + 1):
            sched[y] = round(sched.get(y, 0.0) + per, 2)
    return sched


def plan_total_capex(rows: List[LeverPlanRow]) -> float:
    """Sum of forward capex across the plan (the bottom-up transition-capex total)."""
    return round(sum(max(0.0, float(r.capex_usd)) for r in rows), 2)


def plan_total_opex(rows: List[LeverPlanRow]) -> float:
    return round(sum(max(0.0, float(r.opex_usd_per_year)) for r in rows), 2)


def plan_total_abatement(rows: List[LeverPlanRow]) -> float:
    """Annual tCO2 abated at target adoption across the plan (reference)."""
    return round(sum(r.abatement_tco2 for r in rows), 1)
