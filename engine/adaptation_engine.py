"""
Adaptation measures engine: NPV of avoided EAD, cost-benefit ratio, payback period.
"""

import json
import os
import numpy as np
from typing import List, Dict, Optional
from dataclasses import dataclass

_CATALOG: Optional[dict] = None

_ADAPTATION_ASSET_TYPE_CANDIDATES: Dict[str, tuple[str, ...]] = {
    "residential_high_rise": ("residential_concrete", "commercial_concrete"),
    "commercial_office": ("commercial_steel", "commercial_concrete"),
    "commercial_retail": ("commercial_steel", "commercial_concrete"),
    "commercial_warehouse": ("industrial_steel", "commercial_steel"),
    "industrial_heavy": ("industrial_steel", "commercial_concrete"),
    "healthcare_hospital": ("commercial_concrete", "infrastructure_utility"),
    "education_school": ("residential_masonry", "commercial_concrete"),
    "data_center": ("commercial_concrete", "infrastructure_utility", "industrial_steel"),
    "hotel_resort": ("commercial_concrete", "commercial_steel", "residential_concrete"),
    "mixed_use": ("commercial_concrete", "commercial_steel", "residential_concrete"),
    "infrastructure_bridge": ("infrastructure_road", "infrastructure_utility"),
    "infrastructure_port": ("infrastructure_utility", "infrastructure_road"),
}

_MEASURE_MECHANISM_KEYWORDS = {
    "exposure reduction": ("barrier", "bund", "foundation", "clearance", "permeable", "drainage"),
    "downtime/business interruption reduction": ("backup", "redundancy", "continuity", "suppression"),
    "chronic cost reduction": ("hvac", "heat pump", "insulation", "cool roof", "water recycling", "efficiency"),
}


def _load_catalog() -> dict:
    global _CATALOG
    if _CATALOG is None:
        path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "data", "adaptation_catalog.json")
        )
        with open(path) as f:
            _CATALOG = json.load(f)
    return _CATALOG


def _asset_type_candidates(asset_type: str) -> set[str]:
    candidates = {asset_type}
    candidates.update(_ADAPTATION_ASSET_TYPE_CANDIDATES.get(asset_type, ()))
    return candidates


def list_measures(hazard: Optional[str] = None, asset_type: Optional[str] = None) -> List[dict]:
    """Return adaptation measures, optionally filtered by hazard and/or asset_type."""
    catalog = _load_catalog()
    measures = catalog["measures"]
    if hazard:
        measures = [m for m in measures if m["hazard"] == hazard]
    if asset_type:
        asset_candidates = _asset_type_candidates(asset_type)
        measures = [
            m for m in measures
            if not m.get("applicable_asset_types")
            or bool(asset_candidates.intersection(m["applicable_asset_types"]))
        ]
    return measures


def get_measure(measure_id: str) -> Optional[dict]:
    catalog = _load_catalog()
    for m in catalog["measures"]:
        if m["id"] == measure_id:
            return m
    return None


def classify_measure_mechanism(measure: dict | str) -> str:
    if isinstance(measure, str):
        resolved = get_measure(measure)
        if resolved is None:
            return "vulnerability reduction"
        measure = resolved

    hazard = str(measure.get("hazard", "")).strip().lower()
    text = f"{measure.get('label', '')} {measure.get('description', '')}".lower()

    if hazard in {"heat", "water_stress"}:
        return "chronic cost reduction"

    for label, keywords in _MEASURE_MECHANISM_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return label

    return "vulnerability reduction"


@dataclass
class AdaptationResult:
    measure_id: str
    measure_label: str
    hazard: str
    asset_id: str
    asset_value: float
    capex: float
    npv_opex: float
    total_cost: float
    baseline_ead: float
    adapted_ead: float
    avoided_ead_annual: float
    npv_benefits: float
    cbr: float              # cost-benefit ratio = npv_benefits / total_cost
    payback_years: float
    design_life_years: int
    damage_reduction_pct: float


