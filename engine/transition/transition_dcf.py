"""
Combined Climate-Adjusted DCF (Physical + Transition).

This module composes:
  - engine.dcf_engine.compute_climate_dcf  (physical layer)
  - engine.transition.transition_engine    (transition layer)

Non-duplication
---------------
Physical damages and transition costs flow only through CASH FLOWS in this
combined view. WACC is augmented only if Layer 4 (CCExposure) is routed to
ROUTE_WACC at the orchestrator layer; in that case the financing premium is
added once to wacc and not also reflected in CFs.

Stranded-asset impairment from Layer 2 is reported separately (annual_impairment)
and does not feed the cash-flow stream — consistent with the BSR framework's
distinction between operating-cost adjustments and balance-sheet impairment.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
import pandas as pd

from engine.dcf_engine import DCFInputs, DCFResult, compute_climate_dcf
from engine.transition.transition_engine import (
    TransitionAssetResult,
    transition_results_to_damage_df,
)


@dataclass
class CombinedDCFResult:
    scenario_id: str
    physical_dcf: DCFResult
    combined_dcf: DCFResult           # physical + transition damages combined
    transition_only_dcf: DCFResult    # transition damages only (for attribution)
    total_pv_transition_costs: float
    total_pv_physical_costs: float
    total_pv_stranded_impairment: float
    wacc_premium_bps: float


def compute_combined_dcf(
    inputs: DCFInputs,
    physical_damages_df: pd.DataFrame,
    transition_results: List[TransitionAssetResult],
    scenario_id: str,
    adaptation_savings_df: Optional[pd.DataFrame] = None,
    total_adaptation_capex: float = 0.0,
) -> CombinedDCFResult:
    """
    Compute three DCFs side-by-side and return the comparison:
      1. Physical-only (existing dcf_engine path)
      2. Transition-only (using transition_engine output as the damage stream)
      3. Combined (physical_damages + transition_costs)
    """
    # 1. Physical-only DCF
    phys = compute_climate_dcf(
        inputs=inputs,
        annual_damages_df=physical_damages_df,
        scenario_id=scenario_id,
        adaptation_savings_df=adaptation_savings_df,
        total_adaptation_capex=total_adaptation_capex,
    )

    # Layer-4 financing premium (already capital-structure-weighted in the
    # orchestrator) is applied to the discount rate for the transition and combined
    # DCFs by ADDING it to climate_risk_premium. Physical-only keeps the base WACC.
    wacc_bps = 0.0
    if transition_results:
        wacc_bps = sum(tr.wacc_premium_bps for tr in transition_results) / len(transition_results)
    from dataclasses import replace as _dc_replace
    inputs_l4 = _dc_replace(inputs, climate_risk_premium=inputs.climate_risk_premium + wacc_bps / 10_000.0)

    # 2. Transition-only DCF (discount rate augmented by the L4 financing premium)
    trans_df = transition_results_to_damage_df({scenario_id: transition_results})
    if trans_df.empty:
        trans_df = pd.DataFrame({"year": [inputs.base_year], "ead": [0.0], "scenario_id": [scenario_id]})
    trans = compute_climate_dcf(
        inputs=inputs_l4,
        annual_damages_df=trans_df,
        scenario_id=scenario_id,
    )

    # 3. Combined: sum physical + transition damages by year
    phys_part = physical_damages_df[physical_damages_df["scenario_id"] == scenario_id][["year", "ead"]].copy() \
        if not physical_damages_df.empty else pd.DataFrame(columns=["year", "ead"])
    trans_part = trans_df[trans_df["scenario_id"] == scenario_id][["year", "ead"]].copy()

    _parts = [p for p in (phys_part, trans_part) if not p.empty]
    if not _parts:
        combined_part = pd.DataFrame(columns=["year", "ead"])
    else:
        combined_part = pd.concat(_parts, ignore_index=True)
        combined_part = combined_part.groupby("year", as_index=False)["ead"].sum()
    combined_part["scenario_id"] = scenario_id

    combined = compute_climate_dcf(
        inputs=inputs_l4,
        annual_damages_df=combined_part,
        scenario_id=scenario_id,
        adaptation_savings_df=adaptation_savings_df,
        total_adaptation_capex=total_adaptation_capex,
    )

    # Stranded-asset PV impairment (not in CFs; reported separately). Uses the same
    # end-of-year discount convention (y − base_year + 1) as compute_climate_dcf, so
    # every transition PV in the app shares one timing convention.
    pv_strand = 0.0
    discount = (1.0 + inputs_l4.wacc + inputs_l4.climate_risk_premium)
    for tr in transition_results:
        for y, imp in tr.annual_impairment_usd.items():
            t = max(0, y - inputs.base_year + 1)
            pv_strand += imp / (discount ** t)

    return CombinedDCFResult(
        scenario_id=scenario_id,
        physical_dcf=phys,
        combined_dcf=combined,
        transition_only_dcf=trans,
        total_pv_transition_costs=round(trans.total_pv_damages, 2),
        total_pv_physical_costs=round(phys.total_pv_damages, 2),
        total_pv_stranded_impairment=round(pv_strand, 2),
        wacc_premium_bps=round(wacc_bps, 2),
    )
