"""
ISIMIP3b data extraction — complete implementation using isimip-client.

Provides point-extracted return-period intensity curves for all four hazards:
  • Heat     — tasmax (daily max temp, K→°C) from bias-adjusted InputData, GEV-fitted
  • Wind     — sfcwind (mean wind m/s → 3-s gust) from bias-adjusted InputData, GEV-fitted
  • Flood    — derived from annual max daily precipitation (pr) via JRC-calibrated scaling
  • Wildfire — derived from tasmax + pr + hurs + sfcwind via Canadian FWI system (Van Wagner 1987)

Workflow:
  1. Query ISIMIP3b datasets API → find relevant file paths
  2. Call isimip-client select_point() → async extraction at (lat, lon)
  3. Download ZIP of extracted NetCDF4 files → parse and concatenate time series
  4. Fit GEV distribution via scipy.stats.genextreme
  5. Return (return_periods, intensities)

Output format: ZIP archive containing per-time-chunk NetCDF4 files (NetCDF4/HDF5).
Resolution: 0.5° (~55 km) — ISIMIP3b grid spacing.

Sources:
  Bias-adjusted atmospheric forcing: Lange (2019) https://doi.org/10.5194/esd-10-1321-2019
  isimip-client: https://github.com/ISI-MIP/isimip-client
  FWI system: Van Wagner (1987) CFS Forestry Technical Report 35
"""

import io
import zipfile
import logging
from functools import lru_cache
import numpy as np
from typing import Optional, Tuple, List

import xarray as xr
import pandas as pd

logger = logging.getLogger(__name__)

STANDARD_RETURN_PERIODS = np.array([10, 50, 100, 250, 500, 1000], dtype=float)

_SSP_MAP = {
    "SSP1-1.9": "ssp119",
    "SSP1-2.6": "ssp126",
    "SSP2-4.5": "ssp245",
    "SSP3-7.0": "ssp370",
    "SSP5-8.5": "ssp585",
}

# Preferred GCMs — good global data coverage, widely validated
_GCM_PRIORITY = ["gfdl-esm4", "mpi-esm1-2-hr", "ipsl-cm6a-lr", "mri-esm2-0"]

# Time chunks: use HISTORICAL experiment for scenario-agnostic baseline.
# The damage engine applies IPCC AR6 multipliers for temporal/scenario evolution,
# so fetched data must be a fixed reference — NOT SSP-conditioned future data.
# Historical covers ~1991–2014 (bias-adjusted to W5E5 1979–2014 reanalysis).
_TIME_CHUNKS = ["1991_2000", "2001_2010", "2011_2014"]

# Fixed baseline experiment key — all fetches use this regardless of scenario.
_BASELINE_SSP = "historical"


def _selected_gcms(max_gcms: Optional[int] = None) -> List[str]:
    if max_gcms is None or max_gcms <= 0 or max_gcms >= len(_GCM_PRIORITY):
        return list(_GCM_PRIORITY)
    return list(_GCM_PRIORITY[:max_gcms])


# ---------------------------------------------------------------------------
# GEV fitting
# ---------------------------------------------------------------------------

def _fit_gev(annual_maxima: np.ndarray, return_periods: np.ndarray) -> Optional[np.ndarray]:
    """
    Fit Generalised Extreme Value (GEV) distribution to annual maxima and
    return quantiles at the specified return periods.

    Method: Maximum Likelihood Estimation via scipy.stats.genextreme.
    Reference: Coles (2001) An Introduction to Statistical Modelling of Extreme Values.
    """
    try:
        from scipy.stats import genextreme
        vals = annual_maxima[~np.isnan(annual_maxima)]
        vals = vals[vals > 0]
        if len(vals) < 10:
            return None
        c, loc, scale = genextreme.fit(vals)
        probs = 1.0 - 1.0 / return_periods
        quantiles = genextreme.ppf(probs, c, loc=loc, scale=scale)
        return np.clip(quantiles, 0.0, None)
    except Exception as e:
        logger.debug(f"GEV fit failed: {e}")
        return None


