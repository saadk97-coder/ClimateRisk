"""
Tropical cyclone / hurricane exposure and wind amplification module.

Determines whether an asset is within a tropical cyclone basin and computes
cyclone-adjusted wind hazard intensities for exposed locations.

Cyclone basins and historical track data are based on:
  • IBTrACS (International Best Track Archive for Climate Stewardship)
    Knapp et al. (2010) Bulletin of the AMS, 91(3), 363–376
    https://doi.org/10.1175/2009BAMS2755.1
    https://www.ncei.noaa.gov/products/international-best-track-archive

Wind profile model:
  • Holland (1980) "An Analytic Model of the Wind and Pressure Profiles
    in Hurricanes", Monthly Weather Review, 108(8), 1212–1218.
    https://doi.org/10.1175/1520-0493(1980)108<1212:AAMOTW>2.0.CO;2

Climate scaling:
  • Knutson et al. (2020) "Tropical Cyclones and Climate Change Assessment:
    Part II", BAMS, 101(3), E303–E322.
    https://doi.org/10.1175/BAMS-D-18-0194.1
    Key finding: ~5% increase in peak TC wind speed per +2°C warming.

Saffir-Simpson Hurricane Wind Scale (NOAA):
  https://www.nhc.noaa.gov/aboutsshws.php
"""

import math
import json
import os
import numpy as np
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Saffir-Simpson Hurricane Wind Scale (3-second gust, m/s)
# Source: NOAA NHC https://www.nhc.noaa.gov/aboutsshws.php
# Sustained winds converted to 3-s gust using WMO 1.5× factor
# ---------------------------------------------------------------------------
SAFFIR_SIMPSON = [
    {"category": "TD",   "label": "Tropical Depression",  "sustained_kt": (0, 33),   "gust_ms": (0, 25.5)},
    {"category": "TS",   "label": "Tropical Storm",       "sustained_kt": (34, 63),  "gust_ms": (25.5, 48.6)},
    {"category": "Cat 1", "label": "Category 1 Hurricane", "sustained_kt": (64, 82),  "gust_ms": (48.6, 63.3)},
    {"category": "Cat 2", "label": "Category 2 Hurricane", "sustained_kt": (83, 95),  "gust_ms": (63.3, 73.3)},
    {"category": "Cat 3", "label": "Category 3 (Major)",   "sustained_kt": (96, 112), "gust_ms": (73.3, 86.4)},
    {"category": "Cat 4", "label": "Category 4 (Major)",   "sustained_kt": (113, 136),"gust_ms": (86.4, 104.9)},
    {"category": "Cat 5", "label": "Category 5 (Major)",   "sustained_kt": (137, 999),"gust_ms": (104.9, 200.0)},
]


def classify_saffir_simpson(wind_speed_ms: float) -> dict:
    """Classify a 3-second gust wind speed (m/s) on the Saffir-Simpson scale."""
    for cat in reversed(SAFFIR_SIMPSON):
        if wind_speed_ms >= cat["gust_ms"][0]:
            return cat
    return SAFFIR_SIMPSON[0]


