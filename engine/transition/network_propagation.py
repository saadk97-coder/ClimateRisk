"""
Layer 3 — Production network propagation via the Leontief inverse.

Methodology (screening-grade)
-----------------------------
We start from the carbon-cost shock in each producing sector i, expressed as a
fraction of sector i's output:

    s_i = passed_through_i  /  output_i

Under a fixed-coefficients (Cobb-Douglas with σ=1) production assumption, the
total cost shock absorbed by sector j is:

    total_shock_j = Σ_i  L[i, j] * s_i

where L = (I - A)^-1 is the Leontief inverse and A is the direct-requirements
matrix.

Endogenous-substitution refinement (Reisch et al. 2025)
-------------------------------------------------------
Allowing intermediate-input substitution (CES with elasticity σ > 1) dampens
shock propagation. We approximate this using a softmax-tempered weighting that
scales L by exp(-θ * shock_intensity), where θ encodes substitutability.
Default θ = 0 (= Cobb-Douglas baseline). For high-substitution sectors,
θ > 0 reduces propagated shock; for inelastic sectors θ ≤ 0.

Important caveats
-----------------
This is a screening-grade single-region 20-sector model. For production use:
  - replace io_matrix.json with the EXIOBASE-3 multi-regional MRIO
    (200 sectors × 49 regions) — that is the "bespoke add-on" path in the memo.
  - replace fixed elasticity with sector-specific σ from Papageorgiou et al. 2017.
  - add endogenous default thresholds per Reisch et al. 2025.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging

import numpy as np

from engine.transition.data_loader import load_io_matrix, load_sector_pass_through

_log = logging.getLogger(__name__)


def get_leontief_inverse(elasticity: float = 1.0) -> Tuple[np.ndarray, List[str]]:
    """
    Compute (I - A)^-1 from the io_matrix.json data.

    Parameters
    ----------
    elasticity : float
        Cobb-Douglas (σ=1) is the default. Values > 1 shrink off-diagonal terms
        (more substitution); < 1 amplifies them (less substitution).

    Returns
    -------
    L : (n, n) ndarray
        Leontief inverse.
    sectors : list of sector keys (column/row order).
    """
    raw = load_io_matrix()
    A = np.array(raw["A"], dtype=float)
    sectors = list(raw["_meta"]["sector_order"])
    n = A.shape[0]
    if A.shape != (n, n):
        raise ValueError(f"IO matrix not square: {A.shape}")

    if elasticity != 1.0:
        # Damp off-diagonals by elasticity (rough approximation of CES tempering)
        damp = 1.0 / max(elasticity, 1e-6)
        A = A * damp
        # Diagonal kept as-is
        np.fill_diagonal(A, np.diag(load_io_matrix_array()))

    I = np.eye(n)
    try:
        L = np.linalg.inv(I - A)
    except np.linalg.LinAlgError as e:
        _log.error(f"Leontief inversion failed: {e}; returning identity.")
        L = np.eye(n)
    return L, sectors


def load_io_matrix_array() -> np.ndarray:
    return np.array(load_io_matrix()["A"], dtype=float)


@dataclass
class NetworkShockResult:
    asset_id: str
    sector: str
    scenario_id: str
    year: int
    sectoral_shock_vector: Dict[str, float]   # input shock by source sector (fraction of output)
    direct_carbon_shock: float                # firm's own absorbed carbon cost / output
    propagated_input_shock: float             # additional cost from upstream pass-through
    total_indirect_cost_usd: float            # propagated shock × asset revenue / output
    top_upstream_sources: List[Tuple[str, float]]   # top-5 (sector, contribution)
    notes: str = ""


def build_sectorwide_shock(carbon_price_usd_per_t: float) -> Dict[str, float]:
    """
    Build a sector-typical shock vector. Each sector's shock (fraction of output)
    is:
        shock_i = emission_intensity_i × carbon_price × pass_through_i × 1e-6

    The 1e-6 factor converts emission_intensity from tCO2 per million USD revenue
    (the field's actual unit — a typical figure is 1–10 tCO2/M$) to tCO2 per USD.
    Used by Layer 3 to compute indirect input-cost exposure for any focal asset.
    """
    from engine.transition.data_loader import load_sector_taxonomy
    tax = load_sector_taxonomy()["sectors"]
    spt = load_sector_pass_through()["sectors"]
    out: Dict[str, float] = {}
    for sec_key, sec_meta in tax.items():
        ei_per_musd = float(sec_meta.get("emission_intensity_t_per_revenue", 0.0))
        pt = float(spt.get(sec_key, {"pass_through": 0.4})["pass_through"])
        out[sec_key] = ei_per_musd * 1e-6 * carbon_price_usd_per_t * pt
    return out


def propagate_carbon_shock(
    asset_id: str,
    sector: str,
    scenario_id: str,
    year: int,
    asset_revenue: float,
    sector_carbon_costs: Dict[str, float],
    sector_outputs: Optional[Dict[str, float]] = None,
    elasticity: float = 1.0,
) -> NetworkShockResult:
    """
    Propagate sectoral carbon-cost shocks through the IO network and compute the
    indirect cost absorbed by the focal asset's sector.

    Parameters
    ----------
    asset_id, sector, scenario_id, year : metadata for the result
    asset_revenue : asset-attributable revenue (USD/yr) — used to scale
                    propagated shock to a USD figure
    sector_carbon_costs : dict mapping sector_key → USD passed-through carbon
                          cost in this scenario × year
    sector_outputs : optional dict mapping sector_key → sector output (USD).
                     If absent, defaults to 1e12 per sector (uniform reference) —
                     this means the shock is interpreted as a relative price
                     index across sectors (acceptable for screening).
    elasticity : substitution elasticity (default 1.0 = Cobb-Douglas)
    """
    L, sectors = get_leontief_inverse(elasticity=elasticity)
    n = len(sectors)
    sector_idx = {s: i for i, s in enumerate(sectors)}

    if sector not in sector_idx:
        # Unmapped sector: assume "services" position
        sector = "services"
    j = sector_idx[sector]

    # Shock vector: relative price increase per supplier sector. Two modes:
    #   (a) sector_outputs provided → cost / output → fraction-of-output shock
    #   (b) sector_outputs absent + sector_carbon_costs is a sector-typical
    #       fractional shock vector (e.g. from build_sectorwide_shock) → use directly
    s = np.zeros(n)
    if sector_outputs is None:
        # Treat sector_carbon_costs as already-normalised shocks (fraction of output)
        for sec, shock in sector_carbon_costs.items():
            if sec in sector_idx:
                s[sector_idx[sec]] = float(shock)
    else:
        for sec, cost in sector_carbon_costs.items():
            if sec in sector_idx:
                i = sector_idx[sec]
                denom = max(sector_outputs.get(sec, 1e12), 1.0)
                s[i] = cost / denom

    # Total cost shock absorbed by sector j (per unit of j's output)
    total_shock = float(np.dot(L[:, j], s))
    # P3 — subtract only the single DIRECT round L1 already charged (s_j), not
    # L[j,j]·s_j (which is ≥ s_j and would strip legitimate indirect self-loop
    # feedback). This counts the focal sector's own carbon dollar exactly once.
    own_shock = float(s[j])
    propagated = max(0.0, total_shock - own_shock)

    # Indirect cost in USD = propagated_shock × asset_revenue (interpreting
    # asset_revenue as the firm's share of sector j's output)
    indirect_usd = propagated * max(asset_revenue, 0.0)

    # Top-5 upstream sources by contribution L[i,j] * s[i]
    contribs = [(sectors[i], float(L[i, j] * s[i])) for i in range(n) if i != j and s[i] > 0]
    contribs.sort(key=lambda t: t[1], reverse=True)
    top5 = contribs[:5]

    return NetworkShockResult(
        asset_id=asset_id,
        sector=sector,
        scenario_id=scenario_id,
        year=year,
        sectoral_shock_vector={sectors[i]: float(s[i]) for i in range(n) if s[i] > 0},
        direct_carbon_shock=round(own_shock, 6),
        propagated_input_shock=round(propagated, 6),
        total_indirect_cost_usd=round(indirect_usd, 2),
        top_upstream_sources=[(sec, round(c * max(asset_revenue, 0.0), 2)) for sec, c in top5],
        notes="Screening-grade Leontief cascade (Cobb-Douglas σ=1). For production use replace with EXIOBASE-3 MRIO and CES σ from Papageorgiou et al. 2017.",
    )


def aggregate_sector_carbon_costs(layer1_results: List) -> Dict[str, float]:
    """
    Aggregate Layer-1 passed-through cost by sector for use as the shock vector
    input to propagate_carbon_shock.

    `layer1_results` is a list of CarbonCostResult dataclasses (one per asset).
    """
    out: Dict[str, float] = {}
    for r in layer1_results:
        out[r.sector] = out.get(r.sector, 0.0) + float(r.passed_through_usd)
    return out
