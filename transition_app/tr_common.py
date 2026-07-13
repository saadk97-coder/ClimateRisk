"""
Shared helpers for the standalone BSR Transition Risk application.

This app is a self-contained TCFD-aligned front end over the existing
`engine/transition/` four-layer model. It does NOT depend on the physical-risk
Streamlit app; it keeps its own session state (keys prefixed ``tr_``) and builds
`Asset` objects from a transition-only intake form.
"""

from __future__ import annotations

import os
import re
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
        # financials entered in the reporting currency → USD for the engine
        replacement_value=float(row.get("replacement_value", 0.0) or 0.0) * fx_to_usd(),
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
        annual_revenue=float(row.get("annual_revenue", 0.0) or 0.0) * fx_to_usd(),
        decarb_target_year=_int_or(row.get("target_year"), 0),
        decarb_residual_pct=0.0,
        # blank / NaN priced_pct means "fully priced" (100), not 0
        priced_emissions_fraction=_float_or(row.get("priced_pct"), 100.0) / 100.0,
    )


def _int_or(v, default: int) -> int:
    try:
        f = float(v)
        return default if f != f else int(f)   # NaN → default
    except (TypeError, ValueError):
        return default


def _float_or(v, default: float) -> float:
    try:
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


# The intake portfolio is stored as a list of plain dicts (JSON/CSV friendly).
# target_year: Scope 1+2 net-zero target (0/blank = no abatement, hold emissions flat).
# priced_pct: % of Scope 1+2 exposed to the carbon price, net of free allocation (100 = fully priced).
# attribution_pct: share of the asset attributed to the reporting entity (PCAF).
# 100 = fully owned (corporate view); a lender/investor enters their stake.
PORTFOLIO_COLUMNS = [
    "id", "name", "region", "sector",
    "replacement_value", "annual_revenue", "scope1", "scope2", "scope3",
    "target_year", "priced_pct", "attribution_pct",
]

SAMPLE_PORTFOLIO = [
    {"id": "COAL-1", "name": "Coal Power Plant", "region": "USA", "sector": "power_coal",
     "replacement_value": 500_000_000, "annual_revenue": 300_000_000,
     "scope1": 2_500_000, "scope2": 50_000, "scope3": 200_000,
     "target_year": 0, "priced_pct": 100, "attribution_pct": 100},
    {"id": "REF-1", "name": "Oil Refinery", "region": "USA", "sector": "oil_refining",
     "replacement_value": 2_000_000_000, "annual_revenue": 8_000_000_000,
     "scope1": 4_500_000, "scope2": 300_000, "scope3": 8_000_000,
     "target_year": 0, "priced_pct": 100, "attribution_pct": 100},
    {"id": "OFF-1", "name": "Commercial Office", "region": "USA", "sector": "real_estate_commercial",
     "replacement_value": 50_000_000, "annual_revenue": 15_000_000,
     "scope1": 200, "scope2": 800, "scope3": 0,
     "target_year": 0, "priced_pct": 100, "attribution_pct": 100},
]


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
def _defaults() -> dict:
    return {
        "tr_assets": [],                       # list[dict]
        "tr_currency": "USD",
        "tr_scenarios": list(DEFAULT_SCENARIOS),
        "tr_l4_routing": ROUTE_WACC,           # R5 — equity premium (sourced) → cost of capital by default
        "tr_elasticity": 1.0,
        "tr_layers": [1, 2, 3, 4],
        "tr_wacc": 0.09,                       # NOMINAL WACC
        "tr_inflation": 0.025,                 # long-run inflation → real discount = wacc − inflation
        "tr_governance": {},                   # TCFD governance narrative
        "tr_target_year": 2050,                # net-zero target year
        "tr_scope3_mode": "full",              # 'full' | 'auto' (drop L1 scope-3 when L3 on)
        "tr_l3_mode": "world",                 # 'world' (20×20) | 'mrio' (20×49 EXIOBASE)
        "tr_cascade": False,                   # Reisch endogenous-default cascade (mrio only)
        "tr_cascade_theta": 0.02,              # default threshold (fraction of output)
        "tr_firm_cce": {},                     # {asset_id: {opportunity, regulatory, physical}} L4 override
        "tr_carbon_inclusive_crossover": False,  # P6 — add incumbent carbon cost to L2 crossover
        "tr_non_fossil_base_frac": 0.5,        # R1 — non-fossil impairment base share
        "tr_l3_partial_pt": False,             # R2 — firm recovers its PT share of upstream cost
    }