# ---------------------------------------------------------------------------
# Tropical cyclone basins
# Source: IBTrACS basin definitions (WMO Regional Specialized Meteorological Centres)
# https://www.ncei.noaa.gov/products/international-best-track-archive
# ---------------------------------------------------------------------------
CYCLONE_BASINS: Dict[str, dict] = {
    "NA": {
        "name": "North Atlantic",
        "full_name": "North Atlantic Hurricane Basin",
        "bounds": {"lat": (5, 50), "lon": (-100, -10)},
        "season": "Jun–Nov",
        "peak": "Aug–Oct",
        "avg_annual_storms": 14,
        "avg_annual_hurricanes": 7,
        "rsmcs": ["NHC (Miami)"],
        "color": "#e74c3c",
    },
    "EP": {
        "name": "Eastern Pacific",
        "full_name": "Eastern North Pacific Basin",
        "bounds": {"lat": (5, 35), "lon": (-180, -98)},
        "season": "May–Nov",
        "peak": "Jul–Sep",
        "avg_annual_storms": 17,
        "avg_annual_hurricanes": 9,
        "rsmcs": ["NHC (Miami)", "CPHC (Honolulu)"],
        "color": "#e67e22",
    },
    "WP": {
        "name": "Western Pacific",
        "full_name": "Western North Pacific Typhoon Basin",
        "bounds": {"lat": (5, 40), "lon": (100, 180)},
        "season": "Year-round (peak Jul–Nov)",
        "peak": "Aug–Oct",
        "avg_annual_storms": 26,
        "avg_annual_hurricanes": 16,
        "rsmcs": ["JMA (Tokyo)"],
        "color": "#9b59b6",
    },
    "NI": {
        "name": "North Indian",
        "full_name": "North Indian Ocean Cyclone Basin",
        "bounds": {"lat": (5, 30), "lon": (45, 100)},
        "season": "Apr–Jun, Oct–Dec (bimodal)",
        "peak": "May, Nov",
        "avg_annual_storms": 12,
        "avg_annual_hurricanes": 5,
        "rsmcs": ["IMD (New Delhi)"],
        "color": "#f39c12",
    },
    "SI": {
        "name": "South Indian",
        "full_name": "South-West Indian Ocean Cyclone Basin",
        "bounds": {"lat": (-35, -5), "lon": (30, 90)},
        "season": "Nov–Apr",
        "peak": "Jan–Mar",
        "avg_annual_storms": 12,
        "avg_annual_hurricanes": 7,
        "rsmcs": ["Météo-France (Réunion)"],
        "color": "#1abc9c",
    },
    "SP": {
        "name": "South Pacific",
        "full_name": "South Pacific / Australian Region",
        "bounds": {"lat": (-35, -5), "lon": (90, 180)},
        "season": "Nov–Apr",
        "peak": "Jan–Mar",
        "avg_annual_storms": 10,
        "avg_annual_hurricanes": 5,
        "rsmcs": ["BoM (Melbourne)", "NZMS (Wellington)", "FMS (Nadi)"],
        "color": "#3498db",
    },
    "SA": {
        "name": "South Atlantic",
        "full_name": "South Atlantic (rare cyclones)",
        "bounds": {"lat": (-35, -5), "lon": (-40, 0)},
        "season": "Rare",
        "peak": "—",
        "avg_annual_storms": 0.3,
        "avg_annual_hurricanes": 0.1,
        "rsmcs": ["Brazilian Navy (CPTEC)"],
        "color": "#95a5a6",
    },
}


def get_cyclone_basin(lat: float, lon: float) -> Optional[str]:
    """
    Determine which tropical cyclone basin a location falls in.

    Returns basin code (e.g. 'NA', 'WP') or None if outside all basins.
    Uses IBTrACS basin boundary definitions.
    Checks narrower (more specific) basins first to resolve overlaps.
    """
    # Check order: more specific basins first (narrower lat/lon range)
    _PRIORITY = ["EP", "SA", "NI", "SI", "SP", "WP", "NA"]
    for code in _PRIORITY:
        basin = CYCLONE_BASINS[code]
        b = basin["bounds"]
        lat_range = b["lat"]
        lon_range = b["lon"]
        if lat_range[0] <= lat <= lat_range[1] and lon_range[0] <= lon <= lon_range[1]:
            return code
    return None


def is_cyclone_exposed(lat: float, lon: float) -> bool:
    """Return True if the location is within any tropical cyclone basin."""
    return get_cyclone_basin(lat, lon) is not None


# ---------------------------------------------------------------------------
# Representative historical cyclone tracks per basin
# Based on IBTrACS notable storms — simplified to key waypoints
# Source: https://www.ncei.noaa.gov/products/international-best-track-archive
# ---------------------------------------------------------------------------
_TRACKS: Optional[Dict] = None


def _load_tracks() -> Dict:
    """Load representative cyclone tracks from JSON data file."""
    global _TRACKS
    if _TRACKS is not None:
        return _TRACKS
    path = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "data", "cyclone_tracks.json")
    )
    try:
        with open(path) as f:
            _TRACKS = json.load(f)
    except FileNotFoundError:
        _TRACKS = {}
    return _TRACKS


def get_basin_tracks(basin_code: str) -> List[dict]:
    """Return list of representative tracks for a given basin."""
    tracks = _load_tracks()
    return tracks.get(basin_code, [])


def get_all_tracks() -> Dict[str, List[dict]]:
    """Return all representative tracks keyed by basin code."""
    return _load_tracks()


# ---------------------------------------------------------------------------
# Holland (1980) radial wind profile model
# ---------------------------------------------------------------------------

