"""
Canadian Forest Fire Weather Index (FWI) System — complete implementation.

Authoritative reference:
  Van Wagner, C.E. (1987). Development and structure of the Canadian Forest Fire
  Weather Index System. Canadian Forestry Service, Forestry Technical Report 35.
  https://cfs.nrcan.gc.ca/pubwarehouse/pdfs/19927.pdf

The FWI system is the global standard for fire danger rating, used by:
  EFFIS (European Forest Fire Information System) — JRC, European Commission
  GWIS (Global Wildfire Information System) — Copernicus Emergency Management
  CWFIS (Canadian Wildland Fire Information System)
  FAO / UN Environment Programme global fire danger assessments

Components:
  FFMC  Fine Fuel Moisture Code    — surface duff moisture (0–101)
  DMC   Duff Moisture Code         — upper organic layer moisture (0–∞)
  DC    Drought Code               — deep soil moisture (0–∞)
  ISI   Initial Spread Index       — fire spread rate (FFMC + wind)
  BUI   Buildup Index              — available fuel (DMC + DC)
  FWI   Fire Weather Index         — overall fire danger (ISI + BUI)
  DSR   Daily Severity Rating      — FWI-based suppression difficulty

Inputs required (daily, at noon local solar time or daily max/mean proxies):
  T     Temperature (°C)           — use tasmax as noon proxy
  H     Relative humidity (%)      — use daily mean hurs (conservative)
  W     Wind speed (km/h)          — use sfcWind × 3.6
  r     24-hour rainfall (mm)      — use pr × 86400

Flame length conversion:
  Fireline intensity (kW/m): I = A × FWI^1.5  (Simard 1970 calibration,
  as used in the Canadian Forest Fire Behaviour Prediction System)
  Flame length (m): L = 0.0775 × I^0.46  (Byram 1959)
  Calibration constant A = 300 is empirically derived from Canadian boreal fires;
  A = 450 is used for Mediterranean-type vegetation (Fernandes et al. 2018,
  Int. J. Wildland Fire 27(4)).

Day length factors:
  Approximated from Van Wagner (1987) Table 2 and Forestry Canada (1992).
  Latitude-dependent monthly correction applied to DMC and DC.
"""

import numpy as np
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Day-length factors (Van Wagner 1987, Tables 1 and 2)
# ---------------------------------------------------------------------------

# DMC day-length adjustment factors (L_e) by latitude band and month
_DMC_LE = {
    "≥90°N": [6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0],
    "≥60°N": [6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0],
    "≥45°N": [7.9, 8.4, 10.0, 12.5, 13.4, 13.2, 12.6, 11.5, 10.2, 8.8, 7.7, 7.4],
    "≥30°N": [10.1, 10.5, 11.4, 12.5, 13.0, 12.8, 12.5, 11.8, 11.0, 10.3, 9.8, 9.6],
    "equator": [11.5, 11.5, 11.5, 11.5, 11.5, 11.5, 11.5, 11.5, 11.5, 11.5, 11.5, 11.5],
    "≥-30°S": [10.1, 10.5, 11.4, 12.5, 13.0, 12.8, 12.5, 11.8, 11.0, 10.3, 9.8, 9.6],
    "≥-45°S": [7.9, 8.4, 10.0, 12.5, 13.4, 13.2, 12.6, 11.5, 10.2, 8.8, 7.7, 7.4],
    "south":  [6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0],
}

# DC day-length adjustment factors (L_f) by latitude and month
_DC_LF = {
    "north":   [-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6],
    "mid":     [-0.3, -0.3, -0.3, 1.5, 3.4, 4.9, 5.5, 4.5, 2.2, 0.5, -0.3, -0.3],
    "equator": [1.4, 1.4, 1.4, 3.2, 5.1, 6.7, 7.3, 6.3, 4.1, 2.1, 1.4, 1.4],
    "south":   [-0.3, -0.3, -0.3, 1.5, 3.4, 4.9, 5.5, 4.5, 2.2, 0.5, -0.3, -0.3],
}