def calc_adaptation(
    measure_id: str,
    asset_id: str,
    asset_value: float,
    baseline_ead: float,
    discount_rate: float = 0.035,
) -> AdaptationResult:
    """
    Calculate NPV cost-benefit for an adaptation measure on an asset.

    Parameters
    ----------
    measure_id      : ID from adaptation catalog
    asset_id        : asset identifier
    asset_value     : replacement value £/$/€
    baseline_ead    : current/future EAD without adaptation
    discount_rate   : annual discount rate (default 3.5% green finance rate)
    """
    measure = get_measure(measure_id)
    if measure is None:
        raise ValueError(f"Unknown measure: {measure_id}")

    design_life = measure["design_life_years"]
    reduction_pct = measure["damage_reduction_pct"] / 100.0

    capex = asset_value * measure["capex_pct"] / 100.0
    opex_annual = capex * measure["opex_annual_pct"] / 100.0

    avoided_ead = baseline_ead * reduction_pct
    adapted_ead = baseline_ead - avoided_ead

    # NPV of benefits and opex over design life
    years = np.arange(1, design_life + 1)
    discount_factors = 1.0 / (1.0 + discount_rate) ** years

    npv_benefits = float(np.sum(avoided_ead * discount_factors))
    npv_opex = float(np.sum(opex_annual * discount_factors))
    total_cost = capex + npv_opex

    cbr = npv_benefits / total_cost if total_cost > 0 else 0.0
    payback_years = capex / avoided_ead if avoided_ead > 0 else float("inf")

    return AdaptationResult(
        measure_id=measure_id,
        measure_label=measure["label"],
        hazard=measure["hazard"],
        asset_id=asset_id,
        asset_value=asset_value,
        capex=capex,
        npv_opex=npv_opex,
        total_cost=total_cost,
        baseline_ead=baseline_ead,
        adapted_ead=adapted_ead,
        avoided_ead_annual=avoided_ead,
        npv_benefits=npv_benefits,
        cbr=cbr,
        payback_years=payback_years,
        design_life_years=design_life,
        damage_reduction_pct=measure["damage_reduction_pct"],
    )


@dataclass
class AdaptationNPVResult:
    """NPV-based adaptation result using the full annual damage stream."""
    measure_id: str
    measure_label: str
    hazard: str
    asset_id: str
    asset_value: float
    # Costs
    capex_total: float
    npv_opex: float
    total_cost: float
    # Benefits (NPV of avoided damages over the full annual stream)
    npv_baseline_damages: float
    npv_adapted_damages: float
    npv_avoided_damages: float
    # Metrics
    cbr: float
    roi_pct: float
    irr: float
    discounted_payback_year: Optional[int]
    design_life_years: int
    damage_reduction_pct: float
    # Year-by-year cash flow table
    annual_cashflows: list   # list of dicts with year-level detail

    @property
    def net_npv(self) -> float:
        return self.npv_avoided_damages - self.total_cost


@dataclass
class AdaptationBundleResult:
    asset_id: str
    asset_value: float
    measure_rows: list
    annual_cashflows: list
    baseline_total_npv_damages: float
    bundled_total_npv_damages: float
    bundled_npv_avoided_damages: float
    total_cost: float
    cbr: float
    roi_pct: float
    order_sensitive_warning: str


