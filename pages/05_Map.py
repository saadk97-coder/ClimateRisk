"""
Page 5 – Map: Interactive asset map with damage overlay.
"""

import streamlit as st
import pandas as pd
import numpy as np

from engine.scenario_model import SCENARIOS
from engine.portfolio_aggregator import results_to_dataframe

st.set_page_config(page_title="Map", page_icon="🗺️", layout="wide")

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    total_val = sum(a.replacement_value for a in st.session_state.get("assets", []))
    st.metric("Assets", n)
    st.metric("Total Value", f"£{total_val:,.0f}")

st.title("Risk Map")

from engine.asset_model import Asset as _Asset
assets = [_Asset.from_dict(a) if isinstance(a, dict) else a for a in st.session_state.get("assets", [])]
results = st.session_state.get("results", [])

if not assets:
    st.warning("No assets defined.")
    st.stop()

# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)
selected_scenarios = st.session_state.get("selected_scenarios", [])
selected_horizons = st.session_state.get("selected_horizons", [2050])

with col1:
    map_scenario = st.selectbox(
        "Scenario",
        selected_scenarios if selected_scenarios else list(SCENARIOS.keys()),
        format_func=lambda s: SCENARIOS.get(s, {}).get("label", s),
    )
with col2:
    map_year = st.selectbox("Year", selected_horizons if selected_horizons else [2050])
with col3:
    colour_by = st.selectbox("Colour by", ["EAD %", "Total EAD (£)", "Hazard: Flood", "Hazard: Wind", "Hazard: Wildfire", "Hazard: Heat"])

# ---------------------------------------------------------------------------
# Build map dataframe
# ---------------------------------------------------------------------------
asset_dict = {a.id: a for a in assets}

if results:
    df_res = results_to_dataframe(results)
    df_view = df_res[
        (df_res["scenario_id"] == map_scenario) & (df_res["year"] == map_year)
    ].copy()
else:
    df_view = pd.DataFrame()

rows = []
for asset in assets:
    row = {
        "asset_id": asset.id,
        "name": asset.name,
        "lat": asset.lat,
        "lon": asset.lon,
        "value": asset.replacement_value,
        "asset_type": asset.asset_type,
    }
    if not df_view.empty:
        match = df_view[df_view["asset_id"] == asset.id]
        if not match.empty:
            row["ead_pct"] = float(match["total_ead_pct"].iloc[0])
            row["total_ead"] = float(match["total_ead"].iloc[0])
            for haz in ["flood", "wind", "wildfire", "heat"]:
                col_name = f"ead_{haz}"
                if col_name in match.columns:
                    row[f"ead_{haz}"] = float(match[col_name].iloc[0]) if pd.notna(match[col_name].iloc[0]) else 0.0
                else:
                    row[f"ead_{haz}"] = 0.0
        else:
            row["ead_pct"] = 0.0
            row["total_ead"] = 0.0
            for haz in ["flood", "wind", "wildfire", "heat"]:
                row[f"ead_{haz}"] = 0.0
    else:
        row["ead_pct"] = 0.0
        row["total_ead"] = 0.0
        for haz in ["flood", "wind", "wildfire", "heat"]:
            row[f"ead_{haz}"] = 0.0
    rows.append(row)

map_df = pd.DataFrame(rows)

# Determine colour metric
colour_map = {
    "EAD %": "ead_pct",
    "Total EAD (£)": "total_ead",
    "Hazard: Flood": "ead_flood",
    "Hazard: Wind": "ead_wind",
    "Hazard: Wildfire": "ead_wildfire",
    "Hazard: Heat": "ead_heat",
}
colour_col = colour_map.get(colour_by, "ead_pct")

# ---------------------------------------------------------------------------
# Folium map
# ---------------------------------------------------------------------------
try:
    import folium
    from streamlit_folium import st_folium

    if len(map_df) > 0:
        center_lat = float(map_df["lat"].mean())
        center_lon = float(map_df["lon"].mean())
    else:
        center_lat, center_lon = 51.5, -0.1

    m = folium.Map(location=[center_lat, center_lon], zoom_start=6, tiles="CartoDB positron")

    # Colour scale: green (low) → red (high)
    max_val = map_df[colour_col].max() if colour_col in map_df.columns else 1.0
    max_val = max_val if max_val > 0 else 1.0

    def risk_colour(val):
        fraction = min(val / max_val, 1.0)
        r = int(255 * fraction)
        g = int(255 * (1 - fraction))
        return f"#{r:02x}{g:02x}00"

    for _, row in map_df.iterrows():
        val = row.get(colour_col, 0.0)
        color = risk_colour(val)
        radius = max(8, min(25, 8 + val / max_val * 17))

        popup_html = f"""
        <b>{row['name']}</b><br>
        Type: {row['asset_type']}<br>
        Value: £{row['value']:,.0f}<br>
        EAD: £{row.get('total_ead', 0):,.0f}<br>
        EAD %: {row.get('ead_pct', 0):.3f}%<br>
        Flood EAD: £{row.get('ead_flood', 0):,.0f}<br>
        Wind EAD: £{row.get('ead_wind', 0):,.0f}<br>
        Wildfire EAD: £{row.get('ead_wildfire', 0):,.0f}<br>
        Heat EAD: £{row.get('ead_heat', 0):,.0f}
        """

        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=f"{row['name']} | EAD%: {row.get('ead_pct', 0):.3f}%",
        ).add_to(m)

    # Legend
    legend_html = f"""
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 1000;
                background: white; padding: 10px; border-radius: 5px; border: 1px solid #ccc;
                font-size: 13px;">
        <b>{colour_by}</b><br>
        <span style="background:green; color:white; padding:2px 8px;">Low</span>
        &nbsp;→&nbsp;
        <span style="background:red; color:white; padding:2px 8px;">High</span><br>
        Max: {max_val:.2f}
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    st_folium(m, use_container_width=True, height=600)

except ImportError:
    st.warning("folium / streamlit-folium not installed. Showing basic map.")
    if not map_df.empty:
        st.map(map_df[["lat", "lon"]].rename(columns={"lat": "latitude", "lon": "longitude"}))

# ---------------------------------------------------------------------------
# Summary table below map
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Asset Risk Ranking")
if not map_df.empty and "ead_pct" in map_df.columns:
    rank_df = map_df[["name", "asset_type", "value", "total_ead", "ead_pct"]].sort_values(
        "ead_pct", ascending=False
    ).reset_index(drop=True)
    rank_df.index += 1
    rank_df.columns = ["Asset", "Type", "Value (£)", "EAD (£)", "EAD (%)"]
    rank_df["Value (£)"] = rank_df["Value (£)"].apply(lambda x: f"£{x:,.0f}")
    rank_df["EAD (£)"] = rank_df["EAD (£)"].apply(lambda x: f"£{x:,.0f}")
    rank_df["EAD (%)"] = rank_df["EAD (%)"].apply(lambda x: f"{x:.3f}%")
    st.dataframe(rank_df, use_container_width=True)