def init_state() -> None:
    for k, v in _defaults().items():
        st.session_state.setdefault(k, v)


def get_portfolio() -> list[dict]:
    return st.session_state.get("tr_assets", [])


def set_portfolio(rows: list[dict]) -> None:
    st.session_state["tr_assets"] = rows


def attribution_map() -> dict:
    """{asset_id: attribution fraction in [0,1]} from the portfolio (default 1.0)."""
    out = {}
    for row in get_portfolio():
        out[str(row.get("id", "")).strip()] = _float_or(row.get("attribution_pct"), 100.0) / 100.0
    return out


def get_assets() -> list[Asset]:
    """Portfolio rows → validated Asset objects (skips invalid rows silently)."""
    out = []
    for row in get_portfolio():
        try:
            out.append(make_asset(row))
        except Exception:
            continue
    return out


# Indicative FX — USD per 1 unit of currency. The engine runs in USD because NGFS
# carbon prices are USD/tCO₂; financial inputs are converted to USD on the way in and
# results converted back for display. Update as needed.
FX_USD_PER_UNIT = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "JPY": 0.0064, "CAD": 0.73, "AUD": 0.66}
FX_AS_OF = "2026-07 (indicative — override for reporting)"


def currency() -> str:
    return st.session_state.get("tr_currency", "USD")


def fx_to_usd(code: str | None = None) -> float:
    return FX_USD_PER_UNIT.get(code or currency(), 1.0)


def sym() -> str:
    return currency_symbol(currency())


def fmt_money(x_usd: float) -> str:
    """Format a USD amount in the reporting currency (converts USD → display)."""
    return _fmt(x_usd / fx_to_usd(), currency())


def real_discount() -> float:
    """P2 — carbon prices are real (USD2020), so PV of real cash flows uses a REAL
    discount rate = nominal WACC − long-run inflation. Discounting real flows at the
    nominal WACC would systematically understate PV."""
    return max(0.0, float(st.session_state.get("tr_wacc", 0.09))
               - float(st.session_state.get("tr_inflation", 0.025)))


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
        layer4_routing=st.session_state.get("tr_l4_routing", ROUTE_WACC),
        elasticity=float(st.session_state.get("tr_elasticity", 1.0)),
        enable_layers=tuple(st.session_state.get("tr_layers", [1, 2, 3, 4])),
        scope3_mode=st.session_state.get("tr_scope3_mode", "full"),
        l3_mode=st.session_state.get("tr_l3_mode", "world"),
        cascade=bool(st.session_state.get("tr_cascade", False)),
        cascade_theta=float(st.session_state.get("tr_cascade_theta", 0.02)),
        firm_cce_overrides=st.session_state.get("tr_firm_cce") or None,
        carbon_inclusive_crossover=bool(st.session_state.get("tr_carbon_inclusive_crossover", False)),
        non_fossil_base_fraction=float(st.session_state.get("tr_non_fossil_base_frac", 0.5)),
        l3_partial_pass_through=bool(st.session_state.get("tr_l3_partial_pt", False)),
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
    # convert markdown **bold** in the subtitle to HTML so it renders inside the div
    sub_html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", subtitle)
    tag = f" &nbsp;·&nbsp; <b>TCFD: {pillar}</b>" if pillar else ""
    st.markdown(
        f"<div style='color:#666;margin-bottom:0.6rem;'>{sub_html}{tag}</div>",
        unsafe_allow_html=True,
    )
    st.divider()