def calc_adaptation_npv(
    measure_id: str,
    asset_id: str,
    asset_value: float,
    annual_eads: Dict[int, float],
    discount_rate: float = 0.035,
    implementation_year: int = 2026,
    capex_phases: Optional[Dict[int, float]] = None,
    opex_override: Optional[float] = None,
    base_year: int = 2025,
) -> AdaptationNPVResult:
    """
    NPV-based adaptation CBA using the full annual EAD stream (2025-2050).

    Parameters
    ----------
    measure_id          : ID from adaptation catalog
    asset_id            : asset identifier
    asset_value         : replacement value
    annual_eads         : {year: ead} — baseline annual EAD from damage model
    discount_rate       : annual discount rate
    implementation_year : year the measure becomes effective
    capex_phases        : optional {year: fraction} for phased capex (fractions sum to 1.0)
                          e.g. {2026: 0.6, 2027: 0.4} for 60/40 split
    opex_override       : override annual opex amount (absolute); if None uses catalog %
    base_year           : PV reference year
    """
    measure = get_measure(measure_id)
    if measure is None:
        raise ValueError(f"Unknown measure: {measure_id}")

    design_life = measure["design_life_years"]
    reduction_pct = measure["damage_reduction_pct"] / 100.0

    capex_total = asset_value * measure["capex_pct"] / 100.0
    opex_annual = opex_override if opex_override is not None else capex_total * measure["opex_annual_pct"] / 100.0

    # Default phasing: 100% in year before implementation
    if capex_phases is None:
        capex_phases = {implementation_year - 1: 1.0}

    # Normalise phases to sum to 1.0
    phase_total = sum(capex_phases.values())
    if phase_total > 0:
        capex_phases = {y: v / phase_total for y, v in capex_phases.items()}

    years_sorted = sorted(annual_eads.keys())
    end_of_life_year = implementation_year + design_life - 1

    rows = []
    cum_net_cf_pv = 0.0
    discounted_payback = None
    npv_baseline = 0.0
    npv_adapted = 0.0
    npv_avoided = 0.0
    npv_cost = 0.0
    irr_cashflows = []  # for IRR: net cash flows per year

    for year in years_sorted:
        t = year - base_year
        df = 1.0 / (1.0 + discount_rate) ** t if t >= 0 else 1.0

        baseline_ead = annual_eads.get(year, 0.0)
        measure_active = implementation_year <= year <= end_of_life_year

        # Avoided damage
        avoided = baseline_ead * reduction_pct if measure_active else 0.0
        adapted_ead = baseline_ead - avoided

        # Capex in this year
        capex_yr = capex_total * capex_phases.get(year, 0.0)

        # Opex in this year
        opex_yr = opex_annual if measure_active else 0.0

        # Net cash flow = avoided damage - costs
        net_cf = avoided - capex_yr - opex_yr
        net_cf_pv = net_cf * df

        cum_net_cf_pv += net_cf_pv

        # Track discounted payback
        if discounted_payback is None and cum_net_cf_pv > 0 and measure_active:
            discounted_payback = year

        npv_baseline += baseline_ead * df
        npv_adapted += adapted_ead * df
        npv_avoided += avoided * df
        npv_cost += (capex_yr + opex_yr) * df
        irr_cashflows.append(net_cf)

        rows.append({
            "year": year,
            "baseline_ead": round(baseline_ead, 2),
            "measure_active": measure_active,
            "avoided_damage": round(avoided, 2),
            "adapted_ead": round(adapted_ead, 2),
            "capex": round(capex_yr, 2),
            "opex": round(opex_yr, 2),
            "net_cashflow": round(net_cf, 2),
            "discount_factor": round(df, 6),
            "net_cashflow_pv": round(net_cf_pv, 2),
            "cumulative_npv": round(cum_net_cf_pv, 2),
        })

    total_cost = npv_cost
    cbr = npv_avoided / total_cost if total_cost > 0 else 0.0
    roi_pct = (npv_avoided - total_cost) / total_cost * 100 if total_cost > 0 else 0.0

    # IRR via numpy
    try:
        irr = _calc_irr(irr_cashflows)
    except Exception:
        irr = float("nan")

    return AdaptationNPVResult(
        measure_id=measure_id,
        measure_label=measure["label"],
        hazard=measure["hazard"],
        asset_id=asset_id,
        asset_value=asset_value,
        capex_total=capex_total,
        npv_opex=npv_cost - sum(capex_total * capex_phases.get(y, 0.0) * (1.0 / (1.0 + discount_rate) ** (y - base_year)) for y in years_sorted),
        total_cost=total_cost,
        npv_baseline_damages=npv_baseline,
        npv_adapted_damages=npv_adapted,
        npv_avoided_damages=npv_avoided,
        cbr=cbr,
        roi_pct=roi_pct,
        irr=irr,
        discounted_payback_year=discounted_payback,
        design_life_years=design_life,
        damage_reduction_pct=measure["damage_reduction_pct"],
        annual_cashflows=rows,
    )


def _stream_years(*streams: Dict[int, float]) -> list[int]:
    years: set[int] = set()
    for stream in streams:
        years.update(int(year) for year in stream.keys())
    return sorted(years)


def _copy_stream(stream: Dict[int, float], years: list[int]) -> Dict[int, float]:
    return {int(year): float(stream.get(year, 0.0)) for year in years}


def _apply_measure_to_stream(
    measure: dict,
    annual_eads: Dict[int, float],
    *,
    implementation_year: int,
) -> tuple[Dict[int, float], Dict[int, float]]:
    years = sorted(int(year) for year in annual_eads.keys())
    design_life = int(measure["design_life_years"])
    reduction_pct = float(measure["damage_reduction_pct"]) / 100.0
    end_of_life_year = implementation_year + design_life - 1

    residual = {}
    avoided = {}
    for year in years:
        baseline = float(annual_eads.get(year, 0.0))
        active = implementation_year <= year <= end_of_life_year
        avoided_amount = baseline * reduction_pct if active else 0.0
        residual[year] = max(baseline - avoided_amount, 0.0)
        avoided[year] = avoided_amount
    return residual, avoided


