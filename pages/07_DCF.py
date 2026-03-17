"""
Page 7 - Climate-Adjusted DCF
BSR framework: "From Climate Science to Corporate Strategy"
https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine.asset_model import Asset as _Asset
from engine.dcf_engine import DCFInputs, DCFResult, compute_climate_dcf
from engine.export_engine import export_dcf_xlsx
from engine.fmt import currency_symbol as _currency_symbol, fmt as _fmt_cur
from engine.scenario_model import SCENARIOS

st.set_page_config(page_title="Climate DCF", page_icon="💹", layout="wide")


def _scenario_label(scenario_id: str) -> str:
    return SCENARIOS.get(scenario_id, {}).get("label", scenario_id)


def _scenario_comparison_rows(dcf_results: list[DCFResult]) -> list[dict]:
    return [
        {
            "Scenario": result.label,
            "Scenario ID": result.scenario_id,
            "Base NPV": result.npv_base,
            "Climate-Adjusted NPV": result.npv_climate,
            "NPV Impairment": result.npv_delta,
            "NPV Impairment (%)": result.npv_delta_pct,
            "PV Damages": result.total_pv_damages,
        }
        for result in dcf_results
    ]


def _comparison_display_df(dcf_results: list[DCFResult], currency_code: str, currency_symbol: str) -> pd.DataFrame:
    rows = _scenario_comparison_rows(dcf_results)
    display_df = pd.DataFrame(rows)
    for col in ["Base NPV", "Climate-Adjusted NPV", "NPV Impairment", "PV Damages"]:
        display_df[col] = display_df[col].apply(lambda value: _fmt_cur(value, currency_code))
    display_df = display_df.rename(
        columns={
            "Base NPV": f"Base NPV ({currency_symbol})",
            "Climate-Adjusted NPV": f"Climate-Adjusted NPV ({currency_symbol})",
            "NPV Impairment": f"NPV Impairment ({currency_symbol})",
            "PV Damages": f"PV Damages ({currency_symbol})",
        }
    )
    display_df["NPV Impairment (%)"] = display_df["NPV Impairment (%)"].apply(lambda value: f"{value:.2f}%")
    return display_df


def _comparison_export_df(dcf_results: list[DCFResult], currency_symbol: str) -> pd.DataFrame:
    export_df = pd.DataFrame(_scenario_comparison_rows(dcf_results))
    return export_df.rename(
        columns={
            "Base NPV": f"Base NPV ({currency_symbol})",
            "Climate-Adjusted NPV": f"Climate NPV ({currency_symbol})",
            "NPV Impairment": f"NPV Delta ({currency_symbol})",
            "NPV Impairment (%)": "NPV Delta (%)",
            "PV Damages": f"PV Damages ({currency_symbol})",
        }
    )


def _selected_result(results: list[DCFResult], scenario_id: str) -> DCFResult:
    return next(result for result in results if result.scenario_id == scenario_id)


def _render_results(dcf_results: list[DCFResult], currency_code: str, currency_symbol: str) -> None:
    st.divider()
    st.subheader("Results")
    st.caption("Showing the last computed run. Recompute after changing scenario selection or financial inputs.")

    st.dataframe(
        _comparison_display_df(dcf_results, currency_code, currency_symbol),
        use_container_width=True,
        hide_index=True,
    )

    available_scenarios = [result.scenario_id for result in dcf_results]
    selected_scenario = st.session_state.get("dcf_view_scenario", available_scenarios[0])
    if selected_scenario not in available_scenarios:
        selected_scenario = available_scenarios[0]
        st.session_state.dcf_view_scenario = selected_scenario

    selected_scenario = st.selectbox(
        "Valuation Scenario",
        options=available_scenarios,
        format_func=_scenario_label,
        index=available_scenarios.index(selected_scenario),
        key="dcf_view_scenario",
        help="Inspect one scenario valuation model at a time. No probability weighting is applied.",
    )
    result = _selected_result(dcf_results, selected_scenario)

    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
    metric_col1.metric("Base NPV", _fmt_cur(result.npv_base, currency_code))
    metric_col2.metric(
        "Climate-Adjusted NPV",
        _fmt_cur(result.npv_climate, currency_code),
        delta=_fmt_cur(result.npv_delta, currency_code),
        delta_color="inverse",
    )
    metric_col3.metric("NPV Impairment (%)", f"{result.npv_delta_pct:.2f}%")
    metric_col4.metric("PV Climate Damages", _fmt_cur(result.total_pv_damages, currency_code))

    waterfall = go.Figure(
        go.Waterfall(
            x=["Base NPV", f"{result.label} impairment", f"{result.label} climate-adjusted NPV"],
            y=[result.npv_base, result.npv_delta, result.npv_climate],
            measure=["absolute", "relative", "total"],
            text=[
                _fmt_cur(result.npv_base, currency_code),
                _fmt_cur(result.npv_delta, currency_code),
                _fmt_cur(result.npv_climate, currency_code),
            ],
            connector={"line": {"color": "#888"}},
            decreasing={"marker": {"color": "#C94040"}},
            increasing={"marker": {"color": "#2A9D8F"}},
            totals={"marker": {"color": "#1A3A5C"}},
        )
    )
    waterfall.update_layout(
        title=f"Scenario Valuation Bridge - {result.label}",
        height=360,
        margin=dict(l=20, r=20, t=50, b=20),
        waterfallgap=0.35,
    )
    st.plotly_chart(waterfall, use_container_width=True)

    st.subheader("Annual Damage Stream by Scenario")
    damage_chart = go.Figure()
    for scenario_result in dcf_results:
        if scenario_result.annual_detail.empty:
            continue
        damage_chart.add_trace(
            go.Scatter(
                x=scenario_result.annual_detail["year"],
                y=scenario_result.annual_detail["climate_damage"],
                mode="lines",
                name=scenario_result.label,
                line=dict(
                    color=SCENARIOS.get(scenario_result.scenario_id, {}).get("color", "#888"),
                    width=2.5,
                ),
            )
        )
    damage_chart.update_layout(
        xaxis_title="Year",
        yaxis_title=f"Annual Climate Damage ({currency_symbol})",
        height=320,
        margin=dict(l=20, r=20, t=20, b=20),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(damage_chart, use_container_width=True)

    if not result.annual_detail.empty:
        st.subheader(f"Scenario Cash Flow Path - {result.label}")
        cf_chart = go.Figure()
        cf_chart.add_trace(
            go.Scatter(
                x=result.annual_detail["year"],
                y=result.annual_detail["base_cf"],
                mode="lines",
                name="Base cash flow",
                line=dict(color="#1A3A5C", width=2, dash="dot"),
            )
        )
        cf_chart.add_trace(
            go.Scatter(
                x=result.annual_detail["year"],
                y=result.annual_detail["adjusted_cf"],
                mode="lines",
                name="Climate-adjusted cash flow",
                line=dict(color="#F4721A", width=2.5),
            )
        )
        cf_chart.update_layout(
            xaxis_title="Year",
            yaxis_title=f"Annual Cash Flow ({currency_symbol})",
            height=320,
            margin=dict(l=20, r=20, t=20, b=20),
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(cf_chart, use_container_width=True)

        detail_df = result.annual_detail.rename(
            columns={
                "year": "Year",
                "base_cf": f"Base CF ({currency_symbol})",
                "climate_damage": f"Climate Damage ({currency_symbol})",
                "adaptation_saving": f"Adaptation Saving ({currency_symbol})",
                "adjusted_cf": f"Adjusted CF ({currency_symbol})",
                "discount_factor": "Discount Factor",
                "pv_adjusted_cf": f"PV Adjusted CF ({currency_symbol})",
            }
        ).copy()
        st.dataframe(detail_df, use_container_width=True, hide_index=True)

    with st.expander("BSR Methodology: From Climate Science to Corporate Strategy"):
        st.markdown(
            """
