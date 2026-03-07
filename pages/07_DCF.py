"""
Page 7 – Climate-Adjusted DCF
BSR framework: "From Climate Science to Corporate Strategy"
https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px

from engine.asset_model import Asset as _Asset
from engine.scenario_model import SCENARIOS
from engine.dcf_engine import DCFInputs, compute_climate_dcf, compute_base_dcf, scenario_weighted_npv, DCFResult
from engine.export_engine import export_dcf_xlsx

st.set_page_config(page_title="Climate DCF", page_icon="💹", layout="wide")

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    total_val = sum(a.replacement_value for a in st.session_state.get("assets", []))
    st.metric("Assets", n)
    st.metric("Total Value", f"£{total_val:,.0f}")

st.title("Climate-Adjusted DCF Valuation")
st.markdown("""
**Framework:** BSR "From Climate Science to Corporate Strategy" |
[Download report ↗](https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf)
| [TCFD guidance ↗](https://www.fsb-tcfd.org/recommendations/)

This module translates physical climate risk into **financial impairment of asset value** using a
scenario-based, discounted cash flow framework — enabling climate risk to be integrated into
corporate financial planning, M&A due diligence, and TCFD disclosures.
""")

assets = [_Asset.from_dict(a) if isinstance(a, dict) else a
          for a in st.session_state.get("assets", [])]
annual_df = st.session_state.get("annual_damages", pd.DataFrame())
selected_scenarios = st.session_state.get("selected_scenarios", [])

if not assets:
    st.warning("No assets defined.")
    st.stop()
if annual_df.empty:
    st.warning("Run the damage calculation on the Results page first.")
    st.stop()

# ── Financial inputs ───────────────────────────────────────────────────────
st.divider()
st.subheader("Financial Parameters")

col1, col2, col3 = st.columns(3)
with col1:
    dcf_mode = st.radio(
        "Cash flow basis",
        ["Asset replacement value (proxy)", "Enter annual cash flows"],
        help="Use asset value as a simple proxy, or enter explicit annual free cash flow projections.",
    )
with col2:
    wacc = st.number_input("WACC (%)", min_value=1.0, max_value=25.0,
                           value=st.session_state.get("wacc", 0.08) * 100, step=0.5) / 100.0
    terminal_growth = st.number_input("Terminal Growth Rate (%)", min_value=0.0, max_value=5.0,
                                      value=2.0, step=0.25) / 100.0
with col3:
    climate_risk_premium = st.number_input(
        "Climate Risk Premium (% add to WACC)",
        min_value=0.0, max_value=5.0, value=0.0, step=0.25,
        help="Optional uplift to WACC reflecting physical climate risk. Ranges 0–2% per NGFS/TCFD literature.",
    ) / 100.0
    forecast_years = st.number_input("Forecast years", min_value=5, max_value=26, value=10)

# Cash flows input
cashflows = []
if dcf_mode == "Enter annual cash flows":
    st.markdown("Enter annual free cash flows (£) — one per year from base year (2025):")
    cf_input = st.text_area(
        "Cash flows (comma-separated, £)",
        value=",".join(["1000000"] * int(forecast_years)),
        help="E.g.: 1000000,1050000,1100000,...",
    )
    try:
        cashflows = [float(x.strip()) for x in cf_input.split(",") if x.strip()]
    except ValueError:
        st.error("Invalid cash flow values.")
        st.stop()

# ── Scenario probability weights ───────────────────────────────────────────
st.divider()
st.subheader("Scenario Probability Weights")
st.caption(
    "Assign probabilities to each scenario for the probability-weighted NPV. "
    "Weights must sum to 100%. Per BSR framework: use expert judgement or consult "
    "[NGFS guidance on scenario probabilities](https://www.ngfs.net/ngfs-scenarios-portal/)."
)

weight_cols = st.columns(len(selected_scenarios))
weights = {}
raw_weights = []
for i, sc_id in enumerate(selected_scenarios):
    with weight_cols[i]:
        sc_label = SCENARIOS.get(sc_id, {}).get("label", sc_id)
        w = st.number_input(f"{sc_label} (%)", min_value=0.0, max_value=100.0,
                            value=round(100.0 / len(selected_scenarios), 1),
                            step=5.0, key=f"w_{sc_id}")
        raw_weights.append((sc_id, w))

total_w = sum(w for _, w in raw_weights)
if abs(total_w - 100.0) > 0.1:
    st.warning(f"Weights sum to {total_w:.1f}% — will be normalised to 100%.")
for sc_id, w in raw_weights:
    weights[sc_id] = w / total_w if total_w > 0 else 1.0 / len(raw_weights)

# ── Run ────────────────────────────────────────────────────────────────────
if st.button("▶ Compute Climate-Adjusted NPV", type="primary"):
    total_asset_value = sum(a.replacement_value for a in assets)

    # Build DCF inputs
    if dcf_mode == "Asset replacement value (proxy)":
        cf_list = []
        asset_val_for_dcf = total_asset_value
    else:
        cf_list = cashflows[:int(forecast_years)]
        asset_val_for_dcf = total_asset_value

    inputs = DCFInputs(
        name="Portfolio",
        base_year=2025,
        forecast_years=int(forecast_years),
        terminal_growth_rate=terminal_growth,
        wacc=wacc,
        climate_risk_premium=climate_risk_premium,
        cashflows=cf_list,
        asset_value=asset_val_for_dcf,
    )

    dcf_results = []
    for sc_id in selected_scenarios:
        try:
            res = compute_climate_dcf(inputs, annual_df, sc_id)
            dcf_results.append(res)
        except Exception as e:
            st.error(f"DCF failed for {sc_id}: {e}")

    if not dcf_results:
        st.error("No DCF results computed.")
        st.stop()

    # ── Results display ────────────────────────────────────────────────────
    st.divider()
    st.subheader("Results")

    base_npv = dcf_results[0].npv_base

    # Summary table
    sc_rows = []
    for r in dcf_results:
        sc_rows.append({
            "Scenario": r.label,
            "Base NPV (£)": f"£{r.npv_base:,.0f}",
            "Climate-Adjusted NPV (£)": f"£{r.npv_climate:,.0f}",
            "NPV Impairment (£)": f"£{r.npv_delta:,.0f}",
            "Impairment (%)": f"{r.npv_delta_pct:.2f}%",
            "PV Damages (£)": f"£{r.total_pv_damages:,.0f}",
        })
    st.dataframe(pd.DataFrame(sc_rows), use_container_width=True)

    # Probability-weighted NPV
    w_npv_climate, w_npv_adapted = scenario_weighted_npv(dcf_results, weights)
    st.metric(
        "Probability-Weighted Climate-Adjusted NPV",
        f"£{w_npv_climate:,.0f}",
        delta=f"£{w_npv_climate - base_npv:,.0f} vs base",
        delta_color="inverse",
    )

    # Waterfall chart
    st.subheader("NPV Waterfall — Base vs Climate-Adjusted")
    fig = go.Figure(go.Waterfall(
        x=["Base NPV"] + [r.label for r in dcf_results] + ["Probability-Weighted"],
        y=[base_npv] + [r.npv_delta for r in dcf_results] + [w_npv_climate - base_npv],
        measure=["absolute"] + ["relative"] * len(dcf_results) + ["total"],
        text=[f"£{base_npv:,.0f}"] + [f"£{r.npv_delta:,.0f}" for r in dcf_results] + [f"£{w_npv_climate:,.0f}"],
        connector={"line": {"color": "#888"}},
        decreasing={"marker": {"color": "#e74c3c"}},
        increasing={"marker": {"color": "#27ae60"}},
        totals={"marker": {"color": "#2980b9"}},
    ))
    fig.update_layout(height=380, margin=dict(l=20, r=20, t=20, b=20),
                      waterfallgap=0.3)
    st.plotly_chart(fig, use_container_width=True)

    # Annual damage stream
    st.subheader("Annual Damage Stream by Scenario")
    fig2 = go.Figure()
    for r in dcf_results:
        if not r.annual_detail.empty:
            fig2.add_trace(go.Scatter(
                x=r.annual_detail["year"], y=r.annual_detail["climate_damage"],
                mode="lines", name=r.label,
                line=dict(color=SCENARIOS.get(r.scenario_id, {}).get("color", "#888"), width=2),
            ))
    fig2.update_layout(xaxis_title="Year", yaxis_title="Annual Climate Damage (£)",
                       height=300, margin=dict(l=20,r=20,t=20,b=20),
                       hovermode="x unified",
                       legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig2, use_container_width=True)

    # BSR framework explainer
    with st.expander("📖 BSR Methodology: From Climate Science to Corporate Strategy"):
        st.markdown("""
**Framework Reference:** BSR "From Climate Science to Corporate Strategy"
[https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf](https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf)

**Step 1 — Identify exposures**
Map physical assets to climate hazard zones using location data and scenario-based hazard projections.

**Step 2 — Quantify financial impact**
Translate hazard intensity into asset damage using vulnerability functions (HAZUS, JRC).
Compute annual EAD = ∫ damage(AEP) d(AEP) for each year 2025–2050.

**Step 3 — Integrate into financial planning**
Subtract annual damage stream from cash flows:
> CF_adjusted_t = CF_base_t − EAD_t

Compute climate-adjusted NPV using standard DCF methodology.

**Step 4 — Scenario comparison**
Run under multiple NGFS/IEA/IPCC scenarios. Weight by probability to get expected climate-adjusted value.

**Step 5 — Adaptation investment**
Evaluate adaptation measures (see Adaptation page): measures with CBR > 1 increase climate-adjusted NPV.

**TCFD Alignment**
- *Strategy*: disclose financial impact under different warming scenarios
- *Risk Management*: quantify physical risk exposure using EAD methodology
- *Metrics & Targets*: total PV of climate damages, NPV impairment %, adaptation ROI
        """)

    # Export
    sc_comparison_df = pd.DataFrame([{
        "Scenario": r.label, "Scenario ID": r.scenario_id,
        "Base NPV (£)": r.npv_base, "Climate NPV (£)": r.npv_climate,
        "NPV Delta (£)": r.npv_delta, "NPV Delta (%)": r.npv_delta_pct,
        "PV Damages (£)": r.total_pv_damages,
    } for r in dcf_results])

    xlsx = export_dcf_xlsx(dcf_results, sc_comparison_df)
    st.download_button(
        "⬇️ Download DCF Analysis (.xlsx)", data=xlsx,
        file_name="climate_adjusted_dcf.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