def calc_adaptation_bundle_npv(
    measure_ids: List[str],
    asset_id: str,
    asset_value: float,
    total_annual_eads: Dict[int, float],
    hazard_annual_eads: Dict[str, Dict[int, float]],
    discount_rate: float = 0.035,
    implementation_year: int = 2026,
    capex_phases: Optional[Dict[int, float]] = None,
    opex_override: Optional[float] = None,
    base_year: int = 2025,
) -> AdaptationBundleResult:
    """
    Sequence selected measures on residual hazard risk rather than summing
    standalone savings from the original baseline.
    """
    ordered_measure_ids = [mid for mid in measure_ids if get_measure(mid) is not None]
    years = _stream_years(total_annual_eads, *hazard_annual_eads.values())
    total_stream = _copy_stream(total_annual_eads, years)
    hazard_baselines = {
        hazard: _copy_stream(stream, years)
        for hazard, stream in (hazard_annual_eads or {}).items()
    }
    residual_hazard_streams = {
        hazard: dict(stream)
        for hazard, stream in hazard_baselines.items()
    }

    targeted_hazards = {
        get_measure(mid)["hazard"]
        for mid in ordered_measure_ids
        if get_measure(mid) is not None and get_measure(mid)["hazard"] in hazard_baselines
    }
    unaffected_stream = {
        year: max(
            0.0,
            total_stream.get(year, 0.0) - sum(hazard_baselines.get(hazard, {}).get(year, 0.0) for hazard in targeted_hazards),
        )
        for year in years
    }

    measure_rows = []
    combined_cashflows: dict[int, dict] = {}
    total_cost = 0.0

    for order, measure_id in enumerate(ordered_measure_ids, start=1):
        measure = get_measure(measure_id)
        if measure is None:
            continue
        hazard = measure["hazard"]
        mechanism = classify_measure_mechanism(measure)
        baseline_stream = hazard_baselines.get(hazard, total_stream)
        residual_stream = residual_hazard_streams.get(hazard, _copy_stream(total_stream, years))

        standalone = calc_adaptation_npv(
            measure_id,
            asset_id,
            asset_value,
            baseline_stream,
            discount_rate,
            implementation_year=implementation_year,
            capex_phases=capex_phases,
            opex_override=opex_override,
            base_year=base_year,
        )
        incremental = calc_adaptation_npv(
            measure_id,
            asset_id,
            asset_value,
            residual_stream,
            discount_rate,
            implementation_year=implementation_year,
            capex_phases=capex_phases,
            opex_override=opex_override,
            base_year=base_year,
        )

        next_residual_stream, _ = _apply_measure_to_stream(
            measure,
            residual_stream,
            implementation_year=implementation_year,
        )
        residual_hazard_streams[hazard] = next_residual_stream

        total_cost += incremental.total_cost
        for row in incremental.annual_cashflows:
            year = int(row["year"])
            combined = combined_cashflows.setdefault(
                year,
                {
                    "year": year,
                    "capex": 0.0,
                    "opex": 0.0,
                    "net_cashflow": 0.0,
                    "net_cashflow_pv": 0.0,
                },
            )
            combined["capex"] += float(row["capex"])
            combined["opex"] += float(row["opex"])
            combined["net_cashflow"] += float(row["net_cashflow"])
            combined["net_cashflow_pv"] += float(row["net_cashflow_pv"])

        measure_rows.append(
            {
                "sequence_order": order,
                "measure_id": measure_id,
                "measure": measure["label"],
                "hazard": hazard,
                "mechanism": mechanism,
                "standalone_npv_avoided": standalone.npv_avoided_damages,
                "incremental_npv_avoided": incremental.npv_avoided_damages,
                "standalone_net_npv": standalone.net_npv,
                "incremental_net_npv": incremental.net_npv,
                "standalone_cbr": standalone.cbr,
                "incremental_cbr": incremental.cbr,
                "design_life_years": incremental.design_life_years,
            }
        )

    bundled_total_stream = {}
    for year in years:
        bundled_total_stream[year] = unaffected_stream.get(year, 0.0) + sum(
            residual_hazard_streams.get(hazard, {}).get(year, 0.0)
            for hazard in targeted_hazards
        )

    baseline_total_npv_damages = sum(
        total_stream.get(year, 0.0) / (1.0 + discount_rate) ** (year - base_year)
        for year in years
    )
    bundled_total_npv_damages = sum(
        bundled_total_stream.get(year, 0.0) / (1.0 + discount_rate) ** (year - base_year)
        for year in years
    )
    bundled_npv_avoided_damages = baseline_total_npv_damages - bundled_total_npv_damages
    cbr = bundled_npv_avoided_damages / total_cost if total_cost > 0 else 0.0
    roi_pct = (
        (bundled_npv_avoided_damages - total_cost) / total_cost * 100.0
        if total_cost > 0
        else 0.0
    )

    annual_cashflows = []
    cumulative_npv = 0.0
    for year in years:
        avoided_damage = total_stream.get(year, 0.0) - bundled_total_stream.get(year, 0.0)
        cash = combined_cashflows.get(year, {"capex": 0.0, "opex": 0.0, "net_cashflow": avoided_damage, "net_cashflow_pv": 0.0})
        cumulative_npv += float(cash.get("net_cashflow_pv", 0.0))
        annual_cashflows.append(
            {
                "year": year,
                "baseline_ead": round(total_stream.get(year, 0.0), 2),
                "avoided_damage": round(avoided_damage, 2),
                "adapted_ead": round(bundled_total_stream.get(year, 0.0), 2),
                "capex": round(float(cash.get("capex", 0.0)), 2),
                "opex": round(float(cash.get("opex", 0.0)), 2),
                "net_cashflow": round(float(cash.get("net_cashflow", 0.0)), 2),
                "net_cashflow_pv": round(float(cash.get("net_cashflow_pv", 0.0)), 2),
                "cumulative_npv": round(cumulative_npv, 2),
            }
        )

    warning = (
        "Bundled results sequence measures on residual hazard risk in the selected order. "
        "Cross-hazard interactions and order sensitivity are still approximate."
    )
    return AdaptationBundleResult(
        asset_id=asset_id,
        asset_value=asset_value,
        measure_rows=measure_rows,
        annual_cashflows=annual_cashflows,
        baseline_total_npv_damages=baseline_total_npv_damages,
        bundled_total_npv_damages=bundled_total_npv_damages,
        bundled_npv_avoided_damages=bundled_npv_avoided_damages,
        total_cost=total_cost,
        cbr=cbr,
        roi_pct=roi_pct,
        order_sensitive_warning=warning,
    )