**Framework Reference:** BSR "From Climate Science to Corporate Strategy"
[https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf](https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf)

**Step 1 - Identify exposures**
Map physical assets to climate hazard zones using location data and scenario-based hazard projections.

**Step 2 - Quantify financial impact**
Translate hazard intensity into asset damage using vulnerability functions (HAZUS, JRC).
Compute annual EAD for each year 2025-2050.

**Step 3 - Integrate into financial planning**
Subtract the annual damage stream from the base cash flow profile and discount the adjusted stream using the chosen WACC assumptions.

**Step 4 - Scenario-specific valuation**
Run the valuation separately under each selected scenario and inspect one scenario model at a time. The platform does not probability-weight scenario NPVs in this workflow.

**Step 5 - Adaptation investment**
Evaluate adaptation measures on the Adaptation page and compare avoided-damage benefits against investment cost.

**TCFD Alignment**
- *Strategy*: disclose financial impact under different warming scenarios
- *Risk Management*: quantify physical risk exposure using EAD methodology
- *Metrics & Targets*: total PV of climate damages and scenario-specific NPV impairment
            """
        )

    export_df = _comparison_export_df(dcf_results, currency_symbol)
    xlsx = export_dcf_xlsx(dcf_results, export_df)
    st.download_button(
        "Download DCF Analysis (.xlsx)",
        data=xlsx,
        file_name="climate_adjusted_dcf.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


with st.sidebar:
    st.header("Portfolio Summary")
    raw_assets = st.session_state.get("assets", [])
    n_assets = len(raw_assets)
    total_value = sum(
        asset.replacement_value if hasattr(asset, "replacement_value") else asset.get("replacement_value", 0)
        for asset in raw_assets
    )
    currency_code = st.session_state.get("currency_code", "GBP")
    st.metric("Assets", n_assets)
    st.metric("Total Value", _fmt_cur(total_value, currency_code))

st.title("Climate-Adjusted DCF Valuation")
st.markdown(
    """
