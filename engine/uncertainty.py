"""
Monte Carlo uncertainty quantification: 1000 draws → 5th / 95th percentile CI on EAD.
Sources of uncertainty modelled:
  1. Hazard intensity: log-normal spread (~20% CV) — perturbed BEFORE vulnerability curve
  2. Vulnerability curve: uniform ±15% additive noise on damage fraction AFTER curve lookup
  3. Asset value: normal ±10% CV
"""

import numpy as np
from typing import Tuple, Optional
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
    hazard: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> Tuple[float, float, float, np.ndarray]:
    """
    Monte Carlo EAD uncertainty estimation.

    Correctly separates uncertainty channels:
      1. Perturb intensity (log-normal) → re-evaluate vulnerability curve
      2. Add vulnerability curve noise (uniform additive)
      3. Perturb asset value (normal)

    Parameters
    ----------
    return_periods, base_intensities, base_damage_fractions : baseline EP curve data
    asset_value : replacement value
    hazard, asset_type : if provided, perturbed intensities are re-evaluated through
                         the vulnerability curve; otherwise falls back to scaling base DFs

    Returns
    -------
    (ead_mean, ead_p5, ead_p95, all_ead_draws)
    """
    rng = np.random.default_rng(seed)
    rp = np.asarray(return_periods, dtype=float)
    base_intens = np.asarray(base_intensities, dtype=float)
    base_df = np.asarray(base_damage_fractions, dtype=float)

    # Try to import vulnerability curve for proper intensity → DF re-evaluation
    _get_df = None
    if hazard and asset_type:
        try:
            from engine.impact_functions import get_damage_fraction
            _get_df = get_damage_fraction
        except ImportError:
            pass

    ead_draws = np.empty(n_draws)
    for i in range(n_draws):
        # 1. Perturb hazard intensity (log-normal multiplicative)
        intensity_factor = rng.lognormal(mean=0.0, sigma=INTENSITY_CV)
        perturbed_intens = base_intens * intensity_factor

        # 2. Re-evaluate vulnerability curve with perturbed intensities
        if _get_df is not None:
            df_from_curve = np.array([
                _get_df(hazard, asset_type, float(x)) for x in perturbed_intens
            ])
        else:
            # Fallback: scale base damage fractions proportionally
            df_from_curve = np.clip(base_df * intensity_factor, 0.0, 1.0)

        # 3. Add vulnerability curve uncertainty (uniform additive noise)
        noise = rng.uniform(-VULNERABILITY_SPREAD, VULNERABILITY_SPREAD, size=len(df_from_curve))
        df_perturbed = np.clip(df_from_curve + noise, 0.0, 1.0)

        # 4. Perturb asset value (normal)
        value_perturbed = asset_value * rng.normal(loc=1.0, scale=VALUE_CV)
        value_perturbed = max(value_perturbed, 0.0)

        ead_draws[i] = calc_ead(rp, df_perturbed, value_perturbed)

    ead_mean = float(np.mean(ead_draws))
    ead_p5 = float(np.percentile(ead_draws, 5))
    ead_p95 = float(np.percentile(ead_draws, 95))
    return ead_mean, ead_p5, ead_p95, ead_draws