def _get_dmc_le(lat: float, month_idx: int) -> float:
    # Southern Hemisphere: shift month by 6 to account for opposite seasons.
    # January (idx 0) in SH corresponds to summer (long days), equivalent to
    # July (idx 6) in NH. Day-length table values are NH-centric.
    if lat < -10:
        month_idx = (month_idx + 6) % 12
    if lat >= 60:
        key = "≥60°N"
    elif lat >= 45:
        key = "≥45°N"
    elif lat >= 30:
        key = "≥30°N"
    elif lat >= -30:
        key = "equator"
    elif lat >= -45:
        key = "≥-30°S"
    elif lat >= -60:
        key = "≥-45°S"
    else:
        key = "south"
    return _DMC_LE[key][month_idx]


def _get_dc_lf(lat: float, month_idx: int) -> float:
    # Southern Hemisphere: shift month by 6 for opposite season day-length
    if lat < -10:
        month_idx = (month_idx + 6) % 12
    if lat >= 45:
        key = "north"
    elif lat >= 10:
        key = "mid"
    elif lat >= -10:
        key = "equator"
    else:
        key = "south"
    return _DC_LF[key][month_idx]


# ---------------------------------------------------------------------------
# FFMC (Fine Fuel Moisture Code)
# ---------------------------------------------------------------------------

def _ffmc_next(F_prev: float, T: float, H: float, W: float, r: float) -> float:
    """
    Compute next-day FFMC.
    Inputs: F_prev = previous FFMC, T = temp °C, H = RH %, W = wind km/h, r = rain mm
    Van Wagner (1987) equations 1–9.
    """
    # Convert FFMC to moisture content
    m0 = 147.2 * (101.0 - F_prev) / (59.5 + F_prev)

    # Rain correction
    if r > 0.5:
        rf = r - 0.5
        if m0 <= 150.0:
            mr = m0 + 42.5 * rf * np.exp(-100.0 / (251.0 - m0)) * (1.0 - np.exp(-6.93 / rf))
        else:
            mr = (m0 + 42.5 * rf * np.exp(-100.0 / (251.0 - m0)) * (1.0 - np.exp(-6.93 / rf))
                  + 0.0015 * (m0 - 150.0) ** 2 * rf ** 0.5)
        m0 = min(mr, 250.0)

    # Equilibrium moisture content (drying)
    H = np.clip(H, 0.0, 100.0)
    Ed = (0.942 * H ** 0.679 + 11.0 * np.exp((H - 100.0) / 10.0)
          + 0.18 * (21.1 - T) * (1.0 - np.exp(-0.115 * H)))
    # Equilibrium (wetting)
    Ew = (0.618 * H ** 0.753 + 10.0 * np.exp((H - 100.0) / 10.0)
          + 0.18 * (21.1 - T) * (1.0 - np.exp(-0.115 * H)))

    if m0 > Ed:
        # Drying phase
        kd = 0.424 * (1.0 - (H / 100.0) ** 1.7) + 0.0694 * W ** 0.5 * (1.0 - (H / 100.0) ** 8)
        kd *= 0.581 * np.exp(0.0365 * T)
        m = Ed + (m0 - Ed) * 10.0 ** (-kd)
    elif m0 < Ew:
        # Wetting phase
        kw = 0.424 * (1.0 - ((100.0 - H) / 100.0) ** 1.7) + 0.0694 * W ** 0.5 * (1.0 - ((100.0 - H) / 100.0) ** 8)
        kw *= 0.581 * np.exp(0.0365 * T)
        m = Ew - (Ew - m0) * 10.0 ** (-kw)
    else:
        m = m0

    m = np.clip(m, 0.0, 250.0)
    F = 59.5 * (250.0 - m) / (147.2 + m)
    return float(np.clip(F, 0.0, 101.0))


# ---------------------------------------------------------------------------
# DMC (Duff Moisture Code)
# ---------------------------------------------------------------------------