**Framework:** BSR "From Climate Science to Corporate Strategy" |
[Download report ->](https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf)
| [TCFD guidance ->](https://www.fsb-tcfd.org/recommendations/)

This module translates physical climate risk into **financial impairment of asset value** using a
scenario-based discounted cash flow framework. It is suitable for scenario testing and impairment
screening, not as a substitute for a valuation-grade underwriting or transaction model.
"""
)

assets = [_Asset.from_dict(asset) if isinstance(asset, dict) else asset for asset in st.session_state.get("assets", [])]
annual_df = st.session_state.get("annual_damages", pd.DataFrame())
selected_scenarios = st.session_state.get("selected_scenarios", [])
currency_code = st.session_state.get("currency_code", "GBP")
currency_symbol = _currency_symbol(currency_code)

if not assets:
    st.warning("No assets defined.")
    st.stop()
if annual_df.empty:
    st.warning("Run the damage calculation on the Results page first.")
    st.stop()
if not selected_scenarios:
    st.warning("Select one or more scenarios on the Scenarios page first.")
    st.stop()

st.divider()
st.subheader("Financial Parameters")

col1, col2, col3 = st.columns(3)
with col1:
    dcf_mode = st.radio(
        "Cash flow basis",
        ["Replacement value proxy (screening only)", "Enter annual cash flows"],
        help="Use a screening proxy or enter explicit annual free cash flow projections.",
    )
with col2:
    wacc = st.number_input(
        "WACC (%)",
        min_value=1.0,
        max_value=25.0,
        value=st.session_state.get("wacc", 0.08) * 100,
        step=0.5,
    ) / 100.0
    terminal_growth = st.number_input(
        "Terminal Growth Rate (%)",
        min_value=0.0,
        max_value=5.0,
        value=2.0,
        step=0.25,
    ) / 100.0
with col3:
    climate_risk_premium = st.number_input(
        "Climate Risk Premium (% add to WACC)",
        min_value=0.0,
        max_value=5.0,
        value=0.0,
        step=0.25,
        help="Optional uplift to WACC reflecting physical climate risk. Use this as a sensitivity, not as a substitute for scenario comparison.",
    ) / 100.0
    forecast_years = int(st.number_input("Forecast years", min_value=5, max_value=26, value=10))

cashflows: list[float] = []
if dcf_mode == "Enter annual cash flows":
    st.markdown(f"Enter annual free cash flows ({currency_symbol}) - one per year from base year (2025):")
    cf_input = st.text_area(
        f"Cash flows (comma-separated, {currency_symbol})",
        value=",".join(["1000000"] * forecast_years),
        help="Example: 1000000,1050000,1100000",
    )
    try:
        cashflows = [float(value.strip()) for value in cf_input.split(",") if value.strip()]
    except ValueError:
        st.error("Invalid cash flow values.")

st.divider()
st.subheader("Scenario Coverage")
st.caption(
    "The DCF is calculated separately for every selected scenario. Use the valuation scenario toggle below to inspect one model at a time."
)
st.write(", ".join(_scenario_label(scenario_id) for scenario_id in selected_scenarios))

compute_requested = st.button("Compute Climate-Adjusted NPV", type="primary")
if compute_requested:
    total_asset_value = sum(asset.replacement_value for asset in assets)
    input_errors = False

    if dcf_mode == "Replacement value proxy (screening only)":
        cf_list: list[float] = []
        asset_value_for_dcf = total_asset_value
        st.warning(
            "Replacement-value mode is a screening proxy. For decision-grade valuation work, use explicit cash flows and asset-specific assumptions."
        )
    else:
        if len(cashflows) != forecast_years:
            st.error(f"Enter exactly {forecast_years} annual cash flow values.")
            input_errors = True
        cf_list = cashflows[:forecast_years]
        asset_value_for_dcf = total_asset_value

    if not input_errors:
        inputs = DCFInputs(
            name="Portfolio",
            base_year=2025,
            forecast_years=forecast_years,
            terminal_growth_rate=terminal_growth,
            wacc=wacc,
            climate_risk_premium=climate_risk_premium,
            cashflows=cf_list,
            asset_value=asset_value_for_dcf,
        )

        computed_results: list[DCFResult] = []
        for scenario_id in selected_scenarios:
            try:
                computed_results.append(compute_climate_dcf(inputs, annual_df, scenario_id))
            except Exception as exc:
                st.error(f"DCF failed for {scenario_id}: {exc}")

        if computed_results:
            st.session_state.dcf_results = computed_results
            st.session_state.dcf_result_meta = {
                "cash_flow_basis": dcf_mode,
                "forecast_years": forecast_years,
                "wacc": wacc,
                "terminal_growth": terminal_growth,
                "climate_risk_premium": climate_risk_premium,
                "scenario_ids": [result.scenario_id for result in computed_results],
            }
            st.session_state.dcf_view_scenario = computed_results[0].scenario_id
        else:
            st.error("No DCF results computed.")

dcf_results = st.session_state.get("dcf_results", [])
if dcf_results:
    _render_results(dcf_results, currency_code, currency_symbol)
else:
    st.info("Compute the DCF to view scenario-specific valuation models.")
