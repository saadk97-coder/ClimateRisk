"""
Page 2 – Scenarios: NGFS Phase V / IEA WEO 2023 / IPCC AR6 selector + financial parameters.
"""

import streamlit as st
import plotly.graph_objects as go
from engine.scenario_model import SCENARIOS, SCENARIO_PROVIDERS, PROVIDER_SOURCES, list_scenarios

st.set_page_config(page_title="Scenarios", page_icon="🌡️", layout="wide")

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    total_val = sum(a.replacement_value for a in st.session_state.get("assets", []))
    st.metric("Assets", n)
    st.metric("Total Value", f"£{total_val:,.0f}")

st.title("Climate Scenarios & Time Horizons")

# ── Scenario Provider ──────────────────────────────────────────────────────
st.subheader("Scenario Framework")

provider_options = list(SCENARIO_PROVIDERS.keys())
current_provider = st.session_state.get("scenario_provider", "NGFS Phase V")

col_prov, col_src = st.columns([3, 4])
with col_prov:
    new_provider = st.selectbox(
        "Select framework",
        provider_options,
        index=provider_options.index(current_provider),
        help="Choose the climate scenario framework. NGFS Phase V is standard for financial institutions (TCFD, TNFD).",
    )
with col_src:
    src_url = PROVIDER_SOURCES.get(new_provider, "")
    st.markdown(
        f"""
        | Framework | Source |
        |---|---|
        | **NGFS Phase V** | [NGFS Scenarios Portal](https://www.ngfs.net/ngfs-scenarios-portal/) |
        | **IEA WEO 2023** | [IEA World Energy Outlook 2023](https://www.iea.org/reports/world-energy-outlook-2023) |
        | **IPCC AR6** | [IPCC AR6 WG1 SPM Table 1](https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/) |
        """
    )

active_scenarios = SCENARIO_PROVIDERS[new_provider]

# ── Scenario selector ──────────────────────────────────────────────────────
st.divider()
st.subheader(f"Select Scenarios — {new_provider}")

if new_provider == "NGFS Phase V":
    st.caption(
        "NGFS Phase V (November 2023) uses GCAM 6.0 and REMIND-MAgPIE 3.2 IAMs with MAGICC7 temperature outputs. "
        "Adds 'Divergent Net Zero' scenario vs Phase IV. "
        "[Technical Note ↗](https://www.ngfs.net/sites/default/files/medias/documents/ngfs_climate_scenarios_phase_v.pdf)"
    )
elif new_provider == "IEA WEO 2023":
    st.caption(
        "IEA World Energy Outlook 2023 scenarios cover the global energy system through 2050. "
        "[Full report ↗](https://www.iea.org/reports/world-energy-outlook-2023)"
    )
elif new_provider == "IPCC AR6":
    st.caption(
        "IPCC AR6 Shared Socioeconomic Pathways (SSPs) from the Sixth Assessment Report (2021). "
        "Best-estimate (median) global mean surface temperature above 1850–1900 baseline. "
        "[SPM Table 1 ↗](https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/)"
    )

prev_scenarios = st.session_state.get("selected_scenarios", ["current_policies", "net_zero_2050"])
# Filter to only scenarios in the active provider
prev_in_provider = [s for s in prev_scenarios if s in active_scenarios]
if not prev_in_provider:
    prev_in_provider = list(active_scenarios.keys())[:2]

cols = st.columns(len(active_scenarios))
new_scenarios = []
for i, (sc_id, sc_data) in enumerate(active_scenarios.items()):
    with cols[i]:
        cat_icon = {"orderly": "🟢", "disorderly": "🟡", "intermediate": "🟠", "hot_house": "🔴"}.get(sc_data.get("category", ""), "⚪")
        checked = st.checkbox(
            f"{cat_icon} **{sc_data['label']}**",
            value=sc_id in prev_in_provider,
            key=f"sc_{new_provider}_{sc_id}",
        )
        if checked:
            new_scenarios.append(sc_id)
        st.caption(f"*{sc_data['ssp']}*")
        st.markdown(f"<small>{sc_data['description']}</small>", unsafe_allow_html=True)
        warming_str = " / ".join([f"{yr}: **{wm}°C**" for yr, wm in list(sc_data["warming"].items()) if yr in (2030, 2050, 2080)])
        st.caption(warming_str)