def holland_wind_profile(
    r_km: float,
    r_max_km: float,
    v_max_ms: float,
    lat: float = 25.0,
    p_central_hpa: float = 960.0,
    p_env_hpa: float = 1013.25,
) -> float:
    """
    Compute gradient wind speed at radius r from storm centre.

    Holland (1980) parametric hurricane wind model:
      V(r) = sqrt( B * (r_max/r)^B * (p_env - p_central) * exp(-(r_max/r)^B) / rho
                   + (r*f/2)^2 ) - r*f/2

    Parameters
    ----------
    r_km         : Distance from storm centre (km)
    r_max_km     : Radius of maximum wind (km), typically 20–60 km
    v_max_ms     : Maximum sustained wind at r_max (m/s)
    lat          : Latitude (for Coriolis parameter)
    p_central_hpa: Central pressure (hPa)
    p_env_hpa    : Environmental pressure (hPa)

    Returns
    -------
    Gradient wind speed (m/s) at distance r.

    Reference
    ---------
    Holland (1980) Mon. Wea. Rev., 108(8), 1212–1218.
    https://doi.org/10.1175/1520-0493(1980)108<1212:AAMOTW>2.0.CO;2
    """
    if r_km <= 0:
        return 0.0

    rho = 1.15  # air density (kg/m³)
    f = 2 * 7.2921e-5 * math.sin(math.radians(abs(lat)))  # Coriolis

    dp = (p_env_hpa - p_central_hpa) * 100.0  # Pa
    if dp <= 0:
        dp = 5000.0  # fallback ~50 hPa drop

    # Estimate Holland B parameter from v_max
    # B = v_max² * rho * e / dp  (Holland 1980 eq. 5)
    e = math.e
    B = v_max_ms ** 2 * rho * e / dp
    B = max(1.0, min(2.5, B))  # typical range

    r_ratio = r_max_km / r_km
    r_m = r_km * 1000.0  # convert to metres

    term1 = B * (r_ratio ** B) * dp * math.exp(-(r_ratio ** B)) / rho
    term2 = (r_m * f / 2) ** 2

    v_gradient = math.sqrt(max(0.0, term1 + term2)) - r_m * f / 2
    return max(0.0, v_gradient)


def cyclone_wind_at_distance(
    dist_km: float,
    max_wind_ms: float,
    r_max_km: float = 40.0,
    lat: float = 25.0,
) -> float:
    """
    Simplified wrapper: get wind speed at a distance from a cyclone track point.

    Returns 3-second gust speed (m/s) using Holland profile × WMO 1.5 gust factor.
    """
    gradient_wind = holland_wind_profile(
        r_km=max(dist_km, 1.0),
        r_max_km=r_max_km,
        v_max_ms=max_wind_ms,
        lat=lat,
    )
    # Boundary layer reduction: surface wind ≈ 0.75× gradient wind (Powell et al. 2003)
    surface_sustained = gradient_wind * 0.75
    # WMO gust factor: 3-second gust ≈ 1.5× 1-minute sustained
    gust_ms = surface_sustained * 1.5
    return gust_ms


# ---------------------------------------------------------------------------
# Cyclone exposure scoring and wind amplification
# ---------------------------------------------------------------------------

def cyclone_amplification_factor(
    lat: float,
    lon: float,
    basin_code: Optional[str] = None,
) -> float:
    """
    Return a wind intensity amplification factor for cyclone-exposed locations.

    Assets within tropical cyclone basins experience higher extreme wind speeds
    due to TC activity. This factor scales the baseline wind hazard intensities
    at high return periods (RP100+) to account for cyclone contribution.

    The amplification varies by basin based on historical TC frequency and intensity:
      NA (Atlantic):   1.25  — frequent major hurricanes
      EP (E. Pacific): 1.15  — mostly offshore
      WP (W. Pacific): 1.35  — most active basin globally
      NI (N. Indian):  1.30  — Bay of Bengal very intense
      SI (S. Indian):  1.20
      SP (S. Pacific): 1.20
      SA (S. Atlantic): 1.05

    Sources:
      Knutson et al. (2020) BAMS — TC frequency/intensity by basin
      Emanuel (2005) Nature 436, 686–688 — TC power dissipation trends
    """
    if basin_code is None:
        basin_code = get_cyclone_basin(lat, lon)
    if basin_code is None:
        return 1.0

    _BASIN_AMPLIFICATION = {
        "NA": 1.25,
        "EP": 1.15,
        "WP": 1.35,
        "NI": 1.30,
        "SI": 1.20,
        "SP": 1.20,
        "SA": 1.05,
    }
    return _BASIN_AMPLIFICATION.get(basin_code, 1.0)


