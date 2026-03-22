"""
PCRAM 2.0 alignment engine — IIGCC Physical Climate Risk Appraisal Methodology.

Provides PCRAM-aligned metrics and workflow tracking for the BSR Climate Risk
Intelligence Platform.  Maps the platform's existing capabilities to PCRAM 2.0's
4-step framework (Scoping → Materiality → Resilience Building → Value Enhancement).

Reference
---------
IIGCC (2025). Physical Climate Risk Appraisal Methodology (PCRAM) 2.0.
https://www.iigcc.org/resources/pcram
"""

import json
import os
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# ---------------------------------------------------------------------------
# EU Taxonomy hazard classification
# ---------------------------------------------------------------------------

_EU_TAX: Optional[dict] = None


def _load_eu_taxonomy() -> dict:
    global _EU_TAX
    if _EU_TAX is None:
        path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "data", "eu_taxonomy_hazards.json")
        )
        with open(path) as f:
            _EU_TAX = json.load(f)
    return _EU_TAX


def classify_hazard(hazard: str) -> Dict[str, str]:
    """
    Return PCRAM / EU Taxonomy classification for a platform hazard.

    Returns dict with keys: type (acute/chronic), eu_category,
    impact_pathway, pcram_impact (list).
    """
    tax = _load_eu_taxonomy()
    mapping = tax.get("platform_hazard_classification", {})
    default = {
        "type": "acute",
        "eu_category": "unknown",
        "impact_pathway": "maintenance_lifecycle",
        "pcram_impact": ["maintenance"],
    }
    return mapping.get(hazard, default)


def get_eu_taxonomy_hazards() -> dict:
    """Return the full EU Taxonomy hazard classification."""
    return _load_eu_taxonomy()


# ---------------------------------------------------------------------------
# PCRAM Step tracking — maps platform pages to PCRAM steps
# ---------------------------------------------------------------------------

PCRAM_STEPS = {
    1: {
        "name": "Scoping & Data Gathering",
        "objective": "Define scope and determine data sufficiency within investment mandate",
        "gate": "A",
        "gate_question": "Are scope boundaries and data sufficiency aligned with investment strategy?",
        "sub_steps": ["1a) Project Initiation", "1b) Project Definition", "1c) Data Gathering & Sufficiency"],
        "platform_pages": ["01_Portfolio", "02_Scenarios", "03_Hazards"],
        "outputs": [
            "Climate hazards identified per asset",
            "Time periods and SSP scenarios selected",
            "Hazard data fetched with provenance tracking",
            "Critical asset components mapped",
        ],
    },
    2: {
        "name": "Materiality Assessment",
        "objective": "Assess physical and financial materiality thresholds",
        "gate": "B",
        "gate_question": "Are physical climate risks material for the asset(s)?",
        "sub_steps": [
            "2a) Exposure to Climate Hazards",
            "2b) Impact Identification",
            "2c) Severity Assessment",
            "2d) KPI Quantification",
        ],
        "platform_pages": ["04_Results", "08_Audit", "09_Vulnerability"],
        "outputs": [
            "Exposure mapping per asset per hazard",
            "Impact severity (EAD, EALR %) quantified",
            "Climate Exposure Scores (1–10)",
            "Acute vs chronic impact classification",
            "Base Case vs Climate Case comparison",
        ],
    },
    3: {
        "name": "Resilience Building",
        "objective": "Identify and evaluate adaptation options and their cost-effectiveness",
        "gate": "C",
        "gate_question": "What are the most effective adaptation options, optimal timing, and responsible parties?",
        "sub_steps": [
            "3a) Identify Adaptation Options",
            "3b) Reassess Materiality",
            "3c) Cost-Benefit Analysis",
            "3d) Adaptation Pathways",
        ],
        "platform_pages": ["06_Adaptation"],
        "outputs": [
            "Ranked adaptation measures with NPV, CBR, IRR",
            "Resilience Case cashflow forecasts",
            "Per-hazard damage reduction quantified",
        ],
    },
    4: {
        "name": "Value Enhancement",
        "objective": "Determine investment case for resilience and optimise risk transfer",
        "gate": "D",
        "gate_question": "How can resilience investment be optimised across the value chain?",
        "sub_steps": [
            "4a) Risk Transfer & Insurability",
            "4b) Investment Case for Resilience",
        ],
        "platform_pages": ["07_DCF", "05_Map", "10_Governance"],
        "outputs": [
            "Climate-adjusted DCF valuation",
            "IRR comparison: Base vs Climate vs Resilience",
            "Stranded asset analysis",
            "Resilience metrics (AAL/NPV, PML/NPV)",
        ],
    },
}


