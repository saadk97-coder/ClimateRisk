"""
Page 1 – Portfolio: Asset definition, CSV upload, auto-detect location & elevation,
and map preview.
"""

import streamlit as st
import pandas as pd
import numpy as np
import io
import uuid
import json
import requests

from engine.asset_model import Asset, load_asset_types
from engine.fmt import fmt as _fmt, CURRENCIES
from engine.insights import portfolio_health_check, render_insights_html

# ── ISO 3166-1 alpha-2 → alpha-3 mapping ─────────────────────────────────────
ISO2_TO_ISO3: dict[str, str] = {
    "AF": "AFG", "AL": "ALB", "DZ": "DZA", "AR": "ARG", "AU": "AUS",
    "AT": "AUT", "AZ": "AZE", "BD": "BGD", "BE": "BEL", "BR": "BRA",
    "BG": "BGR", "CA": "CAN", "CL": "CHL", "CN": "CHN", "CO": "COL",
    "HR": "HRV", "CZ": "CZE", "DK": "DNK", "EG": "EGY", "EE": "EST",
    "FI": "FIN", "FR": "FRA", "DE": "DEU", "GH": "GHA", "GR": "GRC",
    "HK": "HKG", "HU": "HUN", "IN": "IND", "ID": "IDN", "IR": "IRN",
    "IQ": "IRQ", "IE": "IRL", "IL": "ISR", "IT": "ITA", "JP": "JPN",
    "KE": "KEN", "KR": "KOR", "KW": "KWT", "LV": "LVA", "LT": "LTU",
    "LU": "LUX", "MY": "MYS", "MA": "MAR", "MX": "MEX", "NL": "NLD",
    "NZ": "NZL", "NG": "NGA", "NO": "NOR", "PK": "PAK", "PE": "PER",
    "PH": "PHL", "PL": "POL", "PT": "PRT", "QA": "QAT", "RO": "ROU",
    "RU": "RUS", "SA": "SAU", "SG": "SGP", "SK": "SVK", "ZA": "ZAF",
    "ES": "ESP", "SE": "SWE", "CH": "CHE", "TW": "TWN", "TH": "THA",
    "TR": "TUR", "UA": "UKR", "AE": "ARE", "GB": "GBR", "US": "USA",
    "VN": "VNM", "KZ": "KAZ", "BO": "BOL", "EC": "ECU",
}

ISO3_COUNTRIES: dict[str, str] = {
    "GBR": "United Kingdom",  "USA": "United States",    "FRA": "France",
    "DEU": "Germany",          "NLD": "Netherlands",      "BEL": "Belgium",
    "CHE": "Switzerland",      "AUT": "Austria",          "ESP": "Spain",
    "ITA": "Italy",            "PRT": "Portugal",         "SWE": "Sweden",
    "NOR": "Norway",           "DNK": "Denmark",          "FIN": "Finland",
    "IRL": "Ireland",          "POL": "Poland",           "CZE": "Czech Republic",
    "HUN": "Hungary",          "ROU": "Romania",          "GRC": "Greece",
    "HRV": "Croatia",          "SVK": "Slovakia",         "BGR": "Bulgaria",
    "LVA": "Latvia",           "LTU": "Lithuania",        "LUX": "Luxembourg",
    "EST": "Estonia",          "TUR": "Turkey",           "RUS": "Russia",
    "UKR": "Ukraine",          "CAN": "Canada",           "USA": "United States",
    "MEX": "Mexico",           "BRA": "Brazil",           "ARG": "Argentina",
    "CHL": "Chile",            "COL": "Colombia",         "PER": "Peru",
    "BOL": "Bolivia",          "ECU": "Ecuador",          "CHN": "China",
    "JPN": "Japan",            "KOR": "South Korea",      "IND": "India",
    "IDN": "Indonesia",        "MYS": "Malaysia",         "SGP": "Singapore",
    "THA": "Thailand",         "VNM": "Vietnam",          "BGD": "Bangladesh",
    "PAK": "Pakistan",         "PHL": "Philippines",      "TWN": "Taiwan",
    "KAZ": "Kazakhstan",       "AUS": "Australia",        "NZL": "New Zealand",
    "ZAF": "South Africa",     "NGA": "Nigeria",          "EGY": "Egypt",
    "KEN": "Kenya",            "MAR": "Morocco",          "GHA": "Ghana",
    "DZA": "Algeria",          "SAU": "Saudi Arabia",     "ARE": "United Arab Emirates",
    "QAT": "Qatar",            "KWT": "Kuwait",           "IRN": "Iran",
    "IRQ": "Iraq",             "ISR": "Israel",           "HKG": "Hong Kong",
    "TWN": "Taiwan",
}