# ---------------------------------------------------------------------------
# NetCDF4 in-memory reader (h5netcdf engine)
# ---------------------------------------------------------------------------

def _read_nc_bytes(data: bytes, variable: str) -> Optional[np.ndarray]:
    """
    Read a single NetCDF4 file from raw bytes using h5netcdf.
    Returns annual maxima (1-D array) or None.
    """
    try:
        ds = xr.open_dataset(io.BytesIO(data), engine="h5netcdf")
        ds = ds.squeeze(drop=True)
        # Find the target variable (case-insensitive fallback)
        var_name = None
        if variable in ds.data_vars:
            var_name = variable
        else:
            for dv in ds.data_vars:
                if dv.lower() == variable.lower():
                    var_name = dv
                    break
        if var_name is None:
            var_name = list(ds.data_vars)[0]
        da = ds[var_name]
        # Drop any remaining singleton spatial dimensions
        for dim in list(da.dims):
            if dim != "time" and da.sizes[dim] == 1:
                da = da.isel({dim: 0})
        if "time" in da.dims:
            annual_max = da.resample(time="1YS").max()
        else:
            annual_max = da
        return annual_max.values.flatten().astype(float)
    except Exception as e:
        logger.debug(f"_read_nc_bytes ({variable}): {e}")
        return None