def validate_portfolio(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for the saved portfolio. Errors block analysis;
    warnings flag results that will be silently degraded."""
    errors: list[str] = []
    warnings: list[str] = []
    valid_sectors = set(sector_options())
    for r in rows:
        rid = r.get("id", "?")
        region = str(r.get("region", ""))
        sector = str(r.get("sector", "")).lower()
        if len(region) != 3:
            errors.append(f"`{rid}`: region must be a 3-letter ISO3 code (got '{region}').")
        if not sector:
            errors.append(f"`{rid}`: no sector assigned.")
        elif sector not in valid_sectors:
            errors.append(f"`{rid}`: sector '{sector}' is not in the taxonomy.")
        rev = float(r.get("annual_revenue", 0) or 0)
        s12 = float(r.get("scope1", 0) or 0) + float(r.get("scope2", 0) or 0)
        if sector in valid_sectors:
            if rev <= 0:
                warnings.append(f"`{rid}`: no annual revenue — network (L3) and reputation (L4) "
                                "costs scale by revenue and will read zero.")
            if sector_meta(sector).get("fossil_dependent") and s12 <= 0:
                warnings.append(f"`{rid}`: fossil-dependent sector with no Scope 1/2 emissions — "
                                "carbon cost (L1) will be ~zero.")
        if s12 > 1e9:
            warnings.append(f"`{rid}`: Scope 1+2 exceeds 1 Gt CO₂ — check the units (tonnes/yr).")
    return errors, warnings


def portfolio_warnings_banner() -> None:
    """Compact warning banner for the analysis pages (non-blocking)."""
    _, warns = validate_portfolio(get_portfolio())
    if warns:
        with st.expander(f"⚠️ {len(warns)} data warning(s) — results may be incomplete"):
            for w in warns:
                st.markdown(f"- {w}")


def build_results_xlsx(results, active, scenarios, discount_rate: float) -> bytes:
    """Multi-sheet XLSX: summary, annual detail, portfolio, and a run manifest with
    provenance. Returns the workbook as bytes."""
    import io
    import datetime as _dt
    from engine.transition.data_loader import (
        load_carbon_prices, load_io_matrix, load_cc_exposure, load_learning_curves,
    )

    def _pv(series):
        return sum(v / (1.0 + discount_rate) ** (y - min(DEFAULT_HORIZON)) for y, v in series.items())

    # Summary by scenario (in reporting currency)
    fx = fx_to_usd()
    summary = []
    for sc, res in results.items():
        pv_c = sum(_pv(r.annual_total_cost_usd) for r in res) / fx
        pv_i = sum(_pv(r.annual_impairment_usd) for r in res) / fx
        # P1 — cost and impairment are alternative lenses on the same loss; not summed.
        summary.append({"scenario": scenario_label(sc),
                        f"pv_transition_cost_{currency()}": round(pv_c, 2),
                        f"pv_stranded_impairment_alt_lens_{currency()}": round(pv_i, 2)})

    annual = []
    for sc, res in results.items():
        for r in res:
            for y in DEFAULT_HORIZON:
                annual.append({
                    "scenario": sc, "entity": r.asset_id, "sector": r.sector, "year": y,
                    "L1_carbon": r.layer_breakdown["L1_carbon_opex"].get(y, 0.0) / fx,
                    "L2_revenue": r.layer_breakdown["L2_revenue_erosion"].get(y, 0.0) / fx,
                    "L3_network": r.layer_breakdown["L3_network_input_cost"].get(y, 0.0) / fx,
                    "L4_reputation": r.layer_breakdown["L4_revenue_modifier"].get(y, 0.0) / fx,
                    "total_cf_cost": r.annual_total_cost_usd.get(y, 0.0) / fx,
                    "impairment": r.annual_impairment_usd.get(y, 0.0) / fx,
                })

    cp_m = load_carbon_prices().get("_meta", {})
    io_m = load_io_matrix().get("_meta", {})
    cce_m = load_cc_exposure().get("_meta", {})
    lc_m = load_learning_curves().get("_meta", {})
    manifest = [
        ("Generated (UTC)", _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"),
        ("Methodology", "BSR Transition Risk v1 (four-layer)"),
        ("Reporting currency", currency()), ("FX basis", FX_AS_OF),
        ("Discount rate (WACC)", discount_rate),
        ("Scenarios", ", ".join(scenario_label(s) for s in scenarios)),
        ("Scope-3 mode", st.session_state.get("tr_scope3_mode", "full")),
        ("Layer-4 routing", st.session_state.get("tr_l4_routing", "cashflows")),
        ("L3 substitution σ", st.session_state.get("tr_elasticity", 1.0)),
        ("Layers enabled", st.session_state.get("tr_layers", [1, 2, 3, 4])),
        ("Carbon prices", f"{cp_m.get('model', 'NGFS Phase V')} · {cp_m.get('reported_unit', 'USD/tCO2')} · {cp_m.get('retrieved_utc', '—')}"),
        ("I-O matrix", (io_m.get("sources", ["EXIOBASE-3"]) or ["EXIOBASE-3"])[0]),
        ("CCExposure", (cce_m.get("sources", ["Sautner 2023"]) or ["Sautner 2023"])[0]),
        ("Learning curves", lc_m.get("units_note", "IRENA 2024 / Lazard 2025 (power)")),
        ("Disclaimer", "Screening-grade — not a regulatory disclosure without specialist review."),
    ]

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame(summary).to_excel(xw, sheet_name="Summary", index=False)
        pd.DataFrame(annual).to_excel(xw, sheet_name="Annual detail", index=False)
        pd.DataFrame(get_portfolio()).to_excel(xw, sheet_name="Portfolio", index=False)
        pd.DataFrame([(k, str(v)) for k, v in manifest],
                     columns=["Field", "Value"]).to_excel(xw, sheet_name="Run manifest", index=False)
    return buf.getvalue()


def build_disclosure_report(active, results, scenarios, discount_rate: float) -> str:
    """Generate an IFRS S2 / ESRS E1-structured transition-risk disclosure (Markdown)
    from the current portfolio, governance narrative and results."""
    import datetime as _dt
    from engine.transition.alignment import financed_emissions, implied_temperature_rise
    from engine.transition.data_loader import load_carbon_prices, load_io_matrix, load_cc_exposure
    from engine.transition.transition_engine import DEFAULT_HORIZON

    from engine.transition.transition_engine import run_portfolio_transition

    gov = st.session_state.get("tr_governance", {})
    att = attribution_map()
    fe = financed_emissions(active, att)
    itr = implied_temperature_rise(active, att)
    base_year = min(DEFAULT_HORIZON)

    # U2 — hard-exclude the experimental endogenous-default cascade (Reisch 2025)
    # from the regulatory disclosure figures, REGARDLESS of the UI toggle. The
    # cascade is a research amplification, not a defensible disclosure input, so
    # the disclosure always recomputes with cascade=False rather than trusting the
    # passed-in `results` (which may have been computed with the cascade on).
    active_sectored = [a for a in active if getattr(a, "sector", "")]
    if active_sectored and scenarios:
        results = run_portfolio_transition(
            assets=active_sectored,
            scenario_ids=list(scenarios),
            horizon=DEFAULT_HORIZON,
            layer4_routing=st.session_state.get("tr_l4_routing", ROUTE_WACC),
            elasticity=float(st.session_state.get("tr_elasticity", 1.0)),
            enable_layers=tuple(st.session_state.get("tr_layers", [1, 2, 3, 4])),
            scope3_mode=st.session_state.get("tr_scope3_mode", "full"),
            l3_mode=st.session_state.get("tr_l3_mode", "world"),
            cascade=False,                                   # ← hard exclusion
            firm_cce_overrides=st.session_state.get("tr_firm_cce") or None,
        )

    def _pv(series):
        return sum(v / (1 + discount_rate) ** (y - base_year) for y, v in series.items())

    scen_lines = []
    for sc, res in results.items():
        pv_c = sum(_pv(r.annual_total_cost_usd) for r in res)
        pv_i = sum(_pv(r.annual_impairment_usd) for r in res)
        scen_lines.append(f"| {scenario_label(sc)} | {fmt_money(pv_c)} | {fmt_money(pv_i)} |")

    def _g(k, default="*Not disclosed.*"):
        return gov.get(k) or default

    cp = load_carbon_prices().get("_meta", {})
    io = load_io_matrix().get("_meta", {})
    cce = load_cc_exposure().get("_meta", {})
    now = _dt.datetime.utcnow().strftime("%Y-%m-%d")

    return f"""# Climate-related Financial Disclosures — Transition Risk

*Prepared {now} with the BSR Transition Risk engine (Methodology v1). Screening-grade;
structured against **IFRS S2** and **ESRS E1**. Not a substitute for assured disclosure.*

Reporting currency: **{currency()}** · Discount rate: **{discount_rate*100:.1f}%** ·
Scenarios: **{', '.join(scenario_label(s) for s in scenarios)}** · Entities: **{len(active)}**

---

## a) Governance  <sub>IFRS S2 ¶6–7 · ESRS 2 GOV-1..5</sub>

**Board oversight.** {_g('board_oversight')}

**Review cadence:** {gov.get('review_cadence', 'Not disclosed')} ·
**Accountable body:** {gov.get('accountable_body') or 'Not disclosed'}

**Management's role.** {_g('management_role')}

**Integration into strategy & financial planning.** {_g('strategy_integration')}

**Regulatory / litigation exposure.** {_g('policy_legal_note')}

---

## b) Strategy — scenario analysis  <sub>IFRS S2 ¶9–23 · ESRS E1-1, E1-6</sub>

Transition risk is quantified over {base_year}–{max(DEFAULT_HORIZON)} under NGFS-style
scenarios through four channels (carbon cost, technology/stranding, supply-chain network,
reputation/capital). Present value of the transition impact:

| Scenario | PV transition cost | PV stranded impairment |
|---|---|---|
{chr(10).join(scen_lines)}

Resilience: results are scenario-differentiated; orderly pathways front-load carbon cost,
disorderly/high-warming pathways shift the burden to stranding and later years.

---

## c) Risk Management  <sub>IFRS S2 ¶24–26 · ESRS E1 IRO-1</sub>

Each transition-risk category is quantified by one engine layer and routed to exactly one
financial destination (non-duplication): **Policy & Legal** → carbon cost (L1);
**Technology** → learning-curve stranding (L2); **Market** → supply-chain network (L3);
**Reputation** → cost of capital (L4). Uncertainty is assessed by Monte-Carlo over the
carbon price, pass-through and substitution elasticity.

The experimental endogenous-default contagion cascade (Reisch et al. 2025) is a research
amplification and is **excluded from the figures in this disclosure** — the network layer here
is the transparent Leontief propagation only.

---

## d) Metrics & Targets  <sub>IFRS S2 ¶27–37 · ESRS E1-4/5/6/7</sub>

**Financed / attributed GHG emissions (PCAF basis):**

| Scope | Attributed tCO₂e |
|---|---|
| Scope 1 | {fe.scope1:,.0f} |
| Scope 2 | {fe.scope2:,.0f} |
| Scope 3 | {fe.scope3:,.0f} |
| **Scope 1+2** | **{fe.total_s1_s2:,.0f}** |

**Implied Temperature Rise:** **{itr['portfolio_itr']:.2f} °C** (Scope 1+2 × attribution weighted,
vs a 1.5 °C linear-to-net-zero budget).

**Targets:** {sum(1 for a in active if a.decarb_target_year)}/{len(active)} entities carry a
Scope 1+2 net-zero target; abatement is reflected in the carbon-cost projection.

**Carbon price basis:** {cp.get('model', 'NGFS Phase V')} ({cp.get('reported_unit', 'USD/tCO₂')}).

---

## Basis of preparation & data provenance

- Carbon prices: {cp.get('model', 'NGFS Phase V')} · {cp.get('retrieved_utc', '—')}
- Input-output network: {(io.get('sources', ['EXIOBASE-3']) or ['EXIOBASE-3'])[0]}
- Reputation exposure: {(cce.get('sources', ['Sautner 2023']) or ['Sautner 2023'])[0]}
- Technology costs: IRENA 2024 / Lazard 2025 (power sector LCOE)

**Limitations.** Screening-grade. Sector-median pass-through and CCExposure proxies;
precipitation-independent transition channels; approximate NGFS vintage. Not a regulatory
disclosure without specialist review and assurance.
"""


def sidebar_settings() -> list[str]:
    """Render the shared analysis settings in the sidebar (scenarios + engine
    config), persist to session, and return the selected scenario list."""
    # Pattern: no `key=`; seed each widget's initial value from session_state via
    # default/value/index, then write the return value back. This displays the
    # persisted value correctly across page navigation (a keyed widget created for
    # the first time on a sub-page does not reliably pick up a pre-seeded session
    # value) and avoids the default+key double-initialisation warning.
    valid = set(scenario_options())
    cur_sc = [s for s in st.session_state.get("tr_scenarios", DEFAULT_SCENARIOS)
              if s in valid] or list(DEFAULT_SCENARIOS)
    with st.sidebar:
        st.markdown("### Analysis settings")
        scenarios = st.multiselect(
            "NGFS scenarios", options=scenario_options(), default=cur_sc,
            format_func=scenario_label,
        )
        st.session_state["tr_scenarios"] = scenarios

        route = st.radio(
            "Layer 4 routing", [ROUTE_WACC, ROUTE_CASHFLOWS],
            index=0 if st.session_state.get("tr_l4_routing", ROUTE_WACC) == ROUTE_WACC else 1,
            format_func=lambda r: "WACC (equity premium — sourced)" if r == ROUTE_WACC
            else "Cash flows (revenue — manual layer)",
            help="CCExposure routes exactly once (non-duplication). WACC is the default: "
            "the equity premium is the only sourced elasticity (Sautner et al. 2023, JoF, "
            "pricing→cost-of-capital). The cash-flow route applies an UNSOURCED market-"
            "opportunity revenue modifier — treat it as a manual overlay, not a model output.",
        )
        st.session_state["tr_l4_routing"] = route

        el = st.slider(
            "L3 substitution elasticity σ", 0.5, 3.0,
            float(st.session_state.get("tr_elasticity", 1.0)), 0.1,
            help="1.0 = Cobb-Douglas; higher damps network propagation (Papageorgiou 2017).",
        )
        st.session_state["tr_elasticity"] = el

        layers = st.multiselect(
            "Enable layers", [1, 2, 3, 4],
            default=st.session_state.get("tr_layers", [1, 2, 3, 4]),
            format_func=lambda i: {1: "L1", 2: "L2", 3: "L3", 4: "L4"}[i],
        )
        st.session_state["tr_layers"] = layers or [1, 2, 3, 4]

        wacc = st.number_input(
            "Nominal WACC", 0.0, 0.30,
            float(st.session_state.get("tr_wacc", 0.09)), 0.005, format="%.3f",
        )
        st.session_state["tr_wacc"] = wacc
        infl = st.number_input(
            "Long-run inflation", 0.0, 0.10,
            float(st.session_state.get("tr_inflation", 0.025)), 0.0025, format="%.4f",
            help="Carbon prices are real (USD2020); PV discounts real cash flows at a REAL "
                 "rate = nominal WACC − inflation. (real = {:.1%})".format(
                     max(0.0, float(st.session_state.get("tr_wacc", 0.09))
                         - float(st.session_state.get("tr_inflation", 0.025)))),
        )
        st.session_state["tr_inflation"] = infl

        modes = ["full", "auto"]
        s3 = st.radio(
            "Scope-3 treatment", modes,
            index=modes.index(st.session_state.get("tr_scope3_mode", "full")),
            format_func=lambda m: "Full (L1 + L3)" if m == "full"
            else "Auto — no double count (recommended)",
            help="'Full' reproduces the methodology's worked examples (Scope-3 in L1 AND "
                 "propagated in L3). 'Auto' drops the L1 Scope-3 term whenever L3 is on so "
                 "upstream cost is counted once.",
        )
        st.session_state["tr_scope3_mode"] = s3

        st.markdown("**Layer 3 (network)**")
        l3_modes = ["world", "mrio"]
        l3 = st.radio(
            "Resolution", l3_modes,
            index=l3_modes.index(st.session_state.get("tr_l3_mode", "world")),
            format_func=lambda m: "World (20 sectors)" if m == "world"
            else "Multi-region (20×49 EXIOBASE)",
            help="World = 20-sector single-region matrix (fast, default). Multi-region = full "
                 "EXIOBASE 20×49 with cross-region supply chains and region-specific carbon prices.",
        )
        st.session_state["tr_l3_mode"] = l3
        if l3 == "mrio":
            casc = st.checkbox(
                "Endogenous-default cascade (Reisch 2025)",
                value=bool(st.session_state.get("tr_cascade", False)),
                help="Nonlinear contagion: sectors absorbing input-cost shocks above the "
                     "threshold pass an amplified shock downstream. Triggers only for the "
                     "most-exposed nodes under stress.",
            )
            st.session_state["tr_cascade"] = casc
            if casc:
                st.session_state["tr_cascade_theta"] = st.slider(
                    "Default threshold θ (share of output)", 0.005, 0.05,
                    float(st.session_state.get("tr_cascade_theta", 0.02)), 0.005,
                    help="Lower θ → more sectors default → more contagion.",
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