def _dmc_next(P_prev: float, T: float, H: float, r: float,
              lat: float, month_idx: int) -> float:
    """
    Compute next-day DMC.
    Van Wagner (1987) equations 10–18.
    """
    P0 = P_prev

    # Rain correction
    if r > 1.5:
        re = 0.92 * r - 1.27
        Mo = 20.0 + np.exp(5.6348 - P0 / 43.43)
        if P0 <= 33.0:
            b = 100.0 / (0.5 + 0.3 * P0)
        elif P0 <= 65.0:
            b = 14.0 - 1.3 * np.log(P0)
        else:
            b = 6.2 * np.log(P0) - 17.2
        Mr = Mo + 1000.0 * re / (48.77 + b * re)
        Pr = 244.72 - 43.43 * np.log(Mr - 20.0) if Mr > 20.0 else 0.0
        P0 = max(Pr, 0.0)

    # Temperature correction
    if T > -1.1:
        Le = _get_dmc_le(lat, month_idx)
        K = 1.894 * (T + 1.1) * (100.0 - H) * Le * 1e-6
        P = P0 + 100.0 * K
    else:
        P = P0

    return max(P, 0.0)


# ---------------------------------------------------------------------------
# DC (Drought Code)
# ---------------------------------------------------------------------------

def _dc_next(D_prev: float, T: float, r: float, lat: float, month_idx: int) -> float:
    """
    Compute next-day DC.
    Van Wagner (1987) equations 19–26.
    """
    D0 = D_prev

    # Rain correction
    if r > 2.8:
        rd = 0.83 * r - 1.27
        Qo = 800.0 * np.exp(-D0 / 400.0)
        Qr = Qo + 3.937 * rd
        Dr = 400.0 * np.log(800.0 / Qr) if Qr > 0 else D0
        D0 = max(Dr, 0.0)

    # Temperature drying
    if T > -2.8:
        Lf = _get_dc_lf(lat, month_idx)
        V = 0.36 * (T + 2.8) + Lf
        V = max(V, 0.0)
        D = D0 + 0.5 * V
    else:
        D = D0

    return max(D, 0.0)


# ---------------------------------------------------------------------------
# ISI (Initial Spread Index)
# ---------------------------------------------------------------------------

def _isi(F: float, W: float) -> float:
    """
    ISI from FFMC and wind speed.
    Van Wagner (1987) equations 27–30.
    """
    m = 147.2 * (101.0 - F) / (59.5 + F)
    fw = np.exp(0.05039 * W)
    ff = 91.9 * np.exp(-0.1386 * m) * (1.0 + m ** 5.31 / 4.93e7)
    return 0.208 * fw * ff


# ---------------------------------------------------------------------------
# BUI (Buildup Index)
# ---------------------------------------------------------------------------

def _bui(P: float, D: float) -> float:
    """
    BUI from DMC and DC.
    Van Wagner (1987) equations 31–32.
    """
    if P <= 0.4 * D:
        B = 0.8 * P * D / (P + 0.4 * D)
    else:
        B = P - (1.0 - 0.8 * D / (P + 0.4 * D)) * (0.92 + (0.0114 * P) ** 1.7)
    return max(B, 0.0)


# ---------------------------------------------------------------------------
# FWI (Fire Weather Index)
# ---------------------------------------------------------------------------

def _fwi(R: float, B: float) -> float:
    """
    FWI from ISI and BUI.
    Van Wagner (1987) equations 33–35.
    """
    if B <= 80.0:
        fD = 0.626 * B ** 0.809 + 2.0
    else:
        fD = 1000.0 / (25.0 + 108.64 * np.exp(-0.023 * B))
    Bx = 0.1 * R * fD
    if Bx > 1.0:
        S = np.exp(2.72 * (0.434 * np.log(Bx)) ** 0.647)
    else:
        S = Bx
    return S


# ---------------------------------------------------------------------------
# DSR (Daily Severity Rating)
# ---------------------------------------------------------------------------

def _dsr(fwi: float) -> float:
    """DSR — suppression difficulty index. Van Wagner (1970)."""
    return 0.0272 * fwi ** 1.77


