"""
Screening-level hazard dependence helpers.

These functions intentionally use transparent, low-parameter distance-decay
approximations. They are not stochastic event-set or institution-grade
portfolio tail models.
"""

from __future__ import annotations

import math


HAZARD_CORRELATION_SPECS = {
    "flood": {"scale_km": 75.0, "floor": 0.02, "label": "short-range fluvial/pluvial decay"},
    "coastal_flood": {"scale_km": 250.0, "floor": 0.10, "label": "regional coastal decay"},
    "wind": {"scale_km": 225.0, "floor": 0.08, "label": "storm-footprint decay"},
    "wildfire": {"scale_km": 150.0, "floor": 0.05, "label": "medium-range wildfire decay"},
    "heat": {"scale_km": 1200.0, "floor": 0.20, "label": "long-range heat co-movement"},
    "water_stress": {"scale_km": 1800.0, "floor": 0.25, "label": "very long-range water-stress decay"},
    "default": {"scale_km": 200.0, "floor": 0.05, "label": "generic screening decay"},
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    d_phi = math.radians(float(lat2) - float(lat1))
    d_lambda = math.radians(float(lon2) - float(lon1))
    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    return 2.0 * radius_km * math.atan2(math.sqrt(a), math.sqrt(max(1.0 - a, 0.0)))


def hazard_pair_correlation(hazard: str, distance_km: float) -> float:
    spec = HAZARD_CORRELATION_SPECS.get(hazard, HAZARD_CORRELATION_SPECS["default"])
    if distance_km <= 0:
        return 1.0
    floor = float(spec["floor"])
    scale_km = float(spec["scale_km"])
    return max(0.0, min(1.0, floor + (1.0 - floor) * math.exp(-distance_km / scale_km)))


def portfolio_dependence_note() -> str:
    return (
        "Hazard-aware screening correlation uses simple distance-decay functions by hazard. "
        "Cross-hazard dependence is not modelled explicitly."
    )