if not new_scenarios:
    st.warning("Select at least one scenario.")

# ── Financial parameters ───────────────────────────────────────────────────
st.divider()
st.subheader("Financial Parameters")

col1, col2, col3 = st.columns(3)
with col1:
    new_discount_rate = st.slider(
        "Discount Rate (%)",
        min_value=0.5, max_value=12.0,
        value=st.session_state.get("discount_rate", 0.035) * 100,
        step=0.5,
        help="Applied to PV of annual climate damages and adaptation benefits. 3.5% = HM Treasury Green Book / standard green finance rate.",
    ) / 100.0
with col2:
    new_wacc = st.slider(
        "WACC (%) — for DCF",
        min_value=2.0, max_value=20.0,
        value=st.session_state.get("wacc", 0.08) * 100,
        step=0.5,
        help="Weighted Average Cost of Capital for climate-adjusted DCF valuation.",
    ) / 100.0
with col3:
    st.markdown("**Reference rates**")
    st.markdown("- HM Treasury Green Book: **3.5%**")
    st.markdown("- NGFS green finance: **3.5%**")
    st.markdown("- [TCFD guidance ↗](https://www.fsb-tcfd.org/recommendations/)")

# ── Warming chart ──────────────────────────────────────────────────────────
st.divider()
st.subheader("Projected Warming Trajectories")

fig = go.Figure()
for sc_id, sc_data in active_scenarios.items():
    if sc_id in new_scenarios:
        yrs = list(sc_data["warming"].keys())
        temps = list(sc_data["warming"].values())
        fig.add_trace(go.Scatter(
            x=yrs, y=temps,
            mode="lines+markers",
            name=sc_data["label"],
            line=dict(color=sc_data.get("color", "#888"), width=2),
            hovertemplate=f"<b>{sc_data['label']}</b><br>Year: %{{x}}<br>Warming: %{{y:.1f}} °C<extra></extra>",
        ))

fig.add_hline(y=1.5, line_dash="dot", line_color="#27ae60", annotation_text="Paris 1.5 °C", annotation_position="right")
fig.add_hline(y=2.0, line_dash="dot", line_color="#e67e22", annotation_text="Paris 2.0 °C", annotation_position="right")
fig.update_layout(
    xaxis_title="Year",
    yaxis_title="Global Mean Warming above pre-industrial (°C)",
    yaxis=dict(range=[0.8, 5.0]),
    hovermode="x unified",
    height=380,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    margin=dict(l=20, r=80, t=20, b=20),
)
st.plotly_chart(fig, use_container_width=True)
st.caption(
    "Sources: "
    "[NGFS Phase V (2023)](https://www.ngfs.net/ngfs-scenarios-portal/) | "
    "[IEA WEO 2023](https://www.iea.org/reports/world-energy-outlook-2023) | "
    "[IPCC AR6 WG1 SPM Table 1](https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/)"
)

# ── Save ───────────────────────────────────────────────────────────────────
st.divider()
if st.button("💾 Save Configuration", type="primary"):
    st.session_state.scenario_provider = new_provider
    st.session_state.selected_scenarios = new_scenarios
    st.session_state.selected_horizons = list(range(2025, 2051))
    st.session_state.discount_rate = new_discount_rate
    st.session_state.wacc = new_wacc
    st.success(
        f"Saved: {new_provider} | {len(new_scenarios)} scenario(s) | "
        f"Annual 2025–2050 | Discount rate {new_discount_rate*100:.1f}% | WACC {new_wacc*100:.1f}%"
    )