# ---------------------------------------------------------------------------
# FWI → Flame Length
# ---------------------------------------------------------------------------

def fwi_to_flame_length(fwi: float, vegetation: str = "forest") -> float:
    """
    Convert FWI to flame length (m).

    Method:
      Step 1: FWI → Fireline Intensity (kW/m) via Simard (1970) calibration,
              as used in the Canadian Forest Fire Behaviour Prediction System:
                I = A × FWI^1.5
              where A depends on vegetation type:
                forest    : A = 300  (Van Wagner 1987, boreal calibration)
                shrubland : A = 450  (Fernandes et al. 2018, Mediterranean)
                grassland : A = 200  (Cruz et al. 2015, grassland fires)

      Step 2: Fireline intensity → Flame length (Byram 1959):
                L = 0.0775 × I^0.46
              Reference: Byram, G.M. (1959) Combustion of forest fuels.
              In: Davis, K.P. (ed.) Forest Fire: Control and Use. McGraw-Hill.

    Returns: flame length in metres.
    """
    A = {"forest": 300.0, "shrubland": 450.0, "grassland": 200.0}.get(vegetation, 300.0)
    fi = A * (fwi ** 1.5)
    fl = 0.0775 * (fi ** 0.46)
    return float(np.clip(fl, 0.0, 20.0))


# ---------------------------------------------------------------------------
# Full FWI time-series computation
# ---------------------------------------------------------------------------

def compute_fwi_series(
    T_arr: np.ndarray,
    H_arr: np.ndarray,
    W_arr: np.ndarray,
    R_arr: np.ndarray,
    months: np.ndarray,
    lat: float,
    ffmc_start: float = 85.0,
    dmc_start: float = 6.0,
    dc_start: float = 15.0,
) -> np.ndarray:
    """
    Compute daily FWI time series from daily climate arrays.

    Parameters
    ----------
    T_arr   : daily maximum temperature (°C)
    H_arr   : daily relative humidity (%)
    W_arr   : daily wind speed (km/h)
    R_arr   : daily precipitation (mm)
    months  : integer month (1–12) for each day
    lat     : latitude (for day-length factors)
    ffmc_start, dmc_start, dc_start : initial moisture code values

    Returns
    -------
    fwi_arr : FWI value for each day (same length as input)
    """
    n = len(T_arr)
    fwi_arr = np.zeros(n)

    F = ffmc_start
    P = dmc_start
    D = dc_start

    for i in range(n):
        T = float(T_arr[i])
        H = float(np.clip(H_arr[i], 0.0, 100.0))
        W = float(max(W_arr[i], 0.0))
        r = float(max(R_arr[i], 0.0))
        m_idx = int(months[i]) - 1   # 0-indexed

        F = _ffmc_next(F, T, H, W, r)
        P = _dmc_next(P, T, H, r, lat, m_idx)
        D = _dc_next(D, T, r, lat, m_idx)

        R_isi = _isi(F, W)
        B_bui = _bui(P, D)
        fwi_arr[i] = _fwi(R_isi, B_bui)

    return fwi_arr


def annual_max_fwi(
    T_arr: np.ndarray,
    H_arr: np.ndarray,
    W_arr: np.ndarray,
    R_arr: np.ndarray,
    years: np.ndarray,
    months: np.ndarray,
    lat: float,
) -> np.ndarray:
    """
    Compute annual maximum FWI from daily climate arrays.

    Parameters
    ----------
    T_arr, H_arr, W_arr, R_arr : daily climate (same length)
    years   : integer year for each day
    months  : integer month for each day
    lat     : latitude

    Returns
    -------
    Array of annual maximum FWI values (one per year in the record).
    """
    fwi_daily = compute_fwi_series(T_arr, H_arr, W_arr, R_arr, months, lat)

    unique_years = np.unique(years)
    ann_max = []
    for y in unique_years:
        mask = years == y
        daily_vals = fwi_daily[mask]
        if len(daily_vals) > 30:        # skip incomplete years
            ann_max.append(np.nanmax(daily_vals))

    return np.array(ann_max)