# ---------------------------------------------------------------------------
# PCRAM Materiality — Base Case vs Climate Case vs Resilience Case
# ---------------------------------------------------------------------------

@dataclass
class PCRAMCaseComparison:
    """Comparison of Base Case, Climate Case, and Resilience Case per PCRAM Step 2/3."""
    asset_id: str
    asset_name: str
    asset_value: float
    scenario_id: str
    # Base Case: asset value without climate risk
    base_case_npv: float
    # Climate Case: asset value reduced by climate damages
    climate_case_npv: float
    climate_case_eal: float       # expected annual loss (EAD)
    climate_case_ealr_pct: float  # EALR %
    # Resilience Case: after adaptation
    resilience_case_npv: Optional[float] = None
    resilience_case_eal: Optional[float] = None
    adaptation_capex: Optional[float] = None
    adaptation_net_npv: Optional[float] = None
    # IRR comparison
    base_irr: Optional[float] = None
    climate_irr: Optional[float] = None
    resilience_irr: Optional[float] = None

    @property
    def climate_impact_pct(self) -> float:
        """% impact of climate on asset value."""
        if self.base_case_npv <= 0:
            return 0.0
        return (self.base_case_npv - self.climate_case_npv) / self.base_case_npv * 100

    @property
    def resilience_recovery_pct(self) -> Optional[float]:
        """% of climate impact recovered by adaptation."""
        if self.resilience_case_npv is None or self.climate_impact_pct <= 0:
            return None
        recovered = self.resilience_case_npv - self.climate_case_npv
        lost = self.base_case_npv - self.climate_case_npv
        if lost <= 0:
            return None
        return recovered / lost * 100


def build_case_comparison(
    asset_id: str,
    asset_name: str,
    asset_value: float,
    scenario_id: str,
    annual_ead: float,
    discount_rate: float = 0.035,
    horizon_years: int = 25,
    adaptation_results: Optional[list] = None,
) -> PCRAMCaseComparison:
    """
    Build PCRAM Base/Climate/Resilience case comparison for a single asset.

    Parameters
    ----------
    annual_ead         : Current annual EAD for this asset/scenario
    discount_rate      : Discount rate for NPV
    horizon_years      : Analysis horizon in years
    adaptation_results : Optional list of AdaptationNPVResult objects
    """
    # Base Case NPV: undiscounted asset value (proxy — actual would use cashflow model)
    base_npv = asset_value

    # Climate Case: PV of cumulative damages over horizon
    years = np.arange(1, horizon_years + 1)
    discount_factors = 1.0 / (1.0 + discount_rate) ** years
    pv_damages = float(np.sum(annual_ead * discount_factors))
    climate_npv = asset_value - pv_damages
    ealr_pct = (annual_ead / asset_value * 100) if asset_value > 0 else 0.0

    # Resilience Case (if adaptation results available)
    res_npv = None
    res_eal = None
    adapt_capex = None
    adapt_net_npv = None
    if adaptation_results:
        total_avoided = sum(
            getattr(r, "npv_avoided_damages", 0) for r in adaptation_results
        )
        total_cost = sum(
            getattr(r, "total_cost", 0) for r in adaptation_results
        )
        adapt_capex = sum(
            getattr(r, "capex_total", getattr(r, "capex", 0)) for r in adaptation_results
        )
        res_npv = climate_npv + total_avoided - total_cost
        adapt_net_npv = total_avoided - total_cost

        # Estimate residual annual loss
        total_reduction = sum(
            getattr(r, "damage_reduction_pct", 0) for r in adaptation_results
        )
        effective_reduction = min(total_reduction / 100.0, 0.95)  # cap at 95%
        res_eal = annual_ead * (1.0 - effective_reduction)

    return PCRAMCaseComparison(
        asset_id=asset_id,
        asset_name=asset_name,
        asset_value=asset_value,
        scenario_id=scenario_id,
        base_case_npv=base_npv,
        climate_case_npv=climate_npv,
        climate_case_eal=annual_ead,
        climate_case_ealr_pct=ealr_pct,
        resilience_case_npv=res_npv,
        resilience_case_eal=res_eal,
        adaptation_capex=adapt_capex,
        adaptation_net_npv=adapt_net_npv,
    )