def _open_isimip_nc(data: bytes, variable: str) -> Optional[np.ndarray]:
    """
    Open ISIMIP-extracted output (ZIP of NetCDF4 files) and return
    concatenated annual maxima across all time chunks.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        nc_names = sorted(n for n in zf.namelist() if n.endswith(".nc"))
        if not nc_names:
            return None
        all_vals: List[float] = []
        for name in nc_names:
            vals = _read_nc_bytes(zf.read(name), variable)
            if vals is not None:
                all_vals.extend(vals.tolist())
        return np.array(all_vals) if all_vals else None
    except zipfile.BadZipFile:
        # Edge case: raw bytes (should not happen with v2 API)
        return _read_nc_bytes(data, variable)
    except Exception as e:
        logger.debug(f"_open_isimip_nc ZIP ({variable}): {e}")
        return None


def _open_isimip_nc_wildfire(data: bytes) -> Optional[tuple]:
    """
    Parse ISIMIP-extracted ZIP containing multiple variables for FWI computation.
    Groups NC files by variable, reads full daily time series, then returns
    aligned arrays in FWI input units.

    Returns (T_arr, H_arr, W_arr, R_arr, years, months) or None.
      T  — daily max temperature (°C)
      H  — relative humidity (%)
      W  — wind speed (km/h)
      R  — precipitation (mm/day)
    """
    # Variable aliases: canonical name → list of possible NetCDF variable names
    VAR_ALIASES = {
        "tasmax": ["tasmax", "tmax"],
        "pr":     ["pr", "prcp", "precipitation"],
        "hurs":   ["hurs", "rh", "relhum"],
        "sfcwind": ["sfcwind", "sfcWind", "wind", "ws"],
    }

    def _read_daily_series(zf, names, aliases):
        """Concatenate daily values + time arrays from multiple NC files."""
        vals_all, years_all, months_all = [], [], []
        for name in names:
            try:
                ds = xr.open_dataset(io.BytesIO(zf.read(name)), engine="h5netcdf")
                ds = ds.squeeze(drop=True)
                var_found = None
                for alias in aliases:
                    if alias in ds.data_vars:
                        var_found = alias
                        break
                    for dv in ds.data_vars:
                        if dv.lower() == alias.lower():
                            var_found = dv
                            break
                    if var_found:
                        break
                if var_found is None:
                    var_found = list(ds.data_vars)[0]
                da = ds[var_found]
                for dim in list(da.dims):
                    if dim != "time" and da.sizes[dim] == 1:
                        da = da.isel({dim: 0})
                v = da.values.flatten().astype(float)
                if "time" in ds.coords:
                    times = pd.DatetimeIndex(ds["time"].values)
                    yrs = times.year.values.astype(int)
                    mths = times.month.values.astype(int)
                else:
                    n = len(v)
                    yrs = np.repeat(np.arange(2021, 2021 + n // 365 + 2), 365)[:n]
                    base_m = np.repeat(np.arange(1, 13),
                                       [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
                    mths = np.tile(base_m, n // 365 + 2)[:n]
                vals_all.extend(v)
                years_all.extend(yrs)
                months_all.extend(mths)
            except Exception as ex:
                logger.debug(f"  wildfire NC read failed ({name}): {ex}")
        if not vals_all:
            return None, None, None
        return np.array(vals_all), np.array(years_all, dtype=int), np.array(months_all, dtype=int)

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        nc_names = sorted(n for n in zf.namelist() if n.endswith(".nc"))
        if not nc_names:
            return None

        # Group files by canonical variable
        var_files = {k: [] for k in VAR_ALIASES}
        for name in nc_names:
            name_lower = name.lower()
            for canonical, aliases in VAR_ALIASES.items():
                if any(f"_{a.lower()}_" in name_lower or name_lower.endswith(f"_{a.lower()}.nc")
                       for a in aliases):
                    var_files[canonical].append(name)
                    break

        if not var_files["tasmax"]:
            logger.debug("No tasmax files found in wildfire ZIP")
            return None

        # Read each variable's daily time series
        T, yl, ml = _read_daily_series(zf, var_files["tasmax"], VAR_ALIASES["tasmax"])
        if T is None or len(T) < 365:
            return None
        n = len(T)

        R, _, _ = _read_daily_series(zf, var_files["pr"], VAR_ALIASES["pr"])
        H, _, _ = _read_daily_series(zf, var_files["hurs"], VAR_ALIASES["hurs"])
        W, _, _ = _read_daily_series(zf, var_files["sfcwind"], VAR_ALIASES["sfcwind"])

        # Fill missing variables with conservative defaults
        if R is None or len(R) < n:
            R = np.zeros(n)          # dry → raises FWI (conservative)
        if H is None or len(H) < n:
            H = np.full(n, 50.0)    # 50% RH
        if W is None or len(W) < n:
            W = np.full(n, 10.0)    # 10 km/h

        # Unit conversions
        if T.mean() > 200:
            T = T - 273.15          # K → °C
        if R.mean() < 1.0:
            R = R * 86400.0         # kg m⁻² s⁻¹ → mm day⁻¹
        if W.mean() < 30:
            W = W * 3.6             # m s⁻¹ → km h⁻¹
        H = np.clip(H, 0.0, 100.0)

        n = min(len(T), len(R), len(H), len(W), len(yl), len(ml))
        return T[:n], H[:n], W[:n], R[:n], yl[:n], ml[:n]

    except zipfile.BadZipFile:
        logger.debug("wildfire: not a ZIP, skipping")
        return None
    except Exception as e:
        logger.debug(f"_open_isimip_nc_wildfire: {e}")
        return None


# ---------------------------------------------------------------------------
# ISIMIP API helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _query_isimip_paths(
    simulation_round: str,
    product: str,
    ssp_key: str,
    variable: str,
    gcm: str,
) -> List[str]:
    """
    Query the ISIMIP datasets API and return file paths for the given specifiers.
    Returns an empty list on failure.
    """
    try:
        from isimip_client.client import ISIMIPClient
        client = ISIMIPClient()
        response = client.datasets(
            simulation_round=simulation_round,
            climate_scenario=ssp_key,
            climate_variable=variable,       # lowercase — ISIMIP API is case-sensitive
            climate_forcing=gcm,
        )
        results = response if isinstance(response, list) else response.get("results", [])
        paths = []
        for dataset in results[:2]:          # limit to 2 datasets
            files = dataset.get("files", []) if isinstance(dataset, dict) else []
            for f in files:
                name = f.get("name", "")
                path = f.get("path", "")
                # Include only files matching requested time chunks
                if path and any(chunk in name for chunk in _TIME_CHUNKS):
                    paths.append(path)
        return paths
    except Exception as e:
        logger.debug(f"ISIMIP dataset query failed: {e}")
        return []


def _isimip_select_point(
    paths: List[str],
    lat: float,
    lon: float,
    poll: int = 5,
) -> Optional[bytes]:
    """
    Submit an ISIMIP point-extraction job, poll until complete, and return
    the raw ZIP bytes containing extracted NetCDF4 files.
    Returns None on any failure.
    """
    try:
        from isimip_client.client import ISIMIPClient
        import requests as req

        client = ISIMIPClient()
        result = client.select_point(paths, lat, lon, poll=poll)
        if not result:
            return None
        status = result.get("status") if isinstance(result, dict) else getattr(result, "status", None)
        if status != "finished":
            logger.debug(f"ISIMIP job status: {status}")
            return None
        file_url = (result.get("file_url") if isinstance(result, dict)
                    else getattr(result, "file_url", None))
        if not file_url:
            return None
        r = req.get(file_url, timeout=120)
        if r.status_code == 200:
            return r.content   # ZIP bytes
        return None
    except Exception as e:
        logger.debug(f"ISIMIP select_point failed: {e}")
        return None


def _build_direct_paths(ssp_key: str, variable: str, gcm: str) -> List[str]:
    """
    Construct ISIMIP3b file paths directly from the known naming convention,
    used as fallback when the datasets API returns no results.
    """
    base = (
        f"ISIMIP3b/SecondaryInputData/climate/atmosphere/bias-adjusted/global/daily"
        f"/{ssp_key}/{gcm.upper()}"
    )
    return [
        f"{base}/{gcm}_r1i1p1f1_w5e5_{ssp_key}_{variable}_global_daily_{chunk}.nc"
        for chunk in _TIME_CHUNKS
    ]


# ---------------------------------------------------------------------------
# Ensemble median helper
# ---------------------------------------------------------------------------

def _ensemble_median(all_curves: List[np.ndarray]) -> Optional[np.ndarray]:
    """Compute element-wise median across GCM curves.

    Parameters
    ----------
    all_curves : list of 1-D arrays, all same length

    Returns median curve or None if empty.
    """
    if not all_curves:
        return None
    return np.median(np.stack(all_curves), axis=0)


# ---------------------------------------------------------------------------
# Public fetch functions
# ---------------------------------------------------------------------------

def fetch_isimip3b_heat(
    lat: float,
    lon: float,
    ssp: str = "SSP2-4.5",
    return_periods: Optional[np.ndarray] = None,
    max_gcms: Optional[int] = None,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Fetch heat (maximum temperature, °C) return-period curve from ISIMIP3b.

    Queries all GCMs in _GCM_PRIORITY and returns the ensemble median curve
    (element-wise median across successful GCM fits).  Falls back to single-GCM
    if only one succeeds.

    Data: ISIMIP3b bias-adjusted tasmax (daily max near-surface temperature, K)
    from the HISTORICAL experiment (scenario-agnostic baseline).
    Resolution: 0.5° (~55 km)
    Citation: Lange (2019) Earth Syst. Dynam. 10, 1321–1336

    Returns (return_periods, temps_celsius) or None.
    """
    if return_periods is None:
        return_periods = STANDARD_RETURN_PERIODS
    # Always use historical baseline — ssp parameter ignored.
    # Scenario differentiation is handled by multipliers in the damage engine.
    ssp_key = _BASELINE_SSP

    gcm_curves: List[np.ndarray] = []
    for gcm in _selected_gcms(max_gcms):
        try:
            paths = _query_isimip_paths("ISIMIP3b", "SecondaryInputData", ssp_key, "tasmax", gcm)
            if not paths:
                paths = _build_direct_paths(ssp_key, "tasmax", gcm)

            data = _isimip_select_point(paths, lat, lon)
            if data is None:
                continue

            annual_max = _open_isimip_nc(data, "tasmax")
            if annual_max is None or len(annual_max) < 10:
                continue

            if annual_max.mean() > 200:
                annual_max = annual_max - 273.15

            temps = _fit_gev(annual_max, return_periods)
            if temps is not None:
                logger.info(f"ISIMIP3b heat: {gcm}/{ssp_key} → {len(annual_max)} yr, "
                            f"RP100={temps[2]:.1f}°C")
                gcm_curves.append(temps)
        except Exception:
            continue

    median = _ensemble_median(gcm_curves)
    if median is not None:
        logger.info(f"ISIMIP3b heat ensemble: {len(gcm_curves)} GCMs, "
                    f"median RP100={median[2]:.1f}°C")
        return return_periods, median
    return None