def _calc_irr(cashflows: list, tol: float = 1e-6, max_iter: int = 200) -> float:
    """Newton-Raphson IRR solver (np.irr was removed in NumPy 1.20)."""
    cf = np.array(cashflows, dtype=float)
    if len(cf) < 2 or np.all(cf == 0):
        return float("nan")
    # Try multiple initial guesses to handle different cash flow profiles
    for r0 in [0.1, 0.0, -0.05, 0.5]:
        r = r0
        converged = False
        for _ in range(max_iter):
            t = np.arange(len(cf))
            try:
                pv = cf / (1 + r) ** t
            except (ZeroDivisionError, FloatingPointError):
                break
            npv = pv.sum()
            dpv = -(t * cf / (1 + r) ** (t + 1)).sum()
            if abs(dpv) < 1e-14:
                break
            r_new = r - npv / dpv
            if abs(r_new - r) < tol:
                converged = True
                r = r_new
                break
            r = r_new
        if converged:
            return r
    return float("nan")


def portfolio_adaptation_frontier(
    adaptation_results: List[AdaptationResult],
) -> List[dict]:
    """
    Build a cost-vs-risk-reduction frontier for portfolio-level adaptation.
    Sorts measures by CBR descending, computes cumulative cost and risk reduction.
    """
    sorted_results = sorted(adaptation_results, key=lambda r: r.cbr, reverse=True)
    cumulative_cost = 0.0
    cumulative_avoided_ead = 0.0
    frontier = []
    for r in sorted_results:
        cumulative_cost += r.capex
        cumulative_avoided_ead += r.avoided_ead_annual
        frontier.append({
            "measure_id": r.measure_id,
            "measure_label": r.measure_label,
            "asset_id": r.asset_id,
            "capex": r.capex,
            "cbr": r.cbr,
            "cumulative_capex": cumulative_cost,
            "cumulative_avoided_ead_annual": cumulative_avoided_ead,
        })
    return frontier


def portfolio_adaptation_frontier_npv(
    adaptation_results: List[AdaptationNPVResult],
) -> List[dict]:
    """
    NPV-based standalone measure ranking. Sorts by CBR descending.
    """
    sorted_results = sorted(adaptation_results, key=lambda r: r.cbr, reverse=True)
    cumulative_cost = 0.0
    cumulative_npv_avoided = 0.0
    frontier = []
    for r in sorted_results:
        cumulative_cost += r.capex_total
        cumulative_npv_avoided += r.npv_avoided_damages
        frontier.append({
            "measure_id": r.measure_id,
            "measure_label": r.measure_label,
            "asset_id": r.asset_id,
            "capex": r.capex_total,
            "cbr": r.cbr,
            "roi_pct": r.roi_pct,
            "npv_avoided": r.npv_avoided_damages,
            "net_npv": r.net_npv,
            "cumulative_capex": cumulative_cost,
            "cumulative_npv_avoided": cumulative_npv_avoided,
        })
    return frontier
