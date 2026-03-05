"""
Page 2 – Scenarios: NGFS scenario selector + time horizon + discount rate.
"""

import streamlit as st
from engine.scenario_model import SCENARIOS, list_horizons

st.set_page_config(page_title="Scenarios", page_icon="🌡️", layout="wide")

# ---------------------------------------------------------------------------
# Sidebar summary
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    total_val = sum(a.replacement_value for a in st.session_state.get("assets", []))
    st.metric("Assets", n)
    st.metric("Total Value", f"£{total_val:,.0f}")

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
st.title("Climate Scenarios & Time Horizons")
st.markdown(
    "Select the NGFS Phase 4 scenarios and time horizons for the risk assessment. "
    "Multiple selections allow scenario comparison."
)

# Scenario selector
st.subheader("NGFS Phase 4 Scenarios")

SCENARIO_COLORS = {
    "net_zero_2050": "🟢",
    "below_2c": "🟡",
    "delayed_transition": "🟠",
    "ndcs_only": "🔴",
    "current_policies": "⚫",
}

selected_scenarios = st.session_state.get("selected_scenarios", ["current_policies", "net_zero_2050"])
selected_horizons = st.session_state.get("selected_horizons", [2050])
discount_rate = st.session_state.get("discount_rate", 0.035)

cols = st.columns(len(SCENARIOS))
new_scenarios = []
for i, (sc_id, sc_data) in enumerate(SCENARIOS.items()):
    with cols[i]:
        icon = SCENARIO_COLORS.get(sc_id, "⚪")
        checked = st.checkbox(
            f"{icon} **{sc_data['label']}**",
            value=sc_id in selected_scenarios,
            key=f"sc_{sc_id}",
        )
        if checked:
            new_scenarios.append(sc_id)

        st.caption(f"*{sc_data['ssp']}*")
        st.markdown(f"<small>{sc_data['description']}</small>", unsafe_allow_html=True)

        # Warming table
        warming_str = " | ".join([f"{yr}: +{wm}°C" for yr, wm in sc_data["warming"].items()])
        st.caption(warming_str)

if not new_scenarios:
    st.warning("Please select at least one scenario.")

# Time horizon
st.divider()
st.subheader("Time Horizons")
all_horizons = list_horizons()
horizon_cols = st.columns(len(all_horizons))
new_horizons = []
for i, yr in enumerate(all_horizons):
    with horizon_cols[i]:
        if st.checkbox(str(yr), value=yr in selected_horizons, key=f"yr_{yr}"):
            new_horizons.append(yr)

if not new_horizons:
    st.warning("Please select at least one time horizon.")

# Financial parameters
st.divider()
st.subheader("Financial Parameters")
col1, col2 = st.columns(2)
with col1:
    new_discount_rate = st.slider(
        "Discount Rate (%)",
        min_value=0.5,
        max_value=10.0,
        value=discount_rate * 100,
        step=0.5,
        help="Used for NPV of adaptation benefits. 3.5% is a standard green finance rate.",
    ) / 100.0
with col2:
    st.markdown("**Interpretation**")
    st.markdown(f"- Green finance benchmark: **3.5%**")
    st.markdown(f"- UK HM Treasury Green Book: **3.5%**")
    st.markdown(f"- Higher rates discount future damages more heavily")

# Scenario warming chart
st.divider()
st.subheader("Projected Warming by Scenario")

import plotly.graph_objects as go

fig = go.Figure()
for sc_id, sc_data in SCENARIOS.items():
    if sc_id in new_scenarios:
        yrs = list(sc_data["warming"].keys())
        temps = list(sc_data["warming"].values())
        fig.add_trace(go.Scatter(
            x=yrs, y=temps,
            mode="lines+markers",
            name=sc_data["label"],
            line=dict(color=sc_data.get("color", "#888"), width=2),
        ))

fig.update_layout(
    xaxis_title="Year",
    yaxis_title="Global Mean Warming (°C above pre-industrial)",
    yaxis=dict(range=[1.0, 5.0]),
    hovermode="x unified",
    height=350,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    margin=dict(l=20, r=20, t=20, b=20),
)
fig.add_hline(y=1.5, line_dash="dot", line_color="green", annotation_text="Paris 1.5°C")
fig.add_hline(y=2.0, line_dash="dot", line_color="orange", annotation_text="Paris 2.0°C")
st.plotly_chart(fig, use_container_width=True)

# Save
st.divider()
if st.button("💾 Save Configuration", type="primary"):
    st.session_state.selected_scenarios = new_scenarios
    st.session_state.selected_horizons = new_horizons
    st.session_state.discount_rate = new_discount_rate
    st.success(
        f"Saved: {len(new_scenarios)} scenario(s), {len(new_horizons)} horizon(s), "
        f"discount rate {new_discount_rate*100:.1f}%"
    )
