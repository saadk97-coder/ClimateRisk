"""
Uncertainty helpers.

This module currently supports two separate screening-level uncertainty views:
  1. Monte Carlo perturbation around an already-built EP curve
  2. Conditional parameter-uncertainty bands for GEV return levels

The GEV bands are conditional on:
  - the fitted GEV model form being appropriate
  - the historical annual-maxima sample being representative

They are not full climate-model, structural, or decision uncertainty.
"""

import numpy as np
from typing import Tuple, Optional
from engine.ead_calculator import calc_ead

N_DRAWS = 1000
INTENSITY_CV = 0.20       # coefficient of variation on hazard intensity
VULNERABILITY_SPREAD = 0.15  # fraction spread on damage fractions
VALUE_CV = 0.10           # coefficient of variation on asset replacement value
RNG_SEED = 42
GEV_PARAMETER_DRAWS = 300
GEV_BAND_QUANTILES = (10.0, 90.0)


def _clean_annual_maxima(annual_maxima: np.ndarray) -> np.ndarray:
    vals = np.asarray(annual_maxima, dtype=float)
    vals = vals[~np.isnan(vals)]
    vals = vals[np.isfinite(vals)]
    vals = vals[vals > 0]
    return vals


def fit_gev_central(
    annual_maxima: np.ndarray,
    return_periods: np.ndarray,
) -> Optional[dict]:
    """
    Fit a GEV by MLE and return only the central return-level curve.

    This is the precision-preserving hot-path fit used during standard runs.
    It intentionally excludes the expensive bootstrap-refit uncertainty step.
    """
    try:
        from scipy.stats import genextreme
    except Exception:
        return None

    vals = _clean_annual_maxima(annual_maxima)
    rp = np.asarray(return_periods, dtype=float)
    if len(vals) < 10 or rp.size == 0:
        return None

    try:
        shape, loc, scale = genextreme.fit(vals)
        if not np.isfinite(scale) or scale <= 0:
            return None
        probs = 1.0 - 1.0 / rp
        central = np.clip(genextreme.ppf(probs, shape, loc=loc, scale=scale), 0.0, None)
        return {
            "central": central,
            "params": {
                "shape": float(shape),
                "loc": float(loc),
                "scale": float(scale),
            },
            "sample_years": int(len(vals)),
        }
    except Exception:
        return None


def fit_gev_parameter_bands(
    annual_maxima: np.ndarray,
    return_periods: np.ndarray,
    *,
    central_fit: Optional[dict] = None,
) -> Optional[dict]:
    """
    Fit a GEV and compute conditional parameter-uncertainty bands.

    The uncertainty bands are generated with a parametric bootstrap:
      1. fit GEV by MLE to the observed annual maxima
      2. simulate synthetic annual maxima from that fitted GEV
      3. refit the GEV to each synthetic sample
      4. compute pointwise return levels across the requested RP grid

    Returns a diagnostics dictionary or None if the fit is not stable enough.
    """
    try:
        from scipy.stats import genextreme
    except Exception:
        return None

    vals = _clean_annual_maxima(annual_maxima)
    rp = np.asarray(return_periods, dtype=float)
    if len(vals) < 10 or rp.size == 0:
        return None

    fit = central_fit or fit_gev_central(vals, rp)
    if fit is None:
        return None

    try:
        params = fit["params"]
        shape = float(params["shape"])
        loc = float(params["loc"])
        scale = float(params["scale"])
        probs = 1.0 - 1.0 / rp
        central = np.asarray(fit["central"], dtype=float)

        rng = np.random.default_rng(RNG_SEED)
        samples = np.empty((GEV_PARAMETER_DRAWS, len(rp)), dtype=float)
        filled = 0
        for _ in range(GEV_PARAMETER_DRAWS):
            synthetic = genextreme.rvs(shape, loc=loc, scale=scale, size=len(vals), random_state=rng)
            synthetic = _clean_annual_maxima(synthetic)
            if len(synthetic) < 10:
                continue
            try:
                s_shape, s_loc, s_scale = genextreme.fit(synthetic)
                if not np.isfinite(s_scale) or s_scale <= 0:
                    continue
                samples[filled, :] = np.clip(
                    genextreme.ppf(probs, s_shape, loc=s_loc, scale=s_scale),
                    0.0,
                    None,
                )
                filled += 1
            except Exception:
                continue

        if filled == 0:
            return None

        draws = samples[:filled, :]
        lower_q, upper_q = GEV_BAND_QUANTILES
        lower = np.percentile(draws, lower_q, axis=0)
        upper = np.percentile(draws, upper_q, axis=0)
        return {
            "central": central,
            "lower": lower,
            "upper": upper,
            "params": dict(params),
            "sample_years": int(fit["sample_years"]),
            "bootstrap_draws": int(filled),
            "band_label": f"P{int(lower_q)}-P{int(upper_q)} parameter band",
            "method": "GEV MLE with parametric bootstrap refits",
            "limitation": (
                "Conditional parameter uncertainty only. Does not include model-form, "
                "climate-model, exposure, or vulnerability uncertainty."
            ),
        }
    except Exception:
        return None


def fit_gev_return_levels(
    annual_maxima: np.ndarray,
    return_periods: np.ndarray,
) -> Optional[dict]:
    """
    Backward-compatible wrapper returning central levels plus conditional bands.
    """
    return fit_gev_parameter_bands(annual_maxima, return_periods)


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