def get_cyclone_wind_intensities(
    lat: float,
    lon: float,
    base_wind_rps: np.ndarray,
    base_wind_intensities: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, Optional[str]]:
    """
    Compute cyclone-adjusted wind intensities.

    For assets within a TC basin, amplifies higher return period wind speeds
    to account for tropical cyclone contribution. Lower return periods
    (RP10, RP50) see less amplification as they represent non-TC wind events.

    Parameters
    ----------
    lat, lon : Asset coordinates
    base_wind_rps : Return periods from wind hazard fetch
    base_wind_intensities : Baseline wind speeds (m/s, 3-s gust)

    Returns
    -------
    (return_periods, adjusted_intensities, basin_code)
    basin_code is None if not in a TC basin.
    """
    basin = get_cyclone_basin(lat, lon)
    if basin is None:
        return base_wind_rps, base_wind_intensities, None

    amp = cyclone_amplification_factor(lat, lon, basin)

    # Progressive amplification: scale increases with return period
    # RP10: minimal TC contribution, RP1000: full TC contribution
    rp_scale = {
        10: 1.0 + (amp - 1.0) * 0.1,     # ~2.5% boost at RP10
        50: 1.0 + (amp - 1.0) * 0.3,     # ~7.5% boost at RP50
        100: 1.0 + (amp - 1.0) * 0.6,    # ~15% boost at RP100
        250: 1.0 + (amp - 1.0) * 0.8,    # ~20% boost at RP250
        500: amp,                          # full amplification at RP500
        1000: amp * 1.05,                  # slightly above at RP1000
    }

    adjusted = base_wind_intensities.copy()
    for i, rp in enumerate(base_wind_rps):
        rp_int = int(rp)
        scale = rp_scale.get(rp_int, amp)
        adjusted[i] = base_wind_intensities[i] * scale

    return base_wind_rps, adjusted, basin


def nearest_track_distance_km(
    lat: float,
    lon: float,
    track: dict,
) -> float:
    """
    Compute minimum distance (km) from a location to any point on a cyclone track.
    """
    waypoints = track.get("waypoints", [])
    if not waypoints:
        return float("inf")

    min_dist = float("inf")
    for wp in waypoints:
        dlat = math.radians(wp["lat"] - lat)
        dlon = math.radians(wp["lon"] - lon)
        cos_lat = math.cos(math.radians(lat))
        approx = 6371.0 * math.sqrt(dlat ** 2 + (dlon * cos_lat) ** 2)
        if approx < min_dist:
            min_dist = approx

    return min_dist


def get_cyclone_exposure_summary(lat: float, lon: float) -> Optional[dict]:
    """
    Return a summary of cyclone exposure for a location.

    Returns None if outside all basins. Otherwise returns dict with:
      basin_code, basin_name, season, peak, avg_storms, avg_hurricanes,
      amplification_factor, saffir_simpson_context, nearest_tracks
    """
    basin_code = get_cyclone_basin(lat, lon)
    if basin_code is None:
        return None

    basin = CYCLONE_BASINS[basin_code]
    amp = cyclone_amplification_factor(lat, lon, basin_code)

    # Find nearest historical tracks
    tracks = get_basin_tracks(basin_code)
    track_distances = []
    for track in tracks:
        dist = nearest_track_distance_km(lat, lon, track)
        track_distances.append({
            "name": track.get("name", "Unknown"),
            "year": track.get("year", ""),
            "category": track.get("category", ""),
            "max_wind_kt": track.get("max_wind_kt", 0),
            "distance_km": round(dist, 0),
        })
    track_distances.sort(key=lambda x: x["distance_km"])

    return {
        "basin_code": basin_code,
        "basin_name": basin["name"],
        "full_name": basin["full_name"],
        "season": basin["season"],
        "peak": basin["peak"],
        "avg_annual_storms": basin["avg_annual_storms"],
        "avg_annual_hurricanes": basin["avg_annual_hurricanes"],
        "amplification_factor": amp,
        "basin_color": basin["color"],
        "nearest_tracks": track_distances[:5],  # top 5 nearest
    }
