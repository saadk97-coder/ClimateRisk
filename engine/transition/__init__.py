"""
BSR Transition Risk Layer — four-module architecture per the BSR Climate Risk
Practice memo (May 2026):

  Layer 1 — Direct carbon cost with pass-through         (carbon_pricing.py)
  Layer 2 — Technology disruption / learning curves       (learning_curves.py)
  Layer 3 — Production network propagation (Leontief I-O) (network_propagation.py)
  Layer 4 — Reputational / capital-access (CCExposure)    (cc_exposure.py)

Orchestration: transition_engine.run_asset_transition()
DCF integration: transition_dcf.compute_combined_dcf()  (composes with engine.dcf_engine)
"""

from engine.transition.data_loader import (
    load_carbon_prices,
    load_sector_pass_through,
    load_learning_curves,
    load_sector_pathways,
    load_cc_exposure,
    load_io_matrix,
    load_sector_taxonomy,
    get_ngfs_region,
    map_scenario_to_ngfs,
)

__all__ = [
    "load_carbon_prices",
    "load_sector_pass_through",
    "load_learning_curves",
    "load_sector_pathways",
    "load_cc_exposure",
    "load_io_matrix",
    "load_sector_taxonomy",
    "get_ngfs_region",
    "map_scenario_to_ngfs",
]
