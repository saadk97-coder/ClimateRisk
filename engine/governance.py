"""
Shared governance and lineage helpers for assurance-oriented platform controls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import os
import platform
import sys
from typing import Iterable, Optional

import pandas as pd

from engine.data_sources import DATA_SOURCE_REGISTRY
from engine.hazard_math import DEFAULT_DISPLAY_RETURN_PERIOD_MAX

PLATFORM_NAME = "BSR Climate Risk Intelligence Platform"
METHODOLOGY_VERSION = "2026.03-assurance"
MODEL_SCOPE = "Screening-level physical climate risk quantification"
BASELINE_METHOD = (
    "Historical baseline hazard intensities are fetched from ISIMIP3b where available. "
    "Coastal flood uses the coastal baseline pathway, wind can be amplified by IBTrACS basin "
    "exposure, water stress uses WRI Aqueduct, and all other gaps fall back to the built-in "
    "regional baseline. Forward-looking change is applied through scenario multipliers."
)
RESULTS_POSITIONING = (
    "Outputs are suitable for portfolio screening, prioritisation, and analyst challenge. "
    "They are not a substitute for site-specific engineering studies, hydraulic modelling, "
    "or insurer catastrophe models."
)
DCF_POSITIONING = (
    "The DCF module is a scenario-testing and impairment-screening tool. Replacement-value mode "
    "is a screening proxy, not a valuation-grade cash flow model."
)
ACTIVE_BASELINE_SOURCE_KEYS = (
    "isimip3b",
    "coastal_slr_baseline",
    "ibtracs_cyclone",
    "aqueduct",
    "fallback_baseline",
)
INACTIVE_BASELINE_SOURCE_KEYS = (
    "nasa_nex_gddp_cmip6",
    "chelsa_cmip6",
    "loca2",
    "climatena_adaptwest",
)
VULNERABILITY_LIBRARY_NOTE = (
    "Built-in vulnerability curves are mapped to asset types through alias resolution where "
    "the catalogue extends beyond the base JSON curve keys."
)
PRIVACY_DISCLOSURE = (
    "Exact asset coordinates may be sent to external providers during geocoding, hazard refresh, "
    "and optional map overlays. Current provider-touching surfaces include BigDataCloud, "
    "OpenTopoData, ISIMIP3b, WRI Aqueduct, Overpass, and IBTrACS-derived utilities."
)
DEGRADED_MODE_DISCLOSURE = (
    "When a provider refresh fails or a hazard falls back to the built-in regional baseline, "
    "the run should be treated as degraded screening output rather than full baseline coverage."
)
TAIL_UNCERTAINTY_DISCLOSURE = (
    "Conditional GEV parameter bands are generated on demand from bootstrap refits around the "
    "fitted GEV. They do not represent total climate uncertainty."
)
PORTFOLIO_DEPENDENCE_DISCLOSURE = (
    "Portfolio dependence diagnostics use hazard-specific distance-decay screening correlations. "
    "Cross-hazard dependence is not modelled explicitly."
)
ADAPTATION_BUNDLE_DISCLOSURE = (
    "Adaptation bundles are sequenced on residual hazard loss in the selected order. Cross-hazard "
    "interactions remain approximate."
)
FETCH_PROFILE_NOTES = {
    "balanced": (
        "Balanced uses the 2-GCM ISIMIP acute-hazard path for flood, heat, and wind. "
        "Wildfire remains on the screening fallback baseline unless Full is selected."
    ),
    "full": (
        "Full uses the 4-GCM ISIMIP acute-hazard path and the full ISIMIP wildfire pipeline "
        "before fallback baseline is used."
    ),
}
GEV_ELIGIBLE_HAZARDS = {"flood", "heat", "wind", "wildfire"}
GEV_STATUS_VALUES = {"deferred", "generated", "unavailable", "failed"}


def current_operator() -> str:
    """Best-effort operator name for manual overrides and exports."""
    for key in ("USERNAME", "USER", "LOGNAME", "COMPUTERNAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return "unknown_operator"


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def requirements_fingerprint(root: str | Path | None = None) -> str:
    base = Path(root) if root else Path(__file__).resolve().parents[1]
    req_path = base / "requirements.txt"
    if not req_path.exists():
        return "unavailable"
    digest = hashlib.sha256(req_path.read_bytes()).hexdigest()
    return digest[:12]


def active_source_names(source_keys: Iterable[str]) -> str:
    names = []
    for key in source_keys:
        info = DATA_SOURCE_REGISTRY.get(key, {})
        names.append(info.get("name", key))
    return ", ".join(names)


def source_status_rows() -> list[dict]:
    rows: list[dict] = []
    for key in ACTIVE_BASELINE_SOURCE_KEYS:
        info = DATA_SOURCE_REGISTRY.get(key, {})
        rows.append(
            {
                "Source key": key,
                "Source": info.get("name", key),
                "Status": "Active in baseline path",
                "Coverage": info.get("coverage", "Global or hazard-specific"),
                "Notes": info.get("description", ""),
            }
        )
    for key in INACTIVE_BASELINE_SOURCE_KEYS:
        info = DATA_SOURCE_REGISTRY.get(key, {})
        rows.append(
            {
                "Source key": key,
                "Source": info.get("name", key),
                "Status": "Catalogued only",
                "Coverage": info.get("coverage", "Global or hazard-specific"),
                "Notes": (
                    "Retained in the registry for future extensions. Not used in the "
                    "automatic historical-baseline path in this release."
                ),
            }
        )
    return rows


def runtime_metadata(root: str | Path | None = None) -> dict[str, str]:
    return {
        "Methodology version": METHODOLOGY_VERSION,
        "Model scope": MODEL_SCOPE,
        "Baseline method": BASELINE_METHOD,
        "Results positioning": RESULTS_POSITIONING,
        "Active baseline sources": active_source_names(ACTIVE_BASELINE_SOURCE_KEYS),
        "Registry-only sources": active_source_names(INACTIVE_BASELINE_SOURCE_KEYS),
        "Requirements fingerprint": requirements_fingerprint(root),
        "Python": sys.version.split()[0],
        "Platform": platform.platform(),
    }


def override_records(hazard_overrides: dict, assets: Iterable) -> list[dict]:
    asset_map = {
        getattr(asset, "id", ""): getattr(asset, "name", getattr(asset, "id", ""))
        for asset in assets
    }
    rows: list[dict] = []
    for asset_id, hazard_map in (hazard_overrides or {}).items():
        for hazard, details in hazard_map.items():
            rows.append(
                {
                    "Asset ID": asset_id,
                    "Asset Name": asset_map.get(asset_id, asset_id),
                    "Hazard": hazard,
                    "Override basis": details.get("override_basis", ""),
                    "Source / justification": details.get("source_note", ""),
                    "Prepared by": details.get("override_user", ""),
                    "Prepared at (UTC)": details.get("override_timestamp_utc", ""),
                    "Replaces source": details.get("replaces_source", ""),
                    "Return periods": ", ".join(
                        str(int(rp)) if float(rp).is_integer() else str(rp)
                        for rp in details.get("return_periods", [])
                    ),
                    "Override intensities": ", ".join(
                        f"{float(val):.4f}" for val in details.get("intensities", [])
                    ),
                }
            )
    return rows


def _source_name(source_key: str) -> str:
    if source_key == "manual_override":
        return "Manual override"
    return DATA_SOURCE_REGISTRY.get(source_key, {}).get("name", source_key)


def _scenario_labels(selected_scenarios: Iterable[str]) -> list[str]:
    try:
        from engine.scenario_model import SCENARIOS
    except Exception:
        return [str(scenario_id) for scenario_id in selected_scenarios or []]
    return [
        SCENARIOS.get(scenario_id, {}).get("label", str(scenario_id))
        for scenario_id in selected_scenarios or []
    ]


def build_run_manifest(
    *,
    annual_damages_df: Optional[pd.DataFrame],
    selected_scenarios: Iterable[str],
    years: Iterable[int],
    currency_code: str,
    currency_symbol: str,
    discount_rate: float,
    fetch_profile: str,
    override_records: Optional[list[dict]] = None,
    fetch_failures: Optional[list[str]] = None,
    reused_assets: int = 0,
    refreshed_assets: int = 0,
    zone_overrides: Optional[dict] = None,
    hazard_data_all: Optional[dict] = None,
) -> dict:
    annual_damages_df = annual_damages_df.copy() if annual_damages_df is not None else pd.DataFrame()
    override_records = override_records or []
    fetch_failures = fetch_failures or []
    zone_overrides = zone_overrides or {}
    hazard_data_all = hazard_data_all or {}

    override_lookup = {
        (row.get("Asset ID", ""), row.get("Hazard", "")): row
        for row in override_records
    }
    provenance_rows: list[dict] = []
    if not annual_damages_df.empty and {
        "asset_id",
        "asset_name",
        "hazard",
        "data_source",
    }.issubset(annual_damages_df.columns):
        unique_rows = (
            annual_damages_df[
                ["asset_id", "asset_name", "hazard", "data_source"]
            ]
            .drop_duplicates()
            .sort_values(["asset_name", "hazard", "data_source"])
        )
        for row in unique_rows.itertuples(index=False):
            asset_id = str(row.asset_id)
            hazard = str(row.hazard)
            source_key = str(row.data_source or "unknown")
            override = override_lookup.get((asset_id, hazard))
            replaced_source = override.get("Replaces source", "") if override else ""
            fallback_used = source_key == "fallback_baseline" or replaced_source == "fallback_baseline"
            provenance_rows.append(
                {
                    "Asset ID": asset_id,
                    "Asset Name": str(row.asset_name),
                    "Hazard": hazard,
                    "Source key": source_key,
                    "Source": _source_name(source_key),
                    "Fallback used": "Yes" if fallback_used else "No",
                    "Manual override": "Yes" if override else "No",
                    "Override replaces source": replaced_source,
                    "Fetch profile": fetch_profile,
                }
            )

    fallback_count = sum(row["Fallback used"] == "Yes" for row in provenance_rows)
    override_count = sum(row["Manual override"] == "Yes" for row in provenance_rows)
    provider_events: list[dict] = []
    for failure in fetch_failures:
        provider_events.append(
            {
                "Event type": "Provider refresh failure",
                "Severity": "warning",
                "Detail": str(failure),
            }
        )
    if fallback_count:
        provider_events.append(
            {
                "Event type": "Fallback baseline used",
                "Severity": "info",
                "Detail": f"{fallback_count} asset-hazard pair(s) used the built-in regional fallback baseline.",
            }
        )
    if override_count:
        provider_events.append(
            {
                "Event type": "Manual overrides applied",
                "Severity": "info",
                "Detail": f"{override_count} asset-hazard pair(s) used analyst-entered hazard overrides.",
            }
        )
    if zone_overrides:
        provider_events.append(
            {
                "Event type": "Preview-only zone overrides",
                "Severity": "info",
                "Detail": (
                    f"{len(zone_overrides)} zone override(s) are stored in session state for Hazards-page preview only "
                    "and do not change Results runs."
                ),
            }
        )

    asset_name_lookup: dict[str, str] = {}
    if not annual_damages_df.empty and {"asset_id", "asset_name"}.issubset(annual_damages_df.columns):
        asset_name_lookup = {
            str(row.asset_id): str(row.asset_name)
            for row in annual_damages_df[["asset_id", "asset_name"]].drop_duplicates().itertuples(index=False)
        }

    gev_status_rows: list[dict] = []
    for asset_id, hazard_map in hazard_data_all.items():
        for hazard, hazard_data in (hazard_map or {}).items():
            hazard_data = hazard_data or {}
            uncertainty = dict(hazard_data.get("uncertainty", {}) or {})
            explicit_status = str(hazard_data.get("uncertainty_status", "")).strip().lower()
            if (
                hazard not in GEV_ELIGIBLE_HAZARDS
                and uncertainty.get("type") != "gev_parameter_uncertainty"
                and explicit_status not in GEV_STATUS_VALUES
                and not hazard_data.get("gev_basis")
            ):
                continue

            if uncertainty.get("type") == "gev_parameter_uncertainty":
                status = "generated"
            elif explicit_status in GEV_STATUS_VALUES:
                status = explicit_status
            elif hazard_data.get("source") == "isimip3b" and hazard_data.get("gev_basis"):
                status = "deferred"
            else:
                status = "unavailable"

            if status == "generated":
                detail = (
                    hazard_data.get("uncertainty_detail")
                    or "Conditional GEV parameter bands were generated for this asset-hazard pair."
                )
            elif status == "deferred":
                detail = (
                    hazard_data.get("uncertainty_detail")
                    or "Conditional GEV parameter bands are available on demand and were not generated in the standard run."
                )
            elif status == "failed":
                detail = (
                    hazard_data.get("uncertainty_error")
                    or hazard_data.get("uncertainty_detail")
                    or "Conditional GEV parameter bands could not be generated from cached basis."
                )
            else:
                detail = (
                    hazard_data.get("uncertainty_detail")
                    or "Conditional GEV parameter bands are unavailable for this hazard-source path."
                )

            gev_status_rows.append(
                {
                    "Asset ID": str(asset_id),
                    "Asset Name": asset_name_lookup.get(str(asset_id), ""),
                    "Hazard": str(hazard),
                    "Source key": str(hazard_data.get("source", "")),
                    "Source": _source_name(str(hazard_data.get("source", ""))),
                    "GEV diagnostics status": status,
                    "Detail": detail,
                }
            )

    gev_generated_count = sum(row["GEV diagnostics status"] == "generated" for row in gev_status_rows)
    gev_deferred_count = sum(row["GEV diagnostics status"] == "deferred" for row in gev_status_rows)
    gev_unavailable_count = sum(row["GEV diagnostics status"] == "unavailable" for row in gev_status_rows)
    gev_failed_count = sum(row["GEV diagnostics status"] == "failed" for row in gev_status_rows)

    gev_rows: list[dict] = []
    for asset_id, hazard_map in hazard_data_all.items():
        for hazard, hazard_data in (hazard_map or {}).items():
            uncertainty = (hazard_data or {}).get("uncertainty", {})
            if uncertainty.get("type") != "gev_parameter_uncertainty":
                continue
            asset_name = asset_name_lookup.get(str(asset_id), "")
            for rp, central, lower, upper in zip(
                uncertainty.get("return_periods", []),
                uncertainty.get("central", []),
                uncertainty.get("lower", []),
                uncertainty.get("upper", []),
            ):
                display_cap = int(uncertainty.get("display_return_period_max", DEFAULT_DISPLAY_RETURN_PERIOD_MAX))
                gev_rows.append(
                    {
                        "Asset ID": asset_id,
                        "Asset Name": asset_name,
                        "Hazard": hazard,
                        "Return period (yr)": rp,
                        "Tail view": (
                            "Advanced high-uncertainty tail"
                            if float(rp) > float(display_cap)
                            else "Standard analyst view"
                        ),
                        "Central": central,
                        "Lower band": lower,
                        "Upper band": upper,
                        "Band label": uncertainty.get("band_label", ""),
                        "Sample years": uncertainty.get("sample_years", 0),
                        "Bootstrap draws": uncertainty.get("bootstrap_draws", 0),
                        "GCM count": uncertainty.get("gcm_count", 0),
                        "Conditional note": uncertainty.get("limitation", ""),
                    }
                )

    year_list = [int(year) for year in years or []]
    return {
        "Manifest version": "1",
        "Run timestamp (UTC)": utc_now_iso(),
        "Methodology version": METHODOLOGY_VERSION,
        "Selected scenarios": list(selected_scenarios or []),
        "Selected scenario labels": _scenario_labels(selected_scenarios),
        "Analysis years": year_list,
        "Analysis window": f"{min(year_list)}-{max(year_list)} annual" if year_list else "",
        "Currency": currency_code,
        "Currency symbol": currency_symbol,
        "Discount rate": discount_rate,
        "Fetch profile": fetch_profile,
        "Fetch profile note": FETCH_PROFILE_NOTES.get(fetch_profile, ""),
        "Source selection mode": "Automatic",
        "Zone override mode": "Preview only",
        "Zone override count": len(zone_overrides),
        "Manual override records": len(override_records),
        "Refreshed assets": refreshed_assets,
        "Reused cached assets": reused_assets,
        "Provider failure count": len(fetch_failures),
        "Fallback asset-hazard pairs": fallback_count,
        "Privacy disclosure": PRIVACY_DISCLOSURE,
        "Degraded mode disclosure": DEGRADED_MODE_DISCLOSURE,
        "Tail uncertainty disclosure": TAIL_UNCERTAINTY_DISCLOSURE,
        "GEV diagnostics mode": "On-demand",
        "GEV generated asset-hazard pairs": gev_generated_count,
        "GEV deferred asset-hazard pairs": gev_deferred_count,
        "GEV unavailable asset-hazard pairs": gev_unavailable_count,
        "GEV failed asset-hazard pairs": gev_failed_count,
        "Portfolio dependence disclosure": PORTFOLIO_DEPENDENCE_DISCLOSURE,
        "Adaptation bundle disclosure": ADAPTATION_BUNDLE_DISCLOSURE,
        "Hazard provenance": provenance_rows,
        "Provider events": provider_events,
        "GEV status": gev_status_rows,
        "GEV diagnostics": gev_rows,
    }


def run_manifest_metadata(run_manifest: Optional[dict]) -> dict[str, str]:
    if not run_manifest:
        return {}
    metadata = {
        "Run timestamp (UTC)": run_manifest.get("Run timestamp (UTC)", ""),
        "Methodology version": run_manifest.get("Methodology version", ""),
        "Scenarios": ", ".join(str(label) for label in run_manifest.get("Selected scenario labels", [])),
        "Analysis period": run_manifest.get("Analysis window", ""),
        "Currency": f"{run_manifest.get('Currency', '')} ({run_manifest.get('Currency symbol', '')})".strip(),
        "Discount rate": f"{float(run_manifest.get('Discount rate', 0.0)) * 100:.1f}%",
        "Fetch profile": run_manifest.get("Fetch profile", ""),
        "Fetch profile note": run_manifest.get("Fetch profile note", ""),
        "Source selection mode": run_manifest.get("Source selection mode", ""),
        "Zone override mode": run_manifest.get("Zone override mode", ""),
        "Zone override count": run_manifest.get("Zone override count", 0),
        "Manual override records": run_manifest.get("Manual override records", 0),
        "Refreshed assets": run_manifest.get("Refreshed assets", 0),
        "Reused cached assets": run_manifest.get("Reused cached assets", 0),
        "Provider failure count": run_manifest.get("Provider failure count", 0),
        "Fallback asset-hazard pairs": run_manifest.get("Fallback asset-hazard pairs", 0),
        "Privacy disclosure": run_manifest.get("Privacy disclosure", ""),
        "Degraded mode disclosure": run_manifest.get("Degraded mode disclosure", ""),
        "Tail uncertainty disclosure": run_manifest.get("Tail uncertainty disclosure", ""),
        "GEV diagnostics mode": run_manifest.get("GEV diagnostics mode", ""),
        "GEV generated asset-hazard pairs": run_manifest.get("GEV generated asset-hazard pairs", 0),
        "GEV deferred asset-hazard pairs": run_manifest.get("GEV deferred asset-hazard pairs", 0),
        "GEV unavailable asset-hazard pairs": run_manifest.get("GEV unavailable asset-hazard pairs", 0),
        "GEV failed asset-hazard pairs": run_manifest.get("GEV failed asset-hazard pairs", 0),
        "Portfolio dependence disclosure": run_manifest.get("Portfolio dependence disclosure", ""),
        "Adaptation bundle disclosure": run_manifest.get("Adaptation bundle disclosure", ""),
    }
    analysis_years = run_manifest.get("Analysis years", [])
    if analysis_years:
        metadata["Analysis years"] = ", ".join(str(year) for year in analysis_years)
    return metadata


def run_manifest_provenance_rows(run_manifest: Optional[dict]) -> list[dict]:
    return list((run_manifest or {}).get("Hazard provenance", []))


def run_manifest_provider_rows(run_manifest: Optional[dict]) -> list[dict]:
    return list((run_manifest or {}).get("Provider events", []))


def run_manifest_gev_rows(run_manifest: Optional[dict]) -> list[dict]:
    return list((run_manifest or {}).get("GEV diagnostics", []))


def run_manifest_gev_status_rows(run_manifest: Optional[dict]) -> list[dict]:
    return list((run_manifest or {}).get("GEV status", []))
