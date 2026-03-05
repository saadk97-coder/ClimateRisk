"""
Expected Annual Damage (EAD) calculator using trapezoidal integration
over the exceedance probability (EP) curve.

Standard return periods: 2, 5, 10, 25, 50, 100, 250, 500, 1000 years
"""

import numpy as np
from typing import Sequence

STANDARD_RETURN_PERIODS = np.array([2, 5, 10, 25, 50, 100, 250, 500, 1000], dtype=float)


def calc_ead(
    return_periods: np.ndarray,
    damage_fractions: np.ndarray,
    asset_value: float,
) -> float:
    """
    Calculate Expected Annual Damage via trapezoidal integration under the EP curve.

    Parameters
    ----------
    return_periods    : 1-D array of return periods (years), e.g. [10, 50, 100, 500]
    damage_fractions  : 1-D array of damage fractions [0–1] at each return period
    asset_value       : replacement value of the asset (£ / $ / €)

    Returns
    -------
    EAD in the same currency as asset_value
    """
    rp = np.asarray(return_periods, dtype=float)
    df = np.asarray(damage_fractions, dtype=float)

    # Annual exceedance probabilities
    aep = 1.0 / rp

    # Absolute damages
    damages = df * asset_value

    # Sort by ascending AEP (i.e. descending return period)
    order = np.argsort(aep)
    aep_sorted = aep[order]
    dmg_sorted = damages[order]

    # Trapezoidal integration (damages vs AEP)
    ead = float(np.trapz(dmg_sorted, aep_sorted))
    return max(ead, 0.0)


def build_ep_curve(
    return_periods: np.ndarray,
    damage_fractions: np.ndarray,
    asset_value: float,
) -> tuple:
    """
    Return (aep, losses) arrays representing the exceedance probability curve.
    Suitable for plotting.
    """
    rp = np.asarray(return_periods, dtype=float)
    df = np.asarray(damage_fractions, dtype=float)
    aep = 1.0 / rp
    losses = df * asset_value
    order = np.argsort(aep)
    return aep[order], losses[order]


def calc_ead_from_intensities(
    return_periods: np.ndarray,
    intensities: np.ndarray,
    asset_type: str,
    hazard: str,
    asset_value: float,
    hazard_multiplier: float = 1.0,
) -> tuple:
    """
    Full pipeline: intensities → damage fractions → EAD.

    Returns (ead, damage_fractions)
    """
    from engine.impact_functions import get_damage_fraction

    scaled = np.asarray(intensities, dtype=float) * hazard_multiplier
    damage_fractions = np.array([
        get_damage_fraction(hazard, asset_type, i) for i in scaled
    ])
    ead = calc_ead(return_periods, damage_fractions, asset_value)
    return ead, damage_fractions
