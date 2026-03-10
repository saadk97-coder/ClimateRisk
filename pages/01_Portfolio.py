"""
Page 1 – Portfolio: Asset definition, CSV upload, and map preview.
"""

import streamlit as st
import pandas as pd
import numpy as np
import io
import uuid
import json

from engine.asset_model import Asset, load_asset_types
from engine.fmt import fmt as _fmt, CURRENCIES

ISO3_COUNTRIES = {
    "GBR": "United Kingdom",
    "USA": "United States",
    "FRA": "France",
    "DEU": "Germany",
    "NLD": "Netherlands",
    "BEL": "Belgium",
    "CHE": "Switzerland",
    "AUT": "Austria",
    "ESP": "Spain",
    "ITA": "Italy",
    "PRT": "Portugal",
    "SWE": "Sweden",
    "NOR": "Norway",
    "DNK": "Denmark",
    "FIN": "Finland",
    "IRL": "Ireland",
    "POL": "Poland",
    "CZE": "Czech Republic",
    "HUN": "Hungary",
    "ROU": "Romania",
    "GRC": "Greece",
    "TUR": "Turkey",
    "CAN": "Canada",
    "MEX": "Mexico",
    "BRA": "Brazil",
    "ARG": "Argentina",
    "CHL": "Chile",
    "COL": "Colombia",
    "PER": "Peru",
    "CHN": "China",
    "JPN": "Japan",
    "KOR": "South Korea",
    "IND": "India",
    "IDN": "Indonesia",
    "MYS": "Malaysia",
    "SGP": "Singapore",
    "THA": "Thailand",
    "VNM": "Vietnam",
    "BGD": "Bangladesh",
    "PAK": "Pakistan",
    "AUS": "Australia",
    "NZL": "New Zealand",
    "ZAF": "South Africa",
    "NGA": "Nigeria",
    "EGY": "Egypt",
    "KEN": "Kenya",
    "MAR": "Morocco",
    "SAU": "Saudi Arabia",
    "ARE": "United Arab Emirates",
    "QAT": "Qatar",
    "KWT": "Kuwait",
    "ISR": "Israel",
    "RUS": "Russia",
    "UKR": "Ukraine",
}

st.set_page_config(page_title="Portfolio", page_icon="🏗️", layout="wide")

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "assets" not in st.session_state:
    st.session_state.assets = []

asset_types = load_asset_types()


def assets_to_df(assets):
    if not assets:
        return pd.DataFrame()
    return pd.DataFrame([a.to_dict() for a in assets])


def df_to_assets(df):
    return [Asset.from_dict(row) for _, row in df.iterrows()]


# ---------------------------------------------------------------------------
# Sidebar summary
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.assets)
    total_val = sum(a.replacement_value for a in st.session_state.assets)
    st.metric("Assets", n)
    _cur = st.session_state.get("currency_code", "GBP")
    st.metric("Total Value", _fmt(total_val, _cur))
    if "last_run" in st.session_state:
        st.caption(f"Last run: {st.session_state.last_run}")

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
st.title("Portfolio Definition")
st.markdown("Define your asset portfolio by uploading a CSV or adding assets manually.")

tab_upload, tab_manual, tab_view = st.tabs(["📤 Upload CSV", "✏️ Add Manually", "📋 View Portfolio"])

# ── Tab 1: CSV Upload ──────────────────────────────────────────────────────
with tab_upload:
    st.subheader("CSV Template")

    template_df = pd.DataFrame([{
        "id": "ASSET001",
        "name": "Example Office Building",
        "lat": 51.5074,
        "lon": -0.1278,
        "asset_type": "commercial_steel",
        "replacement_value": 5000000,
        "construction_material": "steel",
        "year_built": 2005,
        "stories": 8,
        "basement": False,
        "roof_type": "flat",
        "elevation_m": 0.0,
        "floor_area_m2": 4000,
        "region": "GBR",
    }, {
        "id": "ASSET002",
        "name": "Residential House",
        "lat": 51.4500,
        "lon": -0.3200,
        "asset_type": "residential_masonry",
        "replacement_value": 450000,
        "construction_material": "masonry",
        "year_built": 1985,
        "stories": 2,
        "basement": False,
        "roof_type": "gable",
        "elevation_m": 0.5,
        "floor_area_m2": 120,
        "region": "GBR",
    }])

    csv_bytes = template_df.to_csv(index=False).encode()
    st.download_button(
        "⬇️ Download CSV Template",
        data=csv_bytes,
        file_name="portfolio_template.csv",
        mime="text/csv",
    )

    st.divider()
    uploaded = st.file_uploader("Upload your portfolio CSV", type=["csv"])
    if uploaded:
        try:
            df = pd.read_csv(uploaded)
            new_assets = df_to_assets(df)
            if st.button("✅ Import Assets", type="primary"):
                st.session_state.assets = new_assets
                st.success(f"Imported {len(new_assets)} assets.")
                st.rerun()
        except Exception as e:
            st.error(f"Error reading CSV: {e}")