def fetch_isimip3b_wind(
    lat: float,
    lon: float,
    ssp: str = "SSP2-4.5",
    return_periods: Optional[np.ndarray] = None,
    max_gcms: Optional[int] = None,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Fetch wind speed return-period curve from ISIMIP3b (ensemble median).

    Data: ISIMIP3b bias-adjusted sfcwind (daily mean near-surface wind speed, m/s)
    Conversion: Mean wind → 3-s gust using gust factor 1.5 (WMO-No.8, open terrain)
    Resolution: 0.5°

    Returns (return_periods, gust_speed_ms) or None.
    """
    if return_periods is None:
        return_periods = STANDARD_RETURN_PERIODS
    # Always use historical baseline — ssp parameter ignored.
    ssp_key = _BASELINE_SSP

    gcm_curves: List[np.ndarray] = []
    for gcm in _selected_gcms(max_gcms):
        try:
            paths = _query_isimip_paths("ISIMIP3b", "SecondaryInputData", ssp_key, "sfcwind", gcm)
            if not paths:
                paths = _build_direct_paths(ssp_key, "sfcwind", gcm)

            data = _isimip_select_point(paths, lat, lon)
            if data is None:
                continue

            annual_max = _open_isimip_nc(data, "sfcwind")
            if annual_max is None or len(annual_max) < 10:
                annual_max = _open_isimip_nc(data, "sfcWind")
            if annual_max is None or len(annual_max) < 10:
                continue

            annual_max_gust = annual_max * 1.5
            speeds = _fit_gev(annual_max_gust, return_periods)
            if speeds is not None:
                logger.info(f"ISIMIP3b wind: {gcm}/{ssp_key} → {len(annual_max)} yr, "
                            f"RP100={speeds[2]:.1f} m/s")
                gcm_curves.append(speeds)
        except Exception:
            continue

    median = _ensemble_median(gcm_curves)
    if median is not None:
        logger.info(f"ISIMIP3b wind ensemble: {len(gcm_curves)} GCMs, "
                    f"median RP100={median[2]:.1f} m/s")
        return return_periods, median
    return None


def fetch_isimip3b_flood(
    lat: float,
    lon: float,
    ssp: str = "SSP2-4.5",
    return_periods: Optional[np.ndarray] = None,
    max_gcms: Optional[int] = None,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Derive flood depth return-period curve from ISIMIP3b precipitation extremes.

    ISIMIP3b does not publish floodplain inundation depths via the public API.
    Flood hazard is instead derived from annual maximum daily precipitation (Rx1day):
      1. Extract daily precipitation time series (pr, kg m⁻² s⁻¹ → mm day⁻¹)
      2. Compute annual maxima (Rx1day)
      3. Fit GEV to obtain Rx1day at standard return periods
      4. Convert Rx1day → inundation depth using JRC-calibrated empirical scaling:
           depth_m = max(0, (Rx1day - drainage_threshold_mm) × depth_factor)
         where drainage_threshold_mm = 25 mm (typical urban drainage capacity)
         and depth_factor = 0.012 m/mm (calibrated to JRC European data)
    This approach is widely used when floodplain models are unavailable and is
    consistent with TCFD physical risk methodologies for asset-level assessment.

    Reference: Huizinga et al. (2017) JRC EUR 28505 EN; Alfieri et al. (2017) NHESS.
    Resolution: 0.5°

    Returns (return_periods, flood_depths_m) or None.
    """
    if return_periods is None:
        return_periods = STANDARD_RETURN_PERIODS
    # Always use historical baseline — ssp parameter ignored.
    ssp_key = _BASELINE_SSP

    # Regional drainage threshold and depth factor — accounts for regional variation
    # in drainage capacity, soil permeability, and terrain slope.
    # Source: Huizinga et al. (2017) JRC EUR 28505 EN; Alfieri et al. (2017) NHESS.
    _REGIONAL_FLOOD_PARAMS = {
        # (drainage_threshold_mm, depth_factor_m_per_mm)
        "EUR": (30.0, 0.010),    # good drainage infrastructure
        "USA": (28.0, 0.011),    # variable; urban areas better drained
        "CHN": (22.0, 0.014),    # dense urban areas, high runoff
        "IND": (18.0, 0.016),    # poor drainage, flat terrain, monsoon
        "AUS": (25.0, 0.012),    # moderate drainage
        "BRA": (20.0, 0.015),    # tropical rainfall, variable drainage
        "MEA": (15.0, 0.018),    # arid soils, poor absorption, flash flood prone
        "global": (25.0, 0.012),
    }

    # Determine regional parameters
    try:
        from engine.hazard_fetcher import _get_region_key
        # Approximate region from latitude/longitude
        if 35 <= lat <= 72 and -10 <= lon <= 40:
            zone = "EUR"
        elif 25 <= lat <= 50 and -130 <= lon <= -60:
            zone = "USA"
        elif 18 <= lat <= 55 and 73 <= lon <= 135:
            zone = "CHN"
        elif 5 <= lat <= 40 and 60 <= lon <= 100:
            zone = "IND"
        elif -45 <= lat <= -10 and 110 <= lon <= 155:
            zone = "AUS"
        elif -35 <= lat <= 10 and -75 <= lon <= -35:
            zone = "BRA"
        elif (15 <= lat <= 40 and 25 <= lon <= 60) or (-35 <= lat <= 15 and 10 <= lon <= 50):
            zone = "MEA"
        else:
            zone = "global"
    except Exception:
        zone = "global"

    DRAINAGE_THRESHOLD_MM, DEPTH_FACTOR = _REGIONAL_FLOOD_PARAMS.get(zone, _REGIONAL_FLOOD_PARAMS["global"])

    gcm_curves: List[np.ndarray] = []
    for gcm in _selected_gcms(max_gcms):
        try:
            paths = _query_isimip_paths("ISIMIP3b", "SecondaryInputData", ssp_key, "pr", gcm)
            if not paths:
                paths = _build_direct_paths(ssp_key, "pr", gcm)

            data = _isimip_select_point(paths, lat, lon)
            if data is None:
                continue

            annual_max_pr = _open_isimip_nc(data, "pr")
            if annual_max_pr is None or len(annual_max_pr) < 10:
                continue

            if annual_max_pr.mean() < 1.0:
                annual_max_pr = annual_max_pr * 86400.0

            rx1day = _fit_gev(annual_max_pr, return_periods)
            if rx1day is None:
                continue

            depths = np.clip((rx1day - DRAINAGE_THRESHOLD_MM) * DEPTH_FACTOR, 0.0, 8.0)
            logger.info(f"ISIMIP3b flood (pr-derived, zone={zone}): {gcm}/{ssp_key} → {len(annual_max_pr)} yr, "
                        f"RP100 Rx1day={rx1day[2]:.0f}mm → depth={depths[2]:.2f}m")
            gcm_curves.append(depths)
        except Exception:
            continue

    median = _ensemble_median(gcm_curves)
    if median is not None:
        logger.info(f"ISIMIP3b flood ensemble: {len(gcm_curves)} GCMs, "
                    f"median RP100 depth={median[2]:.2f}m")
        return return_periods, median
    return None


def fetch_isimip3b_wildfire(
    lat: float,
    lon: float,
    ssp: str = "SSP2-4.5",
    return_periods: Optional[np.ndarray] = None,
    vegetation: str = "forest",
    max_gcms: Optional[int] = None,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Derive wildfire flame length return periods from ISIMIP3b multi-variable extraction.

    ISIMIP3b does not publish a direct wildfire output. Flame length is derived via the
    complete Canadian Forest Fire Weather Index (FWI) system (Van Wagner 1987):

      Step 1 — Extract 4 daily variables in one job: tasmax, pr, hurs, sfcwind
      Step 2 — Compute daily FWI series (FFMC/DMC/DC/ISI/BUI/FWI sequential algorithm)
                with latitude-dependent day-length factors
      Step 3 — Fit GEV to annual maximum FWI series
      Step 4 — Convert FWI quantiles → flame length (m):
                  Fireline intensity  I = A × FWI^1.5     (Simard 1970)
                  Flame length        L = 0.0775 × I^0.46  (Byram 1959)
                with A = 300 (forest), 450 (Mediterranean shrubland), 200 (grassland)

    Resolution: 0.5° — ISIMIP3b grid
    Citation: Van Wagner (1987) CFS Forestry Technical Report 35

    Returns (return_periods, flame_lengths_m) or None.
    """
    if return_periods is None:
        return_periods = STANDARD_RETURN_PERIODS
    # Always use historical baseline — ssp parameter ignored.
    ssp_key = _BASELINE_SSP

    try:
        from engine.fire_weather import annual_max_fwi, fwi_to_flame_length
    except ImportError:
        logger.debug("fire_weather module not available")
        return None

    WILDFIRE_VARS = ["tasmax", "pr", "hurs", "sfcwind"]

    gcm_curves: List[np.ndarray] = []
    for gcm in _selected_gcms(max_gcms):
        try:
            all_paths: List[str] = []
            for var in WILDFIRE_VARS:
                paths = _query_isimip_paths("ISIMIP3b", "SecondaryInputData", ssp_key, var, gcm)
                if not paths:
                    paths = _build_direct_paths(ssp_key, var, gcm)
                all_paths.extend(paths[:2])

            if not all_paths:
                continue

            data = _isimip_select_point(all_paths, lat, lon)
            if data is None:
                continue

            climate_arrays = _open_isimip_nc_wildfire(data)
            if climate_arrays is None:
                continue

            T_arr, H_arr, W_arr, R_arr, years, months = climate_arrays

            if len(T_arr) < 365 * 10:
                continue

            ann_fwi = annual_max_fwi(T_arr, H_arr, W_arr, R_arr, years, months, lat)
            if len(ann_fwi) < 10:
                continue

            fwi_quantiles = _fit_gev(ann_fwi, return_periods)
            if fwi_quantiles is None:
                continue

            flame_lengths = np.array([
                fwi_to_flame_length(float(q), vegetation) for q in fwi_quantiles
            ])

            logger.info(
                f"ISIMIP3b wildfire (FWI): {gcm}/{ssp_key} lat={lat:.2f} "
                f"→ {len(ann_fwi)} yr, median FWI={np.median(ann_fwi):.1f}, "
                f"RP100 flame={flame_lengths[2]:.2f}m"
            )
            gcm_curves.append(flame_lengths)
        except Exception:
            continue

    median = _ensemble_median(gcm_curves)
    if median is not None:
        logger.info(f"ISIMIP3b wildfire ensemble: {len(gcm_curves)} GCMs, "
                    f"median RP100 flame={median[2]:.2f}m")
        return return_periods, median
    return None
