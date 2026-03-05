"""
Monte Carlo uncertainty quantification: 1000 draws → 5th / 95th percentile CI on EAD.
Sources of uncertainty modelled:
  1. Hazard intensity: log-normal spread (~20% CV)
  2. Vulnerability curve: uniform ±15% on damage fraction
  3. Asset value: normal ±10% CV
"""

import numpy as np
from typing import Tuple
from engine.ead_calculator import calc_ead

N_DRAWS = 1000
INTENSITY_CV = 0.20       # coefficient of variation on hazard intensity
VULNERABILITY_SPREAD = 0.15  # fraction spread on damage fractions
VALUE_CV = 0.10           # coefficient of variation on asset replacement value
RNG_SEED = 42


def run_monte_carlo(
    return_periods: np.ndarray,
    base_intensities: np.ndarray,
    base_damage_fractions: np.ndarray,
    asset_value: float,
    n_draws: int = N_DRAWS,
    seed: int = RNG_SEED,
) -> Tuple[float, float, float, np.ndarray]:
    """
    Monte Carlo EAD uncertainty estimation.

    Returns
    -------
    (ead_mean, ead_p5, ead_p95, all_ead_draws)
    """
    rng = np.random.default_rng(seed)
    rp = np.asarray(return_periods, dtype=float)
    base_df = np.asarray(base_damage_fractions, dtype=float)

    ead_draws = np.empty(n_draws)
    for i in range(n_draws):
        # 1. Perturb hazard intensity (log-normal)
        intensity_factor = rng.lognormal(mean=0.0, sigma=INTENSITY_CV)

        # 2. Perturb damage fractions (uniform additive noise)
        noise = rng.uniform(-VULNERABILITY_SPREAD, VULNERABILITY_SPREAD, size=len(base_df))
        df_perturbed = np.clip(base_df * intensity_factor + noise, 0.0, 1.0)

        # 3. Perturb asset value (normal)
        value_perturbed = asset_value * rng.normal(loc=1.0, scale=VALUE_CV)
        value_perturbed = max(value_perturbed, 0.0)

        ead_draws[i] = calc_ead(rp, df_perturbed, value_perturbed)

    ead_mean = float(np.mean(ead_draws))
    ead_p5 = float(np.percentile(ead_draws, 5))
    ead_p95 = float(np.percentile(ead_draws, 95))
    return ead_mean, ead_p5, ead_p95, ead_draws
