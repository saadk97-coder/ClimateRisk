"""
High-resolution Layer-3: multi-regional (MRIO) network propagation with an optional
Reisch-et-al.-style endogenous-default cascade.

Uses the 20-sector × 49-region EXIOBASE-3 matrix (io_matrix_mrio.npz). Cross-region
supply chains are explicit, and each region's sectors pay carbon on that region's
NGFS price band — so, e.g., an EU refiner's indirect cost reflects emerging-market
upstream facing a lower carbon price.

Endogenous default (Reisch, Diem, Pichler, Stangl, Thurner 2025, arXiv:2503.10644):
beyond the linear Leontief cascade, nodes whose absorbed input-cost shock exceeds a
default threshold θ pass an amplified shock downstream (contagion), iterated to
convergence. Off by default (linear = the standard screening result).
"""

from __future__ import annotations
from functools import lru_cache
from typing import Dict, List, Tuple
import json
import os

import numpy as np

from engine.transition.carbon_pricing import get_carbon_price
from engine.transition.data_loader import load_sector_taxonomy, load_sector_pass_through
from engine.transition.network_propagation import NetworkShockResult

_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "transition"))

# EXIOBASE region (ISO2 + 5 RoW) → NGFS carbon-price band.
_ADV = {"AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR", "HR",
        "HU", "IE", "IT", "LT", "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI",
        "SK", "GB", "US", "JP", "CA", "KR", "AU", "CH", "TW", "NO"}
_EME = {"CN", "IN", "BR", "MX", "RU", "TR", "ID", "ZA"}


def _exio_band(code: str) -> str:
    if code in _ADV:
        return "advanced"
    if code in _EME:
        return "emerging"
    return "rest_of_world"


# ISO3 (asset input) → EXIOBASE region code, for the 44 individually-modelled countries.
_ISO3_TO_EXIO = {
    "AUT": "AT", "BEL": "BE", "BGR": "BG", "CYP": "CY", "CZE": "CZ", "DEU": "DE",
    "DNK": "DK", "EST": "EE", "ESP": "ES", "FIN": "FI", "FRA": "FR", "GRC": "GR",
    "HRV": "HR", "HUN": "HU", "IRL": "IE", "ITA": "IT", "LTU": "LT", "LUX": "LU",
    "LVA": "LV", "MLT": "MT", "NLD": "NL", "POL": "PL", "PRT": "PT", "ROU": "RO",
    "SWE": "SE", "SVN": "SI", "SVK": "SK", "GBR": "GB", "USA": "US", "JPN": "JP",
    "CHN": "CN", "CAN": "CA", "KOR": "KR", "BRA": "BR", "IND": "IN", "MEX": "MX",
    "RUS": "RU", "AUS": "AU", "CHE": "CH", "TUR": "TR", "TWN": "TW", "NOR": "NO",
    "IDN": "ID", "ZAF": "ZA",
}
# RoW aggregate by NGFS band for unmatched ISO3.
_ROW_BY_BAND = {"advanced": "WE", "emerging": "WA", "rest_of_world": "WF"}


def iso3_to_exio(iso3: str, ngfs_band: str = "rest_of_world") -> str:
    return _ISO3_TO_EXIO.get((iso3 or "").upper(), _ROW_BY_BAND.get(ngfs_band, "WA"))


@lru_cache(maxsize=1)
def _load_mrio() -> Tuple[np.ndarray, tuple, tuple]:
    A = np.load(os.path.join(_DIR, "io_matrix_mrio.npz"))["A"].astype(np.float64)
    meta = json.load(open(os.path.join(_DIR, "io_matrix_mrio_meta.json")))["_meta"]
    return A, tuple(meta["sector_order"]), tuple(meta["region_order"])


@lru_cache(maxsize=4)
def get_mrio_leontief(elasticity: float = 1.0) -> Tuple[np.ndarray, tuple, tuple]:
    A, sectors, regions = _load_mrio()
    if elasticity != 1.0:
        diag = np.diag(A).copy()
        A = A / max(elasticity, 1e-6)
        np.fill_diagonal(A, diag)
    n = A.shape[0]
    L = np.linalg.inv(np.eye(n) - A)
    return L, sectors, regions


