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
from engine.fmt import fmt as _fmt_cur, currency_symbol as _currency_symbol

st.set_page_config(page_title="Map", page_icon="🗺️", layout="wide")

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    total_val = sum(a.replacement_value for a in st.session_state.get("assets", []))
    st.metric("Assets", n)
    _cur = st.session_state.get("currency_code", "GBP")
    st.metric("Total Value", _fmt_cur(total_val, _cur))

st.title("Risk Map")

assets = [_Asset.from_dict(a) if isinstance(a, dict) else a
          for a in st.session_state.get("assets", [])]
results = st.session_state.get("results", [])
annual_df = st.session_state.get("annual_damages", pd.DataFrame())
_cur = st.session_state.get("currency_code", "GBP")
_sym = _currency_symbol(_cur)

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
                             [f"EAD %", f"Total EAD ({_sym})", "Flood EAD", "Wind EAD",
                              "Wildfire EAD", "Heat EAD", "Water Stress"])
with col4:
    tile_layer = st.selectbox("Map layer",
                              ["Street Map", "Satellite", "Satellite + Labels", "Terrain"])

TILE_URLS = {
    "Street Map": "CartoDB positron",
    "Satellite": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "Satellite + Labels": None,  # handled separately
    "Terrain": "https://stamen-tiles-{s}.a.ssl.fastly.net/terrain/{z}/{x}/{y}.jpg",
}

col_bld, col_ws, col_tc = st.columns(3)
with col_bld:
    show_buildings = st.checkbox("Show OSM building footprints (per-asset, within 150m)", value=False)
with col_ws:
    show_water_stress = st.checkbox(
        "Show water stress indicators (WRI Aqueduct)",
        value=False,
        help=(
            "Fetches Baseline Water Stress (BWS) scores from WRI Aqueduct 4.0 for each asset location. "
            "BWS = total annual withdrawals / available renewable water supply (0–5 scale). "
            "Source: Kuzma et al. (2023) https://doi.org/10.46830/writn.23.00061"
        ),
    )
with col_tc:
    show_cyclone_tracks = st.checkbox(
        "Show tropical cyclone tracks (IBTrACS)",
        value=False,
        help=(
            "Overlays representative historical tropical cyclone tracks near portfolio assets. "
            "Track data from IBTrACS (Knapp et al. 2010). Colour intensity indicates "
            "storm strength on the Saffir-Simpson scale. Wind amplification is automatically "
            "applied to assets within cyclone basins."
        ),
    )

