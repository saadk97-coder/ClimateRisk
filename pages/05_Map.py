"""
Page 5 – Map: Interactive risk map with satellite imagery, OSM building footprints,
and damage overlays.
"""

import streamlit as st
import pandas as pd
import numpy as np
import requests
import json

from engine.asset_model import Asset as _Asset
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

assets = [_Asset.from_dict(a) if isinstance(a, dict) else a
          for a in st.session_state.get("assets", [])]
results = st.session_state.get("results", [])
annual_df = st.session_state.get("annual_damages", pd.DataFrame())

if not assets:
    st.warning("No assets defined.")
    st.stop()

# ── Controls ───────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
selected_scenarios = st.session_state.get("selected_scenarios", list(SCENARIOS.keys())[:1])
with col1:
    map_scenario = st.selectbox("Scenario", selected_scenarios,
                                format_func=lambda s: SCENARIOS.get(s, {}).get("label", s))
with col2:
    map_year = st.selectbox("Year", [2025, 2030, 2040, 2050], index=2)
with col3:
    colour_by = st.selectbox("Colour by",
                             ["EAD %", "Total EAD (£)", "Flood EAD", "Wind EAD", "Wildfire EAD", "Heat EAD"])
with col4:
    tile_layer = st.selectbox("Map layer",
                              ["Street Map", "Satellite", "Satellite + Labels", "Terrain"])

TILE_URLS = {
    "Street Map": "CartoDB positron",
    "Satellite": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "Satellite + Labels": None,  # handled separately
    "Terrain": "https://stamen-tiles-{s}.a.ssl.fastly.net/terrain/{z}/{x}/{y}.jpg",
}

show_buildings = st.checkbox("Show OSM building footprints (per-asset, within 150m)", value=False)

# ── Build map dataframe ────────────────────────────────────────────────────
colour_map = {
    "EAD %": "ead_pct", "Total EAD (£)": "total_ead",
    "Flood EAD": "ead_flood", "Wind EAD": "ead_wind",
    "Wildfire EAD": "ead_wildfire", "Heat EAD": "ead_heat",
}
colour_col = colour_map.get(colour_by, "ead_pct")

# Pull from annual damages (year-specific) if available
if not annual_df.empty:
    ann_yr = annual_df[
        (annual_df["scenario_id"] == map_scenario) & (annual_df["year"] == map_year)
    ]
    ead_by_asset_haz = (
        ann_yr.groupby(["asset_id", "hazard"])["ead"]
        .sum().unstack(fill_value=0.0).reset_index()
    )
    ead_totals = ann_yr.groupby("asset_id")["ead"].sum().reset_index()
    ead_totals.columns = ["asset_id", "total_ead"]
else:
    ead_by_asset_haz = pd.DataFrame()
    ead_totals = pd.DataFrame()

rows = []
for asset in assets:
    row = {"asset_id": asset.id, "name": asset.name, "lat": asset.lat, "lon": asset.lon,
           "value": asset.replacement_value, "asset_type": asset.asset_type,
           "year_built": asset.year_built, "material": asset.construction_material,
           "region": asset.region}
    row["total_ead"] = 0.0
    row["ead_pct"] = 0.0
    for haz in ["flood", "wind", "wildfire", "heat"]:
        row[f"ead_{haz}"] = 0.0

    if not ead_totals.empty:
        m = ead_totals[ead_totals["asset_id"] == asset.id]
        if not m.empty:
            row["total_ead"] = float(m["total_ead"].iloc[0])
            row["ead_pct"] = row["total_ead"] / asset.replacement_value * 100 if asset.replacement_value > 0 else 0.0

    if not ead_by_asset_haz.empty and "asset_id" in ead_by_asset_haz.columns:
        m = ead_by_asset_haz[ead_by_asset_haz["asset_id"] == asset.id]
        if not m.empty:
            for haz in ["flood", "wind", "wildfire", "heat"]:
                if haz in m.columns:
                    row[f"ead_{haz}"] = float(m[haz].iloc[0])
    rows.append(row)

map_df = pd.DataFrame(rows)

