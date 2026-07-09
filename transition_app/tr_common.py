"""
Shared helpers for the standalone BSR Transition Risk application.

This app is a self-contained TCFD-aligned front end over the existing
`engine/transition/` four-layer model. It does NOT depend on the physical-risk
Streamlit app; it keeps its own session state (keys prefixed ``tr_``) and builds
`Asset` objects from a transition-only intake form.
"""

from __future__ import annotations

import os
import sys

# --- make the repo root importable regardless of where streamlit is launched --
_d = os.path.dirname(os.path.abspath(__file__))
while _d != os.path.dirname(_d) and not os.path.isdir(os.path.join(_d, "engine")):
    _d = os.path.dirname(_d)
REPO_ROOT = _d
for _p in (REPO_ROOT, os.path.join(REPO_ROOT, "transition_app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from engine.asset_model import Asset  # noqa: E402
from engine.fmt import currency_symbol, fmt as _fmt  # noqa: E402
from engine.transition.transition_engine import (  # noqa: E402
    run_portfolio_transition,
    DEFAULT_HORIZON,
)
from engine.transition.cc_exposure import ROUTE_CASHFLOWS, ROUTE_WACC  # noqa: E402
from engine.transition.data_loader import (  # noqa: E402
    load_sector_taxonomy,
    load_carbon_prices,
    get_ngfs_region,
)

# ---------------------------------------------------------------------------
# Branding / constants
# ---------------------------------------------------------------------------
BRAND_ORANGE = "#F4721A"
APP_TITLE = "BSR Transition Risk"

# TCFD transition-risk categories → the engine layer that quantifies each, and the
# app section that carries it. (TCFD 2017, Table 1: transition risk types.)
TCFD_CATEGORIES = [
    ("Policy & Legal", "L1", "② Policy & Legal Risk",
     "Carbon pricing (taxes, ETS), efficiency mandates and litigation exposure → direct "
     "carbon cost and how much can be passed through vs absorbed."),
    ("Technology", "L2", "③ Technology Risk",
     "Cost of shifting to lower-carbon technology: obsolescence of incumbents, sunk cost, "
     "capex, and cost-crossover-driven stranding."),
    ("Market", "L3", "④ Market Risk",
     "Shifting supply/demand, raw-material and input-cost pressure through the supply chain, "
     "and devaluation/stranding of high-carbon assets as demand falls."),
    ("Reputation", "L4", "⑤ Reputation Risk",
     "Changing stakeholder perception → higher cost of capital (credit/equity premium) and "
     "revenue effects."),
]

# TCFD reporting horizons → representative years on the 2025–2050 engine grid.
HORIZONS = {"Short (2030)": 2030, "Medium (2040)": 2040, "Long (2050)": 2050}

DEFAULT_SCENARIOS = ["net_zero_2050", "current_policies", "fragmented_world"]

# ---------------------------------------------------------------------------
# Sector taxonomy helpers
# ---------------------------------------------------------------------------
def sector_options() -> list[str]:
    return list(load_sector_taxonomy()["sectors"].keys())


def sector_label(key: str) -> str:
    meta = load_sector_taxonomy()["sectors"].get(key, {})
    return meta.get("label", key)


def sector_meta(key: str) -> dict:
    return load_sector_taxonomy()["sectors"].get(key, {})


def scenario_options() -> list[str]:
    return list(load_carbon_prices()["scenarios"].keys())


def scenario_label(key: str) -> str:
    return load_carbon_prices()["scenarios"].get(key, {}).get("label", key)


# ---------------------------------------------------------------------------
# Asset construction — fill physical-only fields with harmless defaults
# ---------------------------------------------------------------------------
def make_asset(row: dict) -> Asset:
    """Build an engine `Asset` from a transition-only intake row.

    The physical-risk fields (lat/lon, construction, roof, etc.) are irrelevant
    to the transition layer, so they get valid placeholder defaults.
    """
    return Asset(
        id=row["id"],
        name=row["name"],
        lat=0.0,
        lon=0.0,
        asset_type="transition_entity",
        replacement_value=float(row.get("replacement_value", 0.0) or 0.0),
        construction_material="concrete",
        year_built=2020,
        stories=1,
        basement=False,
        roof_type="flat",
        first_floor_height_m=0.0,
        terrain_elevation_asl_m=0.0,
        floor_area_m2=0.0,
        region=str(row.get("region", "USA")).strip().upper(),
        sector=str(row.get("sector", "")).strip().lower(),
        scope1_emissions_tco2=float(row.get("scope1", 0.0) or 0.0),
        scope2_emissions_tco2=float(row.get("scope2", 0.0) or 0.0),
        scope3_emissions_tco2=float(row.get("scope3", 0.0) or 0.0),
        annual_revenue=float(row.get("annual_revenue", 0.0) or 0.0),
    )


# The intake portfolio is stored as a list of plain dicts (JSON/CSV friendly).
PORTFOLIO_COLUMNS = [
    "id", "name", "region", "sector",
    "replacement_value", "annual_revenue", "scope1", "scope2", "scope3",
]

SAMPLE_PORTFOLIO = [
    {"id": "COAL-1", "name": "Coal Power Plant", "region": "USA", "sector": "power_coal",
     "replacement_value": 500_000_000, "annual_revenue": 300_000_000,
     "scope1": 2_500_000, "scope2": 50_000, "scope3": 200_000},
    {"id": "REF-1", "name": "Oil Refinery", "region": "USA", "sector": "oil_refining",
     "replacement_value": 2_000_000_000, "annual_revenue": 8_000_000_000,
     "scope1": 4_500_000, "scope2": 300_000, "scope3": 8_000_000},
    {"id": "OFF-1", "name": "Commercial Office", "region": "USA", "sector": "real_estate_commercial",
     "replacement_value": 50_000_000, "annual_revenue": 15_000_000,
     "scope1": 200, "scope2": 800, "scope3": 0},
]


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def _defaults() -> dict:
    return {
        "tr_assets": [],                       # list[dict]
        "tr_currency": "USD",
        "tr_scenarios": list(DEFAULT_SCENARIOS),
        "tr_l4_routing": ROUTE_CASHFLOWS,
        "tr_elasticity": 1.0,
        "tr_layers": [1, 2, 3, 4],
        "tr_wacc": 0.09,                       # discount rate for PV metrics
        "tr_governance": {},                   # TCFD governance narrative
        "tr_target_year": 2050,                # net-zero target year
    }


def init_state() -> None:
    for k, v in _defaults().items():
        st.session_state.setdefault(k, v)


def get_portfolio() -> list[dict]:
    return st.session_state.get("tr_assets", [])


def set_portfolio(rows: list[dict]) -> None:
    st.session_state["tr_assets"] = rows


def get_assets() -> list[Asset]:
    """Portfolio rows → validated Asset objects (skips invalid rows silently)."""
    out = []
    for row in get_portfolio():
        try:
            out.append(make_asset(row))
        except Exception:
            continue
    return out


def currency() -> str:
    return st.session_state.get("tr_currency", "USD")


def sym() -> str:
    return currency_symbol(currency())


def fmt_money(x: float) -> str:
    return _fmt(x, currency())


# ---------------------------------------------------------------------------
# Engine runner
# ---------------------------------------------------------------------------
def run_engine(assets: list[Asset], scenarios: list[str]):
    """Run the four-layer model for the current config. Returns
    {scenario_id: [TransitionAssetResult]}. Empty dict if no sectored assets."""
    active = [a for a in assets if a.sector]
    if not active or not scenarios:
        return {}
    return run_portfolio_transition(
        assets=active,
        scenario_ids=scenarios,
        horizon=DEFAULT_HORIZON,
        layer4_routing=st.session_state.get("tr_l4_routing", ROUTE_CASHFLOWS),
        elasticity=float(st.session_state.get("tr_elasticity", 1.0)),
        enable_layers=tuple(st.session_state.get("tr_layers", [1, 2, 3, 4])),
    )


# ---------------------------------------------------------------------------
# Shared UI chrome
# ---------------------------------------------------------------------------
def page_header(subtitle: str, pillar: str | None = None) -> None:
    st.markdown(
        f"<h1 style='margin-bottom:0;'>"
        f"<span style='color:{BRAND_ORANGE};font-weight:900;'>BSR</span> "
        f"Transition Risk</h1>",
        unsafe_allow_html=True,
    )
    tag = f" &nbsp;·&nbsp; <b>TCFD: {pillar}</b>" if pillar else ""
    st.markdown(
        f"<div style='color:#666;margin-bottom:0.6rem;'>{subtitle}{tag}</div>",
        unsafe_allow_html=True,
    )
    st.divider()


def sidebar_settings() -> list[str]:
    """Render the shared analysis settings in the sidebar (scenarios + engine
    config), persist to session, and return the selected scenario list."""
    # Keys are pre-seeded by init_state(); widgets read/write them via `key=` only
    # (no default/index/value) to avoid the double-initialisation warning. Drop any
    # stale scenario id that is no longer a valid option.
    valid = set(scenario_options())
    st.session_state["tr_scenarios"] = [s for s in st.session_state.get("tr_scenarios", []) if s in valid] \
        or list(DEFAULT_SCENARIOS)
    with st.sidebar:
        st.markdown("### Analysis settings")
        scenarios = st.multiselect(
            "NGFS scenarios", options=scenario_options(),
            format_func=scenario_label, key="tr_scenarios",
        )
        st.radio(
            "Layer 4 routing", [ROUTE_CASHFLOWS, ROUTE_WACC],
            format_func=lambda r: "Cash flows" if r == ROUTE_CASHFLOWS else "WACC",
            help="CCExposure premium flows to cash-flow revenue OR to WACC — one only.",
            key="tr_l4_routing",
        )
        st.slider(
            "L3 substitution elasticity σ", 0.5, 3.0, step=0.1,
            help="1.0 = Cobb-Douglas; higher damps network propagation (Papageorgiou 2017).",
            key="tr_elasticity",
        )
        st.multiselect(
            "Enable layers", [1, 2, 3, 4],
            format_func=lambda i: {1: "L1", 2: "L2", 3: "L3", 4: "L4"}[i],
            key="tr_layers",
        )
        st.number_input(
            "Discount rate (WACC) for PV", 0.0, 0.30, step=0.005, format="%.3f",
            key="tr_wacc",
        )
    return scenarios


def portfolio_gate() -> list[Asset]:
    """Return sectored assets or render guidance + stop the page."""
    assets = get_assets()
    active = [a for a in assets if a.sector]
    if not active:
        st.info(
            "No assets with a **sector** yet. Go to **① Data Entry**, add or load a "
            "portfolio, and assign each entity a sector from the taxonomy.",
            icon="📋",
        )
        if st.button("Load the 3 worked-example assets"):
            set_portfolio([dict(r) for r in SAMPLE_PORTFOLIO])
            st.rerun()
        st.stop()
    return active


def disclaimer() -> None:
    st.caption(
        "Screening-grade transition-risk analytics per the *BSR Transition Risk "
        "Methodology v1*. NGFS Phase V carbon prices, EXIOBASE-3 I-O structure, "
        "sector-median pass-through and CCExposure proxies. Not investment advice "
        "or a regulatory disclosure without specialist review."
    )
