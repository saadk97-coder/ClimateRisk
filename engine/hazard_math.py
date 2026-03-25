"""
Shared hazard math helpers used by the engine, audit views, and exports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from engine.scenario_model import get_slr_additive

if TYPE_CHECKING:
    from engine.asset_model import Asset


DEFAULT_DISPLAY_RETURN_PERIOD_MAX = 500.0


@dataclass(frozen=True)
class HazardAdjustmentContext:
    multiplier: float
    freeboard_m: float
    terrain_elevation_asl_m: float
    slr_additive_m: float
    formula_label: str


def display_return_period_mask(
    return_periods: np.ndarray | list[float],
    max_return_period: float = DEFAULT_DISPLAY_RETURN_PERIOD_MAX,
) -> np.ndarray:
    rp = np.asarray(return_periods, dtype=float)
    return rp <= float(max_return_period)


def compute_effective_intensities(
    hazard: str,
    base_intensities: np.ndarray | list[float],
    multiplier: float,
    asset: "Asset",
    *,
    scenario_id: str | None = None,
    year: int | None = None,
    region_zone: str = "global",
) -> tuple[np.ndarray, HazardAdjustmentContext]:
    """
    Apply the live engine's hazard adjustments to baseline intensities.

    Flood:
        effective_depth = max(0, base_depth * flood_mult - freeboard)

    Coastal flood:
        effective_depth = max(
            0,
            base_surge * storm_mult + slr_additive - terrain_elevation - freeboard,
        )
    """
    base = np.asarray(base_intensities, dtype=float)
    freeboard_m = max(float(getattr(asset, "first_floor_height_m", 0.0) or 0.0), 0.0)
    terrain_elevation_asl_m = float(getattr(asset, "terrain_elevation_asl_m", 0.0) or 0.0)
    slr_additive_m = 0.0

    if hazard == "coastal_flood":
        if scenario_id is None or year is None:
            raise ValueError("scenario_id and year are required for coastal flood adjustments")
        slr_additive_m = float(get_slr_additive(scenario_id, year, region_zone))
        effective = np.clip(
            base * float(multiplier) + slr_additive_m - terrain_elevation_asl_m - freeboard_m,
            0.0,
            None,
        )
        formula_label = "max(0, base_surge * storm_mult + slr_additive - terrain_elevation - freeboard)"
    elif hazard == "flood":
        effective = np.clip(base * float(multiplier) - freeboard_m, 0.0, None)
        formula_label = "max(0, base_depth * flood_mult - freeboard)"
    else:
        effective = base * float(multiplier)
        formula_label = "base_intensity * hazard_multiplier"

    return effective, HazardAdjustmentContext(
        multiplier=float(multiplier),
        freeboard_m=freeboard_m,
        terrain_elevation_asl_m=terrain_elevation_asl_m,
        slr_additive_m=slr_additive_m,
        formula_label=formula_label,
    )