def build_mrio_shock(scenario_id: str, year: int,
                     price_scale: float = 1.0, pass_through_scale: float = 1.0) -> np.ndarray:
    """980-vector: shock_{region r, sector i} = EI_i × price(band(r)) × PT_i × 1e-6.

    price_scale / pass_through_scale are the Monte-Carlo / sensitivity multipliers so
    the MRIO L3 responds to the same perturbations as the world L3 and L1 (bug fix)."""
    _, sectors, regions = _load_mrio()
    tax = load_sector_taxonomy()["sectors"]
    spt = load_sector_pass_through()["sectors"]
    ei = np.array([float(tax.get(s, {}).get("emission_intensity_t_per_revenue", 0.0)) for s in sectors])
    pt = np.array([float(spt.get(s, {"pass_through": 0.4})["pass_through"]) for s in sectors])
    pt = np.clip(pt * max(0.0, pass_through_scale), 0.0, 1.0)
    # price per region band (cache per band within this call)
    band_price = {b: get_carbon_price(scenario_id, year, b) * max(0.0, price_scale)
                  for b in ("advanced", "emerging", "rest_of_world")}
    s = np.empty(len(regions) * len(sectors))
    for r_i, r in enumerate(regions):
        price = band_price[_exio_band(r)]
        # Clamp each sector shock to 1.0 (see network_propagation.build_sectorwide_shock):
        # carbon cost cannot inflate output price >100% in the linear basis.
        s[r_i * len(sectors):(r_i + 1) * len(sectors)] = np.minimum(1.0, ei * price * pt * 1e-6)
    return s


def _cascade(L: np.ndarray, s: np.ndarray, theta: float, contagion: float,
             max_iter: int = 8) -> np.ndarray:
    """Reisch-style endogenous default: nodes absorbing > θ pass an amplified shock
    downstream; iterate the extra direct shock to convergence."""
    s_eff = s.copy()
    for _ in range(max_iter):
        total = L @ s_eff
        over = np.maximum(0.0, total - theta)
        if over.max() < 1e-9:
            break
        s_eff = s + contagion * over
    return s_eff


def propagate_mrio(
    asset_id: str, sector: str, region_iso3: str, ngfs_band: str,
    scenario_id: str, year: int, asset_revenue: float,
    elasticity: float = 1.0, cascade: bool = False,
    cascade_theta: float = 0.5, cascade_contagion: float = 0.5,
    absorption: float = 1.0, price_scale: float = 1.0, pass_through_scale: float = 1.0,
    input_share: float = 1.0,
) -> NetworkShockResult:
    L, sectors, regions = get_mrio_leontief(elasticity)
    n_sec = len(sectors)
    if sector not in sectors:   # added-after-matrix sector → io_proxy row, else services
        from engine.transition.data_loader import load_sector_taxonomy
        _proxy = load_sector_taxonomy()["sectors"].get(sector, {}).get("io_proxy")
        sector = _proxy if _proxy in sectors else "services"
    r_code = iso3_to_exio(region_iso3, ngfs_band)
    r_i = regions.index(r_code) if r_code in regions else regions.index("WA")
    s_i = sectors.index(sector)
    j = r_i * n_sec + s_i

    s = build_mrio_shock(scenario_id, year, price_scale=price_scale,
                         pass_through_scale=pass_through_scale)
    s_eff = _cascade(L, s, cascade_theta, cascade_contagion) if cascade else s

    col = L[:, j]
    total_shock = float(col @ s_eff)
    own = float(s_eff[j])   # P3 — subtract only the direct round already in L1, not L[j,j]·s_j
    propagated = max(0.0, total_shock - own)
    absorption = max(0.0, min(1.0, absorption))   # R2 — share absorbed vs passed downstream
    input_share = max(0.0, min(1.0, input_share))  # carbon-exposed input base = revenue × input_share
    indirect_usd = propagated * max(asset_revenue, 0.0) * input_share * absorption

    # top upstream sources aggregated by SECTOR (summed across regions)
    contrib = col * s_eff
    by_sector: Dict[str, float] = {}
    for idx in range(len(contrib)):
        if idx == j or contrib[idx] <= 0:
            continue
        by_sector[sectors[idx % n_sec]] = by_sector.get(sectors[idx % n_sec], 0.0) + float(contrib[idx])
    top5 = sorted(by_sector.items(), key=lambda kv: kv[1], reverse=True)[:5]

    note = f"MRIO 20×49 (EXIOBASE); focal region {r_code}"
    if cascade:
        note += f"; endogenous-default cascade (θ={cascade_theta}, contagion={cascade_contagion})"
    return NetworkShockResult(
        asset_id=asset_id, sector=sector, scenario_id=scenario_id, year=year,
        sectoral_shock_vector={},  # 980-dim omitted for compactness
        direct_carbon_shock=round(own, 6),
        propagated_input_shock=round(propagated, 6),
        total_indirect_cost_usd=round(indirect_usd, 2),
        top_upstream_sources=[(sec, round(c * max(asset_revenue, 0.0) * input_share * absorption, 2)) for sec, c in top5],
        notes=note,
    )