# ---------------------------------------------------------------------------
# PCRAM resilience metrics — AAL, PML, ratios
# ---------------------------------------------------------------------------

def compute_aal(annual_df: pd.DataFrame, asset_id: str,
                scenario_id: Optional[str] = None) -> float:
    """
    Average Annual Loss (AAL) — same as EAD, averaged across all hazards.

    PCRAM uses AAL terminology; this platform uses EAD.  They are equivalent
    for the trapezoidal EP-curve integration used here.
    """
    if annual_df.empty:
        return 0.0
    df = annual_df[annual_df["asset_id"] == asset_id]
    if scenario_id:
        df = df[df["scenario_id"] == scenario_id]
    if df.empty:
        return 0.0
    # Take the latest year available as representative AAL
    latest = df["year"].max()
    return float(df[df["year"] == latest]["ead"].sum())


def compute_pml(annual_df: pd.DataFrame, asset_id: str,
                asset_value: float,
                scenario_id: Optional[str] = None,
                percentile: float = 90.0) -> float:
    """
    Probable Maximum Loss (PML) estimate at a given percentile.

    Approximated from the EP curve: uses the highest return-period EAD
    scaled by asset value.  For true PML you'd need a full loss distribution;
    this is a screening-level proxy.
    """
    if annual_df.empty:
        return 0.0
    df = annual_df[annual_df["asset_id"] == asset_id]
    if scenario_id:
        df = df[df["scenario_id"] == scenario_id]
    if df.empty:
        return 0.0
    # Use max annual EAD across all years as PML proxy
    yearly = df.groupby("year")["ead"].sum()
    if yearly.empty:
        return 0.0
    pml = float(np.percentile(yearly.values, percentile))
    return pml


def compute_pcram_ratios(
    aal: float,
    pml: float,
    asset_value: float,
) -> Dict[str, float]:
    """
    Compute PCRAM resilience metrics as ratios to asset value.

    Returns
    -------
    Dict with:
      aal_npv_ratio : AAL / asset_value (fraction)
      pml_npv_ratio : PML / asset_value (fraction)
      aal_pct       : AAL as % of value
      pml_pct       : PML as % of value
    """
    if asset_value <= 0:
        return {"aal_npv_ratio": 0.0, "pml_npv_ratio": 0.0,
                "aal_pct": 0.0, "pml_pct": 0.0}
    return {
        "aal_npv_ratio": aal / asset_value,
        "pml_npv_ratio": pml / asset_value,
        "aal_pct": aal / asset_value * 100,
        "pml_pct": pml / asset_value * 100,
    }


# ---------------------------------------------------------------------------
# PCRAM Step completion assessment
# ---------------------------------------------------------------------------

def assess_step_completion(session_state: dict) -> Dict[int, Dict[str, Any]]:
    """
    Evaluate which PCRAM steps have been completed based on session state.

    Returns {step_number: {completed: bool, status: str, details: str}}
    """
    results = {}

    # Step 1: Scoping — need assets + scenarios + hazard data
    has_assets = bool(session_state.get("assets"))
    has_scenarios = bool(session_state.get("selected_scenarios"))
    has_hazards = bool(session_state.get("hazard_data"))
    step1_complete = has_assets and has_scenarios and has_hazards
    results[1] = {
        "completed": step1_complete,
        "status": "Complete" if step1_complete else "Incomplete",
        "details": (
            f"Assets: {'Yes' if has_assets else 'No'}, "
            f"Scenarios: {'Yes' if has_scenarios else 'No'}, "
            f"Hazard data: {'Yes' if has_hazards else 'No'}"
        ),
        "gate_passed": step1_complete,
    }

    # Step 2: Materiality — need damage results
    has_results = bool(session_state.get("results"))
    has_annual = session_state.get("annual_damages") is not None
    step2_complete = has_results and has_annual
    results[2] = {
        "completed": step2_complete,
        "status": "Complete" if step2_complete else "Incomplete",
        "details": (
            f"Damage results: {'Yes' if has_results else 'No'}, "
            f"Annual timeline: {'Yes' if has_annual else 'No'}"
        ),
        "gate_passed": step2_complete,
    }

    # Step 3: Resilience Building — adaptation analysis done
    has_adaptation = bool(session_state.get("adaptation_results"))
    results[3] = {
        "completed": has_adaptation,
        "status": "Complete" if has_adaptation else "Not started",
        "details": "Adaptation analysis completed" if has_adaptation else "Run adaptation analysis on page 06",
        "gate_passed": has_adaptation,
    }

    # Step 4: Value Enhancement — DCF analysis done
    has_dcf = bool(session_state.get("dcf_results"))
    results[4] = {
        "completed": has_dcf,
        "status": "Complete" if has_dcf else "Not started",
        "details": "DCF valuation completed" if has_dcf else "Run DCF analysis on page 07",
        "gate_passed": has_dcf,
    }

    return results