st.set_page_config(page_title="Portfolio", page_icon="🏗️", layout="wide")

# ── Session state defaults ───────────────────────────────────────────────────
if "assets" not in st.session_state:
    st.session_state.assets = []
if "geo_lat" not in st.session_state:
    st.session_state.geo_lat = 40.7128
if "geo_lon" not in st.session_state:
    st.session_state.geo_lon = -74.0060
if "geo_country" not in st.session_state:
    st.session_state.geo_country = "USA"
if "geo_elevation" not in st.session_state:
    st.session_state.geo_elevation = 0.0
if "form_asset_type" not in st.session_state:
    st.session_state.form_asset_type = "residential_masonry"

asset_types = load_asset_types()
_cur = st.session_state.get("currency_code", "USD")
_sym = CURRENCIES.get(_cur, CURRENCIES["USD"])["symbol"]


# ── Helpers ──────────────────────────────────────────────────────────────────
def assets_to_df(assets):
    if not assets:
        return pd.DataFrame()
    return pd.DataFrame([a.to_dict() for a in assets])


def df_to_assets(df):
    return [Asset.from_dict(row) for _, row in df.iterrows()]


def _detect_location(lat: float, lon: float):
    """
    Call free APIs to get:
      - ISO3 country code (BigDataCloud reverse geocode, no API key required)
      - Elevation in metres (OpenTopoData ASTER 30m DEM, no API key required)
    Returns (iso3: str, elevation_m: float, status_msg: str)
    """
    iso3 = "USA"
    elev = 0.0
    msgs = []

    # 1. Country via BigDataCloud
    try:
        r = requests.get(
            "https://api.bigdatacloud.net/data/reverse-geocode-client",
            params={"latitude": lat, "longitude": lon, "localityLanguage": "en"},
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json()
            iso2 = data.get("countryCode", "")
            iso3 = ISO2_TO_ISO3.get(iso2.upper(), iso3)
            msgs.append(f"Country: {iso3} ({data.get('countryName', '')})")
    except Exception as e:
        msgs.append(f"Country lookup failed: {e}")

    # 2. Elevation via OpenTopoData (ASTER 30m)
    try:
        r2 = requests.get(
            "https://api.opentopodata.org/v1/aster30m",
            params={"locations": f"{lat},{lon}"},
            timeout=10,
        )
        if r2.status_code == 200:
            results = r2.json().get("results", [])
            if results:
                elev = float(results[0].get("elevation", 0.0) or 0.0)
                msgs.append(f"Elevation: {elev:.1f} m ASL")
    except Exception as e:
        msgs.append(f"Elevation lookup failed: {e}")

    return iso3, elev, " · ".join(msgs)


def _on_asset_type_change():
    """Update form defaults when asset type changes."""
    at = st.session_state.get("_form_at_key", "residential_masonry")
    defaults = asset_types.get(at, {})
    st.session_state["form_asset_type"]   = at
    st.session_state["_auto_material"]    = defaults.get("default_material", "masonry")
    st.session_state["_auto_stories"]     = defaults.get("default_stories", 2)
    st.session_state["_auto_roof"]        = defaults.get("default_roof", "gable")
    st.session_state["_auto_floor_area"]  = float(defaults.get("default_floor_area_m2", 150))


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.assets)
    total_val = sum(a.replacement_value for a in st.session_state.assets)
    st.metric("Assets", n)
    st.metric("Total Value", _fmt(total_val, _cur))
    if "last_run" in st.session_state:
        st.caption(f"Last run: {st.session_state.last_run}")

# ── Main ─────────────────────────────────────────────────────────────────────
st.title("Portfolio Definition")
st.markdown("Define your asset portfolio by uploading a CSV or adding assets manually.")