# ── Build map dataframe ────────────────────────────────────────────────────
colour_map = {
    "EAD %": "ead_pct", f"Total EAD ({_sym})": "total_ead",
    "Flood EAD": "ead_flood", "Wind EAD": "ead_wind",
    "Wildfire EAD": "ead_wildfire", "Heat EAD": "ead_heat",
    "Water Stress": "water_stress_score",
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

# ── Water stress fetch ─────────────────────────────────────────────────────
water_stress_scores: dict = {}
if show_water_stress or colour_by == "Water Stress":
    from engine.water_stress import fetch_aqueduct_bws, get_water_stress_rating
    ws_status = st.empty()
    with ws_status.container():
        with st.spinner("Fetching water stress scores (WRI Aqueduct 4.0)…"):
            for asset in assets:
                bws = fetch_aqueduct_bws(asset.lat, asset.lon)
                if bws is None:
                    # Regional fallback
                    from engine.water_stress import _REGIONAL_BWS_BASELINE
                    from engine.hazard_fetcher import get_region_zone
                    zone = get_region_zone(asset.region)
                    bws = _REGIONAL_BWS_BASELINE.get(zone, 2.0)
                water_stress_scores[asset.id] = float(bws)
    ws_status.empty()

rows = []
for asset in assets:
    row = {"asset_id": asset.id, "name": asset.name, "lat": asset.lat, "lon": asset.lon,
           "value": asset.replacement_value, "asset_type": asset.asset_type,
           "year_built": asset.year_built, "material": asset.construction_material,
           "region": asset.region}
    row["total_ead"] = 0.0
    row["ead_pct"] = 0.0
    row["water_stress_score"] = water_stress_scores.get(asset.id, 0.0)
    for haz in ["flood", "wind", "wildfire", "heat", "coastal_flood"]:
        row[f"ead_{haz}"] = 0.0

    if not ead_totals.empty:
        m = ead_totals[ead_totals["asset_id"] == asset.id]
        if not m.empty:
            row["total_ead"] = float(m["total_ead"].iloc[0])
            row["ead_pct"] = row["total_ead"] / asset.replacement_value * 100 if asset.replacement_value > 0 else 0.0

    if not ead_by_asset_haz.empty and "asset_id" in ead_by_asset_haz.columns:
        m = ead_by_asset_haz[ead_by_asset_haz["asset_id"] == asset.id]
        if not m.empty:
            for haz in ["flood", "wind", "wildfire", "heat", "coastal_flood"]:
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

    # BSR palette gradient: teal (low) → BSR orange (mid) → danger red (high)
    BSR_GRADIENT = [
        (0.00, (42,  157, 143)),   # teal  #2A9D8F
        (0.40, (87,  204, 153)),   # green #57CC99
        (0.60, (233, 196, 106)),   # amber #E9C46A
        (0.80, (244, 114,  26)),   # BSR orange #F4721A
        (1.00, (201,  64,  64)),   # danger red #C94040
    ]

    def _lerp_colour(frac):
        frac = max(0.0, min(1.0, frac))
        for i in range(len(BSR_GRADIENT) - 1):
            t0, c0 = BSR_GRADIENT[i]
            t1, c1 = BSR_GRADIENT[i + 1]
            if t0 <= frac <= t1:
                alpha = (frac - t0) / (t1 - t0)
                r = int(c0[0] + alpha * (c1[0] - c0[0]))
                g = int(c0[1] + alpha * (c1[1] - c0[1]))
                b = int(c0[2] + alpha * (c1[2] - c0[2]))
                return f"#{r:02x}{g:02x}{b:02x}"
        return "#2A9D8F"

    def risk_colour(val):
        frac = min(val / max_val, 1.0)
        return _lerp_colour(frac)

    selected_asset_for_buildings = None

    for _, row in map_df.iterrows():
        val = row.get(colour_col, 0.0)
        color = risk_colour(val)
        radius = max(8, min(28, 8 + val / max_val * 20))

        bws_val = row.get("water_stress_score", 0.0)
        bws_cat = ""
        if show_water_stress and bws_val > 0:
            try:
                from engine.water_stress import get_water_stress_rating
                ws_info = get_water_stress_rating(bws_val)
                bws_cat = f" ({ws_info['category']})"
            except Exception:
                pass
        ws_row = (
            f"<b>Water Stress (raw BWS indicator):</b> {bws_val:.1f}/5{bws_cat}<br>"
            if show_water_stress else ""
        )

        # Cyclone basin info for popup
        tc_row = ""
        if show_cyclone_tracks:
            try:
                from engine.tropical_cyclone import get_cyclone_basin, CYCLONE_BASINS, cyclone_amplification_factor
                _tc_basin = get_cyclone_basin(row["lat"], row["lon"])
                if _tc_basin:
                    _tc_info = CYCLONE_BASINS[_tc_basin]
                    _tc_amp = cyclone_amplification_factor(row["lat"], row["lon"], _tc_basin)
                    tc_row = (
                        f"<b>Cyclone Basin:</b> {_tc_info['name']} ({_tc_basin})<br>"
                        f"<b>TC Season:</b> {_tc_info['season']}<br>"
                        f"<b>Wind Amplification:</b> {_tc_amp:.0%}<br>"
                    )
            except Exception:
                pass

        coastal_row = ""
        cf_ead = row.get('ead_coastal_flood', 0)
        if cf_ead > 0:
            coastal_row = f"<b>Coastal Flood EAD:</b> {_sym}{cf_ead:,.0f}<br>"

        popup_html = f"""
        <div style="font-family:sans-serif;font-size:13px;min-width:240px">
          <b style="font-size:14px;">{row['name']}</b><br>
          <hr style="margin:4px 0">
          <b>Type:</b> {row['asset_type']}<br>
          <b>Material:</b> {row.get('material','')}<br>
          <b>Year built:</b> {row.get('year_built','')}<br>
          <b>Region:</b> {row.get('region','')}<br>
          <b>Value:</b> {_sym}{row['value']:,.0f}<br>
          <hr style="margin:4px 0">
          <b>EALR:</b> {row.get('ead_pct',0):.3f}% of value/yr<br>
          <b>Total EAD ({map_year}):</b> {_sym}{row.get('total_ead',0):,.0f}<br>
          <b>Flood EAD:</b> {_sym}{row.get('ead_flood',0):,.0f}<br>
          <b>Wind EAD:</b> {_sym}{row.get('ead_wind',0):,.0f}<br>
          <b>Wildfire EAD:</b> {_sym}{row.get('ead_wildfire',0):,.0f}<br>
          <b>Heat EAD:</b> {_sym}{row.get('ead_heat',0):,.0f}<br>
          {coastal_row}
          {tc_row}
          {ws_row}
        </div>
        """
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=radius, color=color,
            fill=True, fill_color=color, fill_opacity=0.75,
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"📍 {row['name']} | EAD: {_sym}{row.get('total_ead',0):,.0f}",
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

    # ── Tropical cyclone track overlay ────────────────────────────────────
    asset_basins = set()
    if show_cyclone_tracks:
        try:
            from engine.tropical_cyclone import (
                get_cyclone_basin, get_all_tracks, CYCLONE_BASINS,
                classify_saffir_simpson, nearest_track_distance_km,
            )
            # Determine which basins have portfolio assets
            for asset in assets:
                b = get_cyclone_basin(asset.lat, asset.lon)
                if b:
                    asset_basins.add(b)

            if asset_basins:
                all_tracks = get_all_tracks()
                # Saffir-Simpson colour scale for track segments
                _SS_COLORS = {
                    "TD": "#87CEEB",    # light blue
                    "TS": "#00CED1",    # dark turquoise
                    "Cat 1": "#FFD700", # gold
                    "Cat 2": "#FFA500", # orange
                    "Cat 3": "#FF4500", # orange-red
                    "Cat 4": "#DC143C", # crimson
                    "Cat 5": "#8B0000", # dark red
                }
                tc_group = folium.FeatureGroup(name="Tropical Cyclone Tracks", show=True)

                for basin_code in asset_basins:
                    tracks = all_tracks.get(basin_code, [])
                    for track in tracks:
                        waypoints = track.get("waypoints", [])
                        if len(waypoints) < 2:
                            continue

                        # Check if track passes near any asset (within 500 km)
                        near_asset = False
                        for asset in assets:
                            if nearest_track_distance_km(asset.lat, asset.lon, track) < 500:
                                near_asset = True
                                break
                        if not near_asset:
                            continue

                        # Draw track segments coloured by intensity
                        for j in range(len(waypoints) - 1):
                            wp1 = waypoints[j]
                            wp2 = waypoints[j + 1]
                            cat = wp2.get("cat", "TS")
                            color = _SS_COLORS.get(cat, "#00CED1")
                            wind_kt = wp2.get("wind_kt", 0)

                            folium.PolyLine(
                                locations=[
                                    [wp1["lat"], wp1["lon"]],
                                    [wp2["lat"], wp2["lon"]],
                                ],
                                color=color, weight=3, opacity=0.8,
                                tooltip=(
                                    f"{track['name']} ({track['year']}) — "
                                    f"{cat} ({wind_kt} kt)"
                                ),
                            ).add_to(tc_group)

                        # Storm name label at peak intensity point
                        peak_wp = max(waypoints, key=lambda w: w.get("wind_kt", 0))
                        folium.Marker(
                            location=[peak_wp["lat"], peak_wp["lon"]],
                            icon=folium.DivIcon(
                                html=f'<div style="font-size:10px;color:#fff;background:rgba(0,0,0,0.6);'
                                     f'padding:1px 4px;border-radius:3px;white-space:nowrap;">'
                                     f'{track["name"]} ({track["year"]}) {track.get("category","")}</div>',
                                icon_size=(120, 20),
                                icon_anchor=(60, 10),
                            ),
                            tooltip=f"{track['name']} ({track['year']}) — Peak: {track.get('max_wind_kt',0)} kt",
                        ).add_to(tc_group)

                tc_group.add_to(m)
        except Exception:
            pass

    folium.LayerControl().add_to(m)

    st_folium(m, use_container_width=True, height=620)

    caption_parts = ["Satellite imagery: © Esri and contributors."]
    if show_buildings:
        caption_parts.append(
            "Building footprints: © [OpenStreetMap](https://www.openstreetmap.org/) contributors (ODbL) "
            "via [Overpass API](https://overpass-api.de/)."
        )
    if show_water_stress or colour_by == "Water Stress":
        caption_parts.append(
            "Water stress: [WRI Aqueduct 4.0](https://www.wri.org/data/aqueduct-water-risk-atlas) "
            "— Kuzma et al. (2023) https://doi.org/10.46830/writn.23.00061 (CC BY 4.0)."
        )
    if show_cyclone_tracks:
        caption_parts.append(
            "Cyclone tracks: [IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive) "
            "— Knapp et al. (2010). Colour = Saffir-Simpson category. "
            "Wind profile: Holland (1980)."
        )
    st.caption("  ".join(caption_parts))

    # Saffir-Simpson legend
    if show_cyclone_tracks and asset_basins:
        legend_items = [
            ("TD", "#87CEEB"), ("TS", "#00CED1"), ("Cat 1", "#FFD700"),
            ("Cat 2", "#FFA500"), ("Cat 3", "#FF4500"), ("Cat 4", "#DC143C"),
            ("Cat 5", "#8B0000"),
        ]
        legend_html = " ".join(
            f'<span style="display:inline-block;width:12px;height:12px;background:{c};'
            f'margin-right:2px;border-radius:2px;"></span>{label}&nbsp;&nbsp;'
            for label, c in legend_items
        )
        st.markdown(
            f'<div style="font-size:12px;margin-top:-8px;">Saffir-Simpson Scale: {legend_html}</div>',
            unsafe_allow_html=True,
        )

except ImportError:
    st.warning("folium / streamlit-folium not installed.")
    if not map_df.empty:
        st.map(map_df[["lat", "lon"]].rename(columns={"lat": "latitude", "lon": "longitude"}))

# ── Risk ranking table ─────────────────────────────────────────────────────
st.divider()
st.subheader("Asset Risk Ranking")
if not map_df.empty and "ead_pct" in map_df.columns:
    rank_cols = ["name", "asset_type", "region", "value", "total_ead", "ead_pct"]
    if show_water_stress and "water_stress_score" in map_df.columns:
        rank_cols.append("water_stress_score")
    rank_df = map_df[rank_cols].sort_values("ead_pct", ascending=False).reset_index(drop=True)
    rank_df.index += 1
    _cur_map = st.session_state.get("currency_code", "GBP")
    _sym_map = _currency_symbol(_cur_map)
    col_names = ["Asset", "Type", "Region", f"Value ({_sym_map})", f"EAD ({_sym_map})", "EALR (%)"]
    if show_water_stress and "water_stress_score" in map_df.columns:
        col_names.append("Water Stress (BWS 0–5)")
    rank_df.columns = col_names
    rank_df[f"Value ({_sym_map})"] = rank_df[f"Value ({_sym_map})"].apply(lambda x: _fmt_cur(x, _cur_map))
    rank_df[f"EAD ({_sym_map})"] = rank_df[f"EAD ({_sym_map})"].apply(lambda x: _fmt_cur(x, _cur_map))
    rank_df["EALR (%)"] = rank_df["EALR (%)"].apply(lambda x: f"{x:.3f}%")
    if "Water Stress (BWS 0–5)" in rank_df.columns:
        rank_df["Water Stress (BWS 0–5)"] = rank_df["Water Stress (BWS 0–5)"].apply(lambda x: f"{x:.1f}")
    st.dataframe(rank_df, use_container_width=True, hide_index=False)
    st.caption(
        "**EALR (%)** = Expected Annual Loss Ratio (EAD as % of replacement value). "
        "**Water Stress (raw BWS indicator, not modelled loss)**: 0–1 Low · 1–2 Low-Medium · 2–3 Medium-High · 3–4 High · 4–5 Extremely High. "
        "Source: [WRI Aqueduct 4.0](https://doi.org/10.46830/writn.23.00061)"
    )