# ── Tab 2: Manual Add ─────────────────────────────────────────────────────
with tab_manual:
    st.subheader("Add a Single Asset")
    with st.form("add_asset_form"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Asset Name", placeholder="e.g. HQ Office Block")
            asset_type = st.selectbox(
                "Asset Type",
                options=list(asset_types.keys()),
                format_func=lambda k: asset_types[k]["label"],
            )
            _cur = st.session_state.get("currency_code", "GBP")
            _sym = CURRENCIES.get(_cur, CURRENCIES["GBP"])["symbol"]
            replacement_value = st.number_input(
                f"Replacement Value ({_sym})", min_value=1000, value=1_000_000, step=10_000
            )
            region = st.selectbox(
                "Country (ISO3)",
                list(ISO3_COUNTRIES.keys()),
                index=0,
                format_func=lambda k: f"{k} — {ISO3_COUNTRIES[k]}",
                help="Select the country where this asset is located (ISO 3166-1 alpha-3 code).",
            )
        with col2:
            lat = st.number_input("Latitude", value=51.5074, format="%.6f")
            lon = st.number_input("Longitude", value=-0.1278, format="%.6f")
            year_built = st.number_input("Year Built", min_value=1800, max_value=2025, value=2000)
            elevation_m = st.number_input("Elevation above flood plain (m)", value=0.0, step=0.1)

        col3, col4 = st.columns(2)
        with col3:
            material = st.selectbox(
                "Construction Material",
                ["wood_frame", "masonry", "steel", "concrete", "mixed"],
                index=1,
            )
            stories = st.number_input("Number of Stories", min_value=1, value=2)
        with col4:
            roof_type = st.selectbox("Roof Type", ["flat", "gable", "hip"])
            basement = st.checkbox("Has Basement")
            floor_area = st.number_input("Floor Area (m²)", min_value=1, value=200)

        submitted = st.form_submit_button("➕ Add Asset", type="primary")
        if submitted:
            if not name:
                st.error("Asset name is required.")
            else:
                new_asset = Asset(
                    id=str(uuid.uuid4())[:8].upper(),
                    name=name,
                    lat=lat,
                    lon=lon,
                    asset_type=asset_type,
                    replacement_value=replacement_value,
                    construction_material=material,
                    year_built=year_built,
                    stories=stories,
                    basement=basement,
                    roof_type=roof_type,
                    elevation_m=elevation_m,
                    floor_area_m2=floor_area,
                    region=region,
                )
                st.session_state.assets.append(new_asset)
                st.success(f"Added: {name}")
                st.rerun()

# ── Tab 3: View / Edit / Delete ───────────────────────────────────────────
with tab_view:
    if not st.session_state.assets:
        st.info("No assets defined yet. Upload a CSV or add assets manually.")
    else:
        st.subheader(f"Portfolio ({len(st.session_state.assets)} assets)")
        df = assets_to_df(st.session_state.assets)

        _cur = st.session_state.get("currency_code", "GBP")
        _sym = CURRENCIES.get(_cur, CURRENCIES["GBP"])["symbol"]
        st.dataframe(
            df[["id", "name", "asset_type", "replacement_value", "lat", "lon", "region"]].rename(
                columns={
                    "id": "ID", "name": "Name", "asset_type": "Type",
                    "replacement_value": f"Value ({_sym})", "lat": "Lat", "lon": "Lon",
                    "region": "Region",
                }
            ),
            use_container_width=True,
        )

        # Map preview
        if len(df) > 0:
            st.subheader("Asset Locations")
            map_df = df[["lat", "lon"]].rename(columns={"lat": "latitude", "lon": "longitude"})
            st.map(map_df, zoom=5)

        # Delete
        st.divider()
        del_id = st.selectbox(
            "Select asset to delete",
            options=[a.id for a in st.session_state.assets],
            format_func=lambda i: next((a.name for a in st.session_state.assets if a.id == i), i),
        )
        if st.button("🗑️ Delete Selected Asset", type="secondary"):
            st.session_state.assets = [a for a in st.session_state.assets if a.id != del_id]
            st.success("Asset deleted.")
            st.rerun()

        if st.button("🗑️ Clear All Assets", type="secondary"):
            st.session_state.assets = []
            st.rerun()