# ---------------------------------------------------------------------------
# PCRAM materiality threshold assessment
# ---------------------------------------------------------------------------

# PCRAM Step 2d thresholds — when EAD exceeds these, the hazard is "material"
MATERIALITY_THRESHOLDS = {
    "low":      0.1,   # EALR < 0.1% → Low materiality
    "moderate": 0.5,   # 0.1–0.5% → Moderate
    "high":     1.0,   # 0.5–1.0% → High
    "critical": 2.0,   # > 2.0% → Critical
}


def assess_materiality(ealr_pct: float) -> Dict[str, str]:
    """
    Classify materiality of a hazard exposure per PCRAM Step 2d.

    Parameters
    ----------
    ealr_pct : Expected Annual Loss Ratio as percentage

    Returns
    -------
    Dict with 'level' (Low/Moderate/High/Critical) and 'action'
    """
    if ealr_pct < MATERIALITY_THRESHOLDS["low"]:
        return {
            "level": "Low",
            "color": "#2A9D8F",
            "action": "Monitor — include in risk register; re-assess at next PCRAM cycle",
        }
    elif ealr_pct < MATERIALITY_THRESHOLDS["moderate"]:
        return {
            "level": "Moderate",
            "color": "#E9C46A",
            "action": "Investigate — quantify impacts; assess whether adaptation is warranted",
        }
    elif ealr_pct < MATERIALITY_THRESHOLDS["high"]:
        return {
            "level": "High",
            "color": "#F4721A",
            "action": "Act — proceed to Step 3 (Resilience Building); identify adaptation options",
        }
    else:
        return {
            "level": "Critical",
            "color": "#C94040",
            "action": "Urgent — material financial impact; immediate resilience intervention required",
        }


def portfolio_materiality_summary(
    annual_df: pd.DataFrame,
    assets: list,
    scenario_id: Optional[str] = None,
    year: int = 2050,
) -> pd.DataFrame:
    """
    Generate PCRAM materiality assessment for the portfolio.

    Returns DataFrame with asset/hazard level materiality classifications.
    """
    if annual_df.empty:
        return pd.DataFrame()

    asset_map = {a.id: a for a in assets}
    df = annual_df.copy()
    if scenario_id:
        df = df[df["scenario_id"] == scenario_id]
    df = df[df["year"] == year]

    rows = []
    for _, row in df.iterrows():
        asset = asset_map.get(row["asset_id"])
        if asset is None:
            continue
        val = asset.replacement_value
        ead = float(row.get("ead", 0))
        ealr = (ead / val * 100) if val > 0 else 0.0
        haz = str(row.get("hazard", "unknown"))
        classification = classify_hazard(haz)
        materiality = assess_materiality(ealr)

        rows.append({
            "asset_id": row["asset_id"],
            "asset_name": asset.name,
            "asset_value": val,
            "hazard": haz,
            "hazard_type": classification.get("type", "unknown"),
            "eu_category": classification.get("eu_category", "unknown"),
            "ead": ead,
            "ealr_pct": ealr,
            "materiality": materiality["level"],
            "materiality_color": materiality["color"],
            "pcram_action": materiality["action"],
        })

    return pd.DataFrame(rows)
