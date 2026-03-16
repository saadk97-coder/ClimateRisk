"""
Portfolio input validation helpers used by upload and manual-entry flows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

REQUIRED_COLUMNS = [
    "id",
    "name",
    "lat",
    "lon",
    "asset_type",
    "replacement_value",
    "region",
]

OPTIONAL_COLUMNS = [
    "construction_material",
    "year_built",
    "stories",
    "basement",
    "roof_type",
    "first_floor_height_m",
    "terrain_elevation_asl_m",
    "floor_area_m2",
]

VALID_MATERIALS = {"wood_frame", "masonry", "steel", "concrete", "mixed"}
VALID_ROOFS = {"flat", "gable", "hip"}


@dataclass
class PortfolioValidationResult:
    normalized_df: pd.DataFrame
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def _coerce_bool(value) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "t", "yes", "y", "1"}:
        return True
    if text in {"false", "f", "no", "n", "0", ""}:
        return False
    raise ValueError(f"Invalid boolean value '{value}'")


def validate_portfolio_df(
    df: pd.DataFrame,
    asset_types: dict,
    valid_regions: Iterable[str],
) -> PortfolioValidationResult:
    normalized = df.copy()
    normalized.columns = [str(c).strip() for c in normalized.columns]
    errors: list[str] = []
    warnings: list[str] = []
    valid_regions_set = set(valid_regions)

    missing = [col for col in REQUIRED_COLUMNS if col not in normalized.columns]
    if missing:
        errors.append(
            "Missing required columns: " + ", ".join(missing)
        )
        return PortfolioValidationResult(normalized, errors, warnings)

    for optional in OPTIONAL_COLUMNS:
        if optional not in normalized.columns:
            normalized[optional] = None

    normalized["id"] = normalized["id"].astype(str).str.strip()
    normalized["name"] = normalized["name"].astype(str).str.strip()
    normalized["asset_type"] = normalized["asset_type"].astype(str).str.strip()
    normalized["region"] = normalized["region"].astype(str).str.strip().str.upper()

    duplicate_ids = normalized["id"][normalized["id"].duplicated()].unique().tolist()
    if duplicate_ids:
        errors.append("Duplicate asset IDs are not allowed: " + ", ".join(duplicate_ids))

    empty_id_rows = normalized.index[normalized["id"] == ""].tolist()
    if empty_id_rows:
        errors.append(
            "Asset ID is required for every row. Empty IDs at rows: "
            + ", ".join(str(i + 2) for i in empty_id_rows)
        )

    empty_name_rows = normalized.index[normalized["name"] == ""].tolist()
    if empty_name_rows:
        errors.append(
            "Asset name is required for every row. Empty names at rows: "
            + ", ".join(str(i + 2) for i in empty_name_rows)
        )

    unknown_asset_types = sorted(set(normalized["asset_type"]) - set(asset_types))
    if unknown_asset_types:
        errors.append(
            "Unknown asset types: " + ", ".join(unknown_asset_types)
        )

    unknown_regions = sorted(set(normalized["region"]) - valid_regions_set)
    if unknown_regions:
        errors.append(
            "Unknown ISO3 country codes: " + ", ".join(unknown_regions)
        )

    numeric_columns = [
        "lat",
        "lon",
        "replacement_value",
        "year_built",
        "stories",
        "first_floor_height_m",
        "terrain_elevation_asl_m",
        "floor_area_m2",
    ]
    for column in numeric_columns:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    for idx, row in normalized.iterrows():
        row_num = idx + 2
        asset_defaults = asset_types.get(row["asset_type"], {})

        if pd.isna(row["lat"]) or not (-90.0 <= float(row["lat"]) <= 90.0):
            errors.append(f"Row {row_num}: latitude must be between -90 and 90.")
        if pd.isna(row["lon"]) or not (-180.0 <= float(row["lon"]) <= 180.0):
            errors.append(f"Row {row_num}: longitude must be between -180 and 180.")
        if pd.isna(row["replacement_value"]) or float(row["replacement_value"]) <= 0:
            errors.append(f"Row {row_num}: replacement_value must be greater than 0.")

        if pd.isna(row["year_built"]):
            normalized.at[idx, "year_built"] = 2000
            warnings.append(f"Row {row_num}: year_built missing, defaulted to 2000.")
        elif not (1800 <= int(row["year_built"]) <= 2025):
            errors.append(f"Row {row_num}: year_built must be between 1800 and 2025.")

        if pd.isna(row["stories"]):
            normalized.at[idx, "stories"] = int(asset_defaults.get("default_stories", 1))
        elif int(row["stories"]) < 1:
            errors.append(f"Row {row_num}: stories must be at least 1.")

        if pd.isna(row["first_floor_height_m"]):
            normalized.at[idx, "first_floor_height_m"] = 0.0
        elif float(row["first_floor_height_m"]) < 0:
            errors.append(f"Row {row_num}: first_floor_height_m cannot be negative.")

        if pd.isna(row["terrain_elevation_asl_m"]):
            normalized.at[idx, "terrain_elevation_asl_m"] = 0.0

        if pd.isna(row["floor_area_m2"]):
            normalized.at[idx, "floor_area_m2"] = float(asset_defaults.get("default_floor_area_m2", 200.0))
        elif float(row["floor_area_m2"]) < 0:
            errors.append(f"Row {row_num}: floor_area_m2 cannot be negative.")

        material = row.get("construction_material")
        if pd.isna(material) or str(material).strip() == "":
            normalized.at[idx, "construction_material"] = asset_defaults.get("default_material", "masonry")
        else:
            normalized.at[idx, "construction_material"] = str(material).strip()
            if normalized.at[idx, "construction_material"] not in VALID_MATERIALS:
                errors.append(
                    f"Row {row_num}: construction_material must be one of "
                    + ", ".join(sorted(VALID_MATERIALS))
                    + "."
                )

        roof_type = row.get("roof_type")
        if pd.isna(roof_type) or str(roof_type).strip() == "":
            normalized.at[idx, "roof_type"] = asset_defaults.get("default_roof", "gable")
        else:
            normalized.at[idx, "roof_type"] = str(roof_type).strip()
            if normalized.at[idx, "roof_type"] not in VALID_ROOFS:
                errors.append(
                    f"Row {row_num}: roof_type must be one of "
                    + ", ".join(sorted(VALID_ROOFS))
                    + "."
                )

        basement = row.get("basement")
        try:
            normalized.at[idx, "basement"] = _coerce_bool(basement)
        except ValueError as exc:
            errors.append(f"Row {row_num}: {exc}")

    return PortfolioValidationResult(normalized, errors, warnings)
