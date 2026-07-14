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

Substitution damping (screening approximation)
-----------------------------------------------
Allowing intermediate-input substitution (CES with elasticity σ > 1) dampens
shock propagation. We approximate this by scaling the OFF-DIAGONAL direct-
requirements coefficients by 1/σ before inverting (diagonal preserved): σ = 1 is
the Cobb-Douglas baseline, σ > 1 shrinks off-diagonals (more substitution → less
propagation), σ < 1 amplifies them. (The full Reisch et al. 2025 endogenous-default
cascade is a separate, opt-in mechanism in network_mrio._cascade.)

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


def build_sectorwide_shock(
    carbon_price_usd_per_t: float,
    pass_through_scale: float = 1.0,
) -> Dict[str, float]:
    """
    Build a sector-typical shock vector. Each sector's shock (fraction of gross
    output) is:
        shock_i = emission_intensity_i × carbon_price × pass_through_i × 1e-6

    emission_intensity_i is tCO2 per MILLION USD of sector GROSS OUTPUT; the 1e-6
    factor converts it to tCO2 per USD so the product is a fraction of output.
    `pass_through_scale` is the Monte-Carlo / sensitivity multiplier on pass-through
    (so L3 responds to the pass-through channel, not just L1).
    """
    from engine.transition.data_loader import load_sector_taxonomy
    tax = load_sector_taxonomy()["sectors"]
    spt = load_sector_pass_through()["sectors"]
    out: Dict[str, float] = {}
    for sec_key, sec_meta in tax.items():
        ei_per_musd = float(sec_meta.get("emission_intensity_t_per_revenue", 0.0))
        pt = float(spt.get(sec_key, {"pass_through": 0.4})["pass_through"])
        pt = max(0.0, min(1.0, pt * max(0.0, pass_through_scale)))
        # Clamp the per-sector shock to 1.0: carbon cost cannot inflate output price by
        # more than 100% within the linear Leontief basis — beyond that the sector is
        # stranding (Layer 2), not passing input cost. Keeps propagation well-conditioned
        # for very high-carbon sectors at high carbon prices (screening safeguard).
        out[sec_key] = min(1.0, ei_per_musd * 1e-6 * carbon_price_usd_per_t * pt)
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
    absorption: float = 1.0,
    input_share: float = 1.0,
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
    absorption : R2 — share of the propagated upstream cost the focal firm
        ABSORBS rather than passing on to its own customers. 1.0 (default) = full
        absorption (legacy). Set to (1 − focal-sector pass-through) to let the
        firm recover part of the input-cost shock downstream.
    """
    L, sectors = get_leontief_inverse(elasticity=elasticity)
    n = len(sectors)
    sector_idx = {s: i for i, s in enumerate(sectors)}

    if sector not in sector_idx:
        # Sector added after the 20×20 matrix was built: use its io_proxy row; else 'services'.
        from engine.transition.data_loader import load_sector_taxonomy
        proxy = load_sector_taxonomy()["sectors"].get(sector, {}).get("io_proxy")
        if proxy in sector_idx:
            sector = proxy
        else:
            _log.warning("L3: sector '%s' not in the IO matrix and no io_proxy; using 'services'.", sector)
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

    # Indirect cost in USD = propagated_shock × the firm's carbon-EXPOSED input base,
    # net of the share it passes downstream (R2 — absorption). The input base is
    # revenue × intermediate_input_share (bought-in inputs, NOT total revenue), so a
    # labour/margin-heavy firm (services, finance) doesn't book an implausible
    # supply-chain carbon cost (diagnostic distortion #1). Default input_share=1.0.
    absorption = max(0.0, min(1.0, absorption))
    input_share = max(0.0, min(1.0, input_share))
    indirect_usd = propagated * max(asset_revenue, 0.0) * input_share * absorption

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
        top_upstream_sources=[(sec, round(c * max(asset_revenue, 0.0) * input_share * absorption, 2)) for sec, c in top5],
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