# ── OSM building footprints ────────────────────────────────────────────────
def get_osm_buildings(lat: float, lon: float, radius: int = 150) -> list:
    """Fetch building footprints from OpenStreetMap Overpass API.
    Source: https://www.openstreetmap.org/ | License: ODbL"""
    query = f"""
    [out:json][timeout:20];
    way["building"](around:{radius},{lat},{lon});
    (._;>;);
    out body;
    """
    try:
        r = requests.post("https://overpass-api.de/api/interpreter",
                          data=query, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        nodes = {el["id"]: (el["lon"], el["lat"])
                 for el in data["elements"] if el["type"] == "node"}
        buildings = []
        for el in data["elements"]:
            if el["type"] == "way" and "building" in el.get("tags", {}):
                coords = [nodes[n] for n in el["nodes"] if n in nodes]
                if coords:
                    tags = el.get("tags", {})
                    buildings.append({
                        "coords": coords,
                        "building_type": tags.get("building", "yes"),
                        "levels": tags.get("building:levels", "?"),
                        "name": tags.get("name", ""),
                        "height": tags.get("height", "?"),
                    })
        return buildings
    except Exception:
        return []


# ── Folium map ────────────────────────────────────────────────────────────
try:
    import folium
    from streamlit_folium import st_folium

    center_lat = float(map_df["lat"].mean()) if len(map_df) > 0 else 51.5
    center_lon = float(map_df["lon"].mean()) if len(map_df) > 0 else -0.1

    tile_url = TILE_URLS.get(tile_layer, "CartoDB positron")
    if tile_layer == "Street Map":
        m = folium.Map(location=[center_lat, center_lon], zoom_start=6, tiles="CartoDB positron")
    elif tile_layer in ("Satellite", "Satellite + Labels"):
        m = folium.Map(location=[center_lat, center_lon], zoom_start=6, tiles=None)
        folium.TileLayer(
            tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            attr="Tiles © Esri — Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community",
            name="ESRI Satellite",
        ).add_to(m)
        if tile_layer == "Satellite + Labels":
            folium.TileLayer(
                tiles="https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
                attr="Esri",
                name="Labels",
                overlay=True,
            ).add_to(m)
    elif tile_layer == "Terrain":
        m = folium.Map(location=[center_lat, center_lon], zoom_start=6,
                       tiles="https://stamen-tiles-a.a.ssl.fastly.net/terrain/{z}/{x}/{y}.jpg",
                       attr="Map tiles by Stamen Design; data © OpenStreetMap contributors")
    else:
        m = folium.Map(location=[center_lat, center_lon], zoom_start=6)

    max_val = map_df[colour_col].max() if colour_col in map_df.columns else 1.0
    max_val = max_val if max_val > 0 else 1.0

    def risk_colour(val):
        frac = min(val / max_val, 1.0)
        r = int(255 * frac)
        g = int(255 * (1 - frac))
        return f"#{r:02x}{g:02x}00"

    selected_asset_for_buildings = None

    for _, row in map_df.iterrows():
        val = row.get(colour_col, 0.0)
        color = risk_colour(val)
        radius = max(8, min(28, 8 + val / max_val * 20))

        popup_html = f"""
        <div style="font-family:sans-serif;font-size:13px;min-width:220px">
          <b>{row['name']}</b><br>
          <hr style="margin:4px 0">
          <b>Type:</b> {row['asset_type']}<br>
          <b>Material:</b> {row.get('material','')}<br>
          <b>Year built:</b> {row.get('year_built','')}<br>
          <b>Region:</b> {row.get('region','')}<br>
          <b>Value:</b> £{row['value']:,.0f}<br>
          <hr style="margin:4px 0">
          <b>EAD ({map_year}):</b> £{row.get('total_ead',0):,.0f}<br>
          <b>EAD %:</b> {row.get('ead_pct',0):.3f}%<br>
          <b>Flood EAD:</b> £{row.get('ead_flood',0):,.0f}<br>
          <b>Wind EAD:</b> £{row.get('ead_wind',0):,.0f}<br>
          <b>Wildfire EAD:</b> £{row.get('ead_wildfire',0):,.0f}<br>
          <b>Heat EAD:</b> £{row.get('ead_heat',0):,.0f}
        </div>
        """
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=radius, color=color,
            fill=True, fill_color=color, fill_opacity=0.75,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"📍 {row['name']} | EAD: £{row.get('total_ead',0):,.0f}",
        ).add_to(m)

    # OSM building footprints
    if show_buildings:
        for _, row in map_df.iterrows():
            buildings = get_osm_buildings(row["lat"], row["lon"], radius=150)
            for b in buildings[:30]:
                coords_ll = [(c[1], c[0]) for c in b["coords"]]
                tooltip = (
                    f"Building type: {b['building_type']} | "
                    f"Levels: {b['levels']} | Height: {b['height']}"
                )
                folium.Polygon(
                    locations=coords_ll,
                    color="#e67e22", weight=1.5,
                    fill=True, fill_color="#f39c12", fill_opacity=0.3,
                    tooltip=tooltip,
                ).add_to(m)

    folium.LayerControl().add_to(m)

    st_folium(m, use_container_width=True, height=620)

    if show_buildings:
        st.caption(
            "Building footprints: © [OpenStreetMap](https://www.openstreetmap.org/) contributors (ODbL). "
            "Data via [Overpass API](https://overpass-api.de/). "
            "Satellite imagery: © [Esri](https://www.esri.com/en-us/home) and contributors."
        )
    else:
        st.caption("Satellite imagery: © Esri and contributors.")

except ImportError:
    st.warning("folium / streamlit-folium not installed.")
    if not map_df.empty:
        st.map(map_df[["lat", "lon"]].rename(columns={"lat": "latitude", "lon": "longitude"}))

# ── Risk ranking table ─────────────────────────────────────────────────────
st.divider()
st.subheader("Asset Risk Ranking")
if not map_df.empty and "ead_pct" in map_df.columns:
    rank_df = map_df[["name", "asset_type", "value", "total_ead", "ead_pct"]].sort_values("ead_pct", ascending=False).reset_index(drop=True)
    rank_df.index += 1
    rank_df.columns = ["Asset", "Type", "Value (£)", "EAD (£)", "EAD (%)"]
    rank_df["Value (£)"] = rank_df["Value (£)"].apply(lambda x: f"£{x:,.0f}")
    rank_df["EAD (£)"] = rank_df["EAD (£)"].apply(lambda x: f"£{x:,.0f}")
    rank_df["EAD (%)"] = rank_df["EAD (%)"].apply(lambda x: f"{x:.3f}%")
    st.dataframe(rank_df, use_container_width=True)
