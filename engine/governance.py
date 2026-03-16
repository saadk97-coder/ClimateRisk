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
from typing import Iterable

from engine.data_sources import DATA_SOURCE_REGISTRY

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