tab_upload, tab_manual, tab_view = st.tabs(["📤 Upload CSV", "✏️ Add Manually", "📋 View Portfolio"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: CSV Upload
# ══════════════════════════════════════════════════════════════════════════════
with tab_upload:
    # ── Sample portfolio download — top of tab ────────────────────────────────
    _sample_csv = (
        "id,name,lat,lon,asset_type,replacement_value,construction_material,year_built,stories,basement,roof_type,first_floor_height_m,terrain_elevation_asl_m,floor_area_m2,region\n"
        "SAM001,Manhattan Financial Tower,40.7074,-74.0113,commercial_office,125000000,steel,2001,42,True,flat,1.2,10,32000,USA\n"
        "SAM002,Miami Oceanfront Resort,25.7617,-80.1918,hotel_resort,48000000,concrete,1998,12,False,flat,0.6,2,9500,USA\n"
        "SAM003,Houston Petrochemical Plant,29.7604,-95.3698,industrial_heavy,185000000,concrete,1982,4,False,flat,1.5,15,28000,USA\n"
        "SAM004,Los Angeles Office Campus,34.0522,-118.2437,commercial_office,62000000,steel,2005,8,False,flat,0.3,90,18000,USA\n"
        "SAM005,San Francisco Bay Area Data Centre,37.7749,-122.4194,data_center,95000000,concrete,2015,3,False,flat,0.6,16,6000,USA\n"
        "SAM006,Amsterdam Polder Logistics Hub,52.3676,4.9041,commercial_warehouse,22000000,steel,2008,1,False,flat,0.0,-2,35000,NLD\n"
        "SAM007,Rotterdam Port Terminal,51.9244,4.4777,infrastructure_port,75000000,concrete,1995,1,False,flat,0.0,0,0,NLD\n"
        "SAM008,London Canary Wharf Tower,51.5055,-0.0250,commercial_office,210000000,concrete,2002,50,True,flat,1.0,6,42000,GBR\n"
        "SAM009,Thames Valley Residential Block,51.4607,-0.9238,residential_masonry,8500000,masonry,1968,5,False,flat,0.3,45,3200,GBR\n"
        "SAM010,Paris La Defense Commercial Tower,48.8917,2.2360,commercial_concrete,145000000,concrete,2010,35,True,flat,0.8,62,30000,FRA\n"
        "SAM011,Rhine Valley Industrial Factory,51.3397,6.8750,industrial_steel,31000000,steel,1990,2,False,flat,0.5,30,22000,DEU\n"
        "SAM012,Singapore Marina Bay Office,1.2839,103.8607,commercial_office,88000000,steel,2012,38,True,flat,1.5,5,25000,SGP\n"
        "SAM013,Mumbai Coastal Mixed-Use Tower,19.0760,72.8777,mixed_use,35000000,concrete,2008,25,True,flat,0.5,8,18000,IND\n"
        "SAM014,Tokyo Shinjuku Office Block,35.6895,139.6917,commercial_office,92000000,concrete,2003,20,True,flat,0.8,38,16000,JPN\n"
        "SAM015,Dubai Internet City Data Centre,25.0942,55.1533,data_center,120000000,concrete,2018,4,False,flat,1.0,12,8000,ARE\n"
        "SAM016,Sydney Bush Interface Residential,33.7295,151.2862,residential_wood,1850000,wood_frame,1975,2,False,gable,0.3,85,180,AUS\n"
        "SAM017,Melbourne CBD Commercial Tower,-37.8136,144.9631,commercial_concrete,67000000,concrete,1999,22,True,flat,0.5,25,18000,AUS\n"
        "SAM018,Sao Paulo Industrial Complex,-23.5505,-46.6333,industrial_steel,28000000,steel,1985,2,False,flat,0.3,760,20000,BRA\n"
        "SAM019,Jakarta Flood Pumping Station,-6.2088,106.8456,infrastructure_utility,18000000,steel,2005,1,False,flat,0.0,5,400,IDN\n"
        "SAM020,Cape Town Mixed-Use Development,-33.9249,18.4241,mixed_use,42000000,concrete,2016,8,False,flat,0.5,15,12000,ZAF\n"
    )
    st.download_button(
        "🌍 Download Sample Portfolio (20 global assets)",
        data=_sample_csv.encode(),
        file_name="sample_portfolio.csv",
        mime="text/csv",
        type="primary",
    )
    st.caption("20 assets across 13 countries — USA, GBR, NLD, FRA, DEU, SGP, IND, JPN, ARE, AUS, BRA, IDN, ZAF. Upload it below to get started.")
    st.divider()

    st.subheader("CSV Template")

    template_df = pd.DataFrame([{
        "id": "ASSET001",
        "name": "Manhattan Office Tower",
        "lat": 40.7128, "lon": -74.0060,
        "asset_type": "commercial_office",
        "replacement_value": 50_000_000,
        "construction_material": "steel",
        "year_built": 2005,
        "stories": 20,
        "basement": False,
        "roof_type": "flat",
        "first_floor_height_m": 0.3,
        "terrain_elevation_asl_m": 10,
        "floor_area_m2": 15000,
        "region": "USA",
    }, {
        "id": "ASSET002",
        "name": "Chicago Logistics Hub",
        "lat": 41.8781, "lon": -87.6298,
        "asset_type": "commercial_warehouse",
        "replacement_value": 8_500_000,
        "construction_material": "steel",
        "year_built": 2010,
        "stories": 1,
        "basement": False,
        "roof_type": "flat",
        "first_floor_height_m": 0.0,
        "terrain_elevation_asl_m": 181,
        "floor_area_m2": 25000,
        "region": "USA",
    }, {
        "id": "ASSET003",
        "name": "London Data Centre",
        "lat": 51.5074, "lon": -0.1278,
        "asset_type": "data_center",
        "replacement_value": 30_000_000,
        "construction_material": "concrete",
        "year_built": 2018,
        "stories": 3,
        "basement": True,
        "roof_type": "flat",
        "first_floor_height_m": 0.5,
        "terrain_elevation_asl_m": 11,
        "floor_area_m2": 5000,
        "region": "GBR",
    }])

    with st.expander("📋 Asset type reference", expanded=False):
        ref_rows = []
        for key, val in asset_types.items():
            ref_rows.append({
                "Type Key": key,
                "Label": val["label"],
                "Default Material": val["default_material"],
                "Default Stories": val["default_stories"],
                "Hazards Covered": ", ".join(val.get("hazards", [])),
                "HAZUS Class": val.get("hazus_class", "—"),
                "Description": val["description"],
            })
        st.dataframe(pd.DataFrame(ref_rows), use_container_width=True, hide_index=True)

    st.divider()
    uploaded = st.file_uploader("Upload your portfolio CSV", type=["csv"])
    if uploaded:
        try:
            df = pd.read_csv(uploaded)
            st.dataframe(df.head(), use_container_width=True)
            new_assets = df_to_assets(df)
            if st.button("✅ Import Assets", type="primary"):
                st.session_state.assets = new_assets
                st.success(f"Imported {len(new_assets)} assets.")
                st.rerun()
        except Exception as e:
            st.error(f"Error reading CSV: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: Manual Add
# ══════════════════════════════════════════════════════════════════════════════
with tab_manual:
    st.subheader("Add an Asset")

    # ── Step 1: Location ─────────────────────────────────────────────────────
    st.markdown("#### 📍 Step 1 — Location")
    st.caption(
        "Enter coordinates, then click **Auto-detect** to look up the country and "
        "terrain elevation automatically (uses OpenStreetMap reverse geocoding + ASTER DEM, free)."
    )

    c1, c2 = st.columns(2)
    with c1:
        form_lat = st.number_input(
            "Latitude", value=st.session_state.geo_lat,
            min_value=-90.0, max_value=90.0, format="%.6f",
            key="input_lat",
        )
    with c2:
        form_lon = st.number_input(
            "Longitude", value=st.session_state.geo_lon,
            min_value=-180.0, max_value=180.0, format="%.6f",
            key="input_lon",
        )

    detect_col, status_col = st.columns([1, 4])
    with detect_col:
        detect_btn = st.button("📍 Auto-detect Country & Elevation", type="secondary")
    with status_col:
        detect_status = st.empty()

    if detect_btn:
        with st.spinner("Querying reverse geocode & elevation APIs…"):
            iso3, elev, msg = _detect_location(form_lat, form_lon)
            st.session_state.geo_lat       = form_lat
            st.session_state.geo_lon       = form_lon
            st.session_state.geo_country   = iso3
            st.session_state.geo_elevation = elev
        detect_status.success(f"✅ {msg}")
    else:
        # Keep lat/lon in sync even without auto-detect
        st.session_state.geo_lat = form_lat
        st.session_state.geo_lon = form_lon

    st.divider()

    # ── Step 2: Asset Type → auto-fills material defaults ───────────────────
    st.markdown("#### 🏗️ Step 2 — Asset Type")
    st.caption("Selecting a type pre-fills construction material, stories, and roof type with evidence-based defaults.")

    at_options = list(asset_types.keys())
    at_default_idx = at_options.index(st.session_state.form_asset_type) if st.session_state.form_asset_type in at_options else 0

    chosen_asset_type = st.selectbox(
        "Asset Type",
        at_options,
        index=at_default_idx,
        format_func=lambda k: asset_types[k]["label"],
        key="_form_at_key",
        on_change=_on_asset_type_change,
        help="Select the asset category. Construction material, stories, and roof type will be set automatically.",
    )
    at_info = asset_types.get(chosen_asset_type, {})

    # Show description and hazards for chosen type
    desc_col, haz_col = st.columns([3, 2])
    with desc_col:
        st.caption(f"📖 {at_info.get('description', '')}")
    with haz_col:
        hazard_labels = {
            "flood": "🌊 Flood", "wind": "🌬️ Wind",
            "wildfire": "🔥 Wildfire", "heat": "☀️ Heat", "water_stress": "💧 Water Stress",
        }
        haz_badges = " ".join(hazard_labels.get(h, h) for h in at_info.get("hazards", []))
        st.caption(f"Hazards: {haz_badges}")

    st.divider()

    # ── Step 3: Form ─────────────────────────────────────────────────────────
    st.markdown("#### ✏️ Step 3 — Asset Details")

    # Resolve current defaults (either from on_change callback or asset type directly)
    _def_mat      = st.session_state.get("_auto_material",   at_info.get("default_material", "masonry"))
    _def_stories  = st.session_state.get("_auto_stories",    at_info.get("default_stories", 2))
    _def_roof     = st.session_state.get("_auto_roof",       at_info.get("default_roof", "gable"))
    _def_area     = float(st.session_state.get("_auto_floor_area", at_info.get("default_floor_area_m2", 150)))
    _def_country  = st.session_state.get("geo_country", "USA")
    _def_elev     = st.session_state.get("geo_elevation", 0.0)

    with st.form("add_asset_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("Asset Name", placeholder="e.g. Chicago Distribution Centre")
            replacement_value = st.number_input(
                f"Replacement Value ({_sym})", min_value=1_000, value=5_000_000, step=50_000,
            )
            year_built = st.number_input("Year Built", min_value=1800, max_value=2025, value=2005)
            floor_area = st.number_input("Floor Area (m²)", min_value=0, value=int(_def_area), step=100)

        with col2:
            # Country — pre-filled from auto-detect
            country_options = list(ISO3_COUNTRIES.keys())
            country_idx = country_options.index(_def_country) if _def_country in country_options else 0
            region = st.selectbox(
                "Country (ISO3)",
                country_options,
                index=country_idx,
                format_func=lambda k: f"{k} — {ISO3_COUNTRIES.get(k, k)}",
                help="Pre-filled from Auto-detect. Override if needed.",
            )
            # First-floor height above ground (freeboard)
            elevation_m = st.number_input(
                "First-floor height above ground (m)",
                value=0.0,
                min_value=0.0,
                step=0.1,
                format="%.1f",
                help=(
                    "Height of the lowest occupied floor above local ground level (freeboard). "
                    "NOT the site's ASL elevation. Enter 0 for slab-on-grade buildings. "
                    "The engine computes flood exposure as (flood_depth − first_floor_height)."
                ),
            )
            basement = st.checkbox("Has Basement", help="Basements significantly increase flood damage exposure.")

        st.markdown("**Construction**")
        c3, c4, c5 = st.columns(3)
        with c3:
            mat_options = ["wood_frame", "masonry", "steel", "concrete", "mixed"]
            mat_idx = mat_options.index(_def_mat) if _def_mat in mat_options else 1
            material = st.selectbox(
                "Construction Material",
                mat_options,
                index=mat_idx,
                help="Pre-filled from asset type default. Affects which vulnerability curve is applied.",
            )
        with c4:
            stories = st.number_input(
                "Number of Stories", min_value=1, max_value=200, value=int(_def_stories),
            )
        with c5:
            roof_options = ["flat", "gable", "hip"]
            roof_idx = roof_options.index(_def_roof) if _def_roof in roof_options else 0
            roof_type = st.selectbox(
                "Roof Type", roof_options, index=roof_idx,
                help="Flat roofs have higher wind uplift loading; gable and hip shed wind more effectively.",
            )

        submitted = st.form_submit_button("➕ Add Asset", type="primary", use_container_width=True)
        if submitted:
            if not name:
                st.error("Asset name is required.")
            else:
                new_asset = Asset(
                    id=str(uuid.uuid4())[:8].upper(),
                    name=name,
                    lat=st.session_state.geo_lat,
                    lon=st.session_state.geo_lon,
                    asset_type=chosen_asset_type,
                    replacement_value=replacement_value,
                    construction_material=material,
                    year_built=year_built,
                    stories=stories,
                    basement=basement,
                    roof_type=roof_type,
                    first_floor_height_m=elevation_m,
                    terrain_elevation_asl_m=_def_elev,
                    floor_area_m2=float(floor_area),
                    region=region,
                )
                st.session_state.assets.append(new_asset)
                st.success(f"✅ Added: **{name}** ({at_info['label']}, {region})")
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: View / Edit / Delete
# ══════════════════════════════════════════════════════════════════════════════
with tab_view:
    if not st.session_state.assets:
        st.info("No assets defined yet. Upload a CSV or add assets manually.")
    else:
        st.subheader(f"Portfolio — {len(st.session_state.assets)} assets")
        df = assets_to_df(st.session_state.assets)

        # Add a human-readable type label column
        df["type_label"] = df["asset_type"].map(lambda k: asset_types.get(k, {}).get("label", k))

        ffh_col = "first_floor_height_m" if "first_floor_height_m" in df.columns else "elevation_m"
        disp = df[["id", "name", "type_label", "replacement_value", "region", "lat", "lon", ffh_col]].copy()
        disp = disp.rename(columns={
            "id": "ID", "name": "Name", "type_label": "Type",
            "replacement_value": f"Value ({_sym})", "region": "Country",
            "lat": "Lat", "lon": "Lon", ffh_col: "FFH (m)",
        })
        disp[f"Value ({_sym})"] = disp[f"Value ({_sym})"].apply(lambda x: _fmt(x, _cur))

        st.dataframe(disp, use_container_width=True, hide_index=True)

        # Metrics strip
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Portfolio Value", _fmt(total_val := sum(a.replacement_value for a in st.session_state.assets), _cur))
        m2.metric("Asset Types", len({a.asset_type for a in st.session_state.assets}))
        m3.metric("Countries", len({a.region for a in st.session_state.assets}))

        # ── Portfolio Health Check Insights ──────────────────────────────────
        _insights = portfolio_health_check(st.session_state.assets)
        if _insights:
            st.divider()
            st.subheader("Portfolio Health Check")
            st.caption(
                "Structural observations based on asset attributes — before running damage calculations. "
                "These flags highlight concentration, vulnerability, and code-compliance concerns."
            )
            st.markdown(render_insights_html(_insights), unsafe_allow_html=True)

        # Map preview
        if len(df) > 0:
            st.subheader("Asset Locations")
            map_df = df[["lat", "lon"]].rename(columns={"lat": "latitude", "lon": "longitude"})
            st.map(map_df, zoom=3)

        # Delete
        st.divider()
        col_del1, col_del2 = st.columns([3, 1])
        with col_del1:
            del_id = st.selectbox(
                "Select asset to delete",
                options=[a.id for a in st.session_state.assets],
                format_func=lambda i: next(
                    (f"{a.name} ({asset_types.get(a.asset_type, {}).get('label', a.asset_type)})"
                     for a in st.session_state.assets if a.id == i), i
                ),
            )
        with col_del2:
            st.markdown("&nbsp;", unsafe_allow_html=True)
            if st.button("🗑️ Delete", type="secondary", use_container_width=True):
                st.session_state.assets = [a for a in st.session_state.assets if a.id != del_id]
                st.success("Asset deleted.")
                st.rerun()

        if st.button("🗑️ Clear All Assets", type="secondary"):
            st.session_state.assets = []
            st.rerun()
