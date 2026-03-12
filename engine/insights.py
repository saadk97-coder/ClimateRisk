"""
Portfolio insight engine — generates human-readable risk observations.

Two entry points:
  portfolio_health_check(assets)          → pre-calculation structural observations
  results_hotspots(annual_df, assets, scenario_id, year) → post-calc risk findings

Each function returns a list of dicts:
  { "level": "info"|"warning"|"error", "icon": str, "title": str, "body": str }
"""

from __future__ import annotations
from typing import TYPE_CHECKING
import pandas as pd

if TYPE_CHECKING:
    from engine.asset_model import Asset


# ── Thresholds ──────────────────────────────────────────────────────────────
_LOW_ELEVATION_M    = 3.0    # assets at or below this flag flood exposure
_VERY_LOW_ELEV_M   = 0.0    # below sea level
_OLD_STOCK_YEAR     = 1980   # assets built before this are pre-modern codes
_CONCENTRATION_PCT  = 0.5    # single asset > 50% portfolio value → concentration risk
_COUNTRY_CONC_PCT   = 0.7    # single country > 70% portfolio value
_HIGH_EAD_PCT       = 0.02   # asset EAD > 2% of replacement value → high risk
_ESCALATION_PCT     = 0.5    # EAD grows >50% between reference year and target year

_WILDFIRE_TYPES = {"residential_wood", "agricultural", "infrastructure_road",
                   "commercial_warehouse", "industrial_steel"}
_HEAT_SENSITIVE  = {"data_center", "healthcare_hospital", "industrial_heavy",
                    "commercial_office", "mixed_use"}
_FLOOD_CRITICAL  = {"infrastructure_utility", "infrastructure_port",
                    "data_center", "healthcare_hospital"}
_WATER_STRESS    = {"data_center", "healthcare_hospital", "industrial_heavy"}


def portfolio_health_check(assets: list) -> list[dict]:
    """
    Pre-calculation structural observations from asset attributes alone.
    Returns a list of insight dicts sorted by severity (error > warning > info).
    """
    if not assets:
        return []

    insights: list[dict] = []
    total_value = sum(a.replacement_value for a in assets)

    # ── Value concentration (single asset) ──────────────────────────────────
    for a in assets:
        share = a.replacement_value / total_value if total_value > 0 else 0
        if share >= _CONCENTRATION_PCT:
            insights.append({
                "level": "warning",
                "icon": "⚠️",
                "title": f"High value concentration: {a.name}",
                "body": (
                    f"**{a.name}** represents **{share*100:.0f}%** of total portfolio value "
                    f"({a.replacement_value:,.0f}). A single climate event affecting this "
                    f"asset could drive significant portfolio-level losses."
                ),
            })

    # ── Geographic concentration ─────────────────────────────────────────────
    country_vals: dict[str, float] = {}
    for a in assets:
        country_vals[a.region] = country_vals.get(a.region, 0) + a.replacement_value
    for country, val in country_vals.items():
        share = val / total_value if total_value > 0 else 0
        if share >= _COUNTRY_CONC_PCT:
            insights.append({
                "level": "warning",
                "icon": "🌍",
                "title": f"Geographic concentration in {country}",
                "body": (
                    f"**{share*100:.0f}%** of portfolio value is located in **{country}**. "
                    f"Country-level climate events (river flooding, heatwaves, named storms) "
                    f"could affect multiple assets simultaneously."
                ),
            })

    # ── Low-elevation flood exposure ─────────────────────────────────────────
    low_elev = [a for a in assets if a.first_floor_height_m <= _LOW_ELEVATION_M]
    below_sea = [a for a in assets if a.first_floor_height_m < _VERY_LOW_ELEV_M]

    if below_sea:
        names = ", ".join(a.name for a in below_sea[:3])
        if len(below_sea) > 3:
            names += f" + {len(below_sea)-3} more"
        insights.append({
            "level": "error",
            "icon": "🌊",
            "title": f"{len(below_sea)} asset(s) below sea level",
            "body": (
                f"**{names}** sit at negative elevation and face acute flood and storm surge exposure. "
                f"These assets are particularly vulnerable under accelerating sea-level rise projections "
                f"in high-emission scenarios."
            ),
        })
    elif low_elev:
        names = ", ".join(a.name for a in low_elev[:4])
        if len(low_elev) > 4:
            names += f" + {len(low_elev)-4} more"
        insights.append({
            "level": "warning",
            "icon": "🌊",
            "title": f"{len(low_elev)} asset(s) at low elevation (≤{_LOW_ELEVATION_M:.0f}m)",
            "body": (
                f"**{names}** are at or near ground level and may face increased inundation risk "
                f"as climate change intensifies precipitation extremes and raises sea levels."
            ),
        })

    # ── Wildfire-prone asset types in high-risk configurations ───────────────
    wildfire_wood = [a for a in assets
                     if a.asset_type in _WILDFIRE_TYPES
                     and getattr(a, "construction_material", "") == "wood_frame"]
    if wildfire_wood:
        names = ", ".join(a.name for a in wildfire_wood[:3])
        insights.append({
            "level": "warning",
            "icon": "🔥",
            "title": f"{len(wildfire_wood)} wood-frame asset(s) with wildfire exposure",
            "body": (
                f"**{names}** are wood-frame structures in asset categories with modelled wildfire "
                f"vulnerability. Wood-frame construction has significantly higher damage fractions "
                f"under wildfire scenarios compared to masonry or steel."
            ),
        })

    # ── Heat-sensitive assets ────────────────────────────────────────────────
    heat_sensitive = [a for a in assets if a.asset_type in _HEAT_SENSITIVE]
    if heat_sensitive:
        val = sum(a.replacement_value for a in heat_sensitive)
        insights.append({
            "level": "info",
            "icon": "🌡️",
            "title": f"{len(heat_sensitive)} heat-sensitive asset(s) in portfolio",
            "body": (
                f"Data centres, hospitals, offices, and heavy industry (total value: "
                f"{val:,.0f}) have elevated heat vulnerability. Cooling system demand and "
                f"productivity losses increase nonlinearly with peak temperatures."
            ),
        })

    # ── Water-stressed assets ────────────────────────────────────────────────
    water_assets = [a for a in assets if a.asset_type in _WATER_STRESS]
    if water_assets:
        insights.append({
            "level": "info",
            "icon": "💧",
            "title": f"{len(water_assets)} asset(s) with water-stress dependency",
            "body": (
                f"Data centres, hospitals, and heavy industrial facilities require reliable "
                f"water supply for cooling. WRI Aqueduct projects significant water stress "
                f"increases in arid regions by 2050 under high-emission scenarios."
            ),
        })

    # ── Old building stock ───────────────────────────────────────────────────
    old_assets = [a for a in assets if a.year_built <= _OLD_STOCK_YEAR]
    if old_assets:
        val = sum(a.replacement_value for a in old_assets)
        share = val / total_value if total_value > 0 else 0
        insights.append({
            "level": "info",
            "icon": "🏛️",
            "title": f"{len(old_assets)} asset(s) built before 1980 (pre-modern codes)",
            "body": (
                f"**{share*100:.0f}%** of portfolio value is in buildings constructed before "
                f"modern seismic, wind, and energy codes. These assets typically have higher "
                f"vulnerability across all hazard types."
            ),
        })

    # ── Sort: error → warning → info ─────────────────────────────────────────
    order = {"error": 0, "warning": 1, "info": 2}
    insights.sort(key=lambda x: order.get(x["level"], 9))
    return insights


def results_hotspots(
    annual_df: pd.DataFrame,
    assets: list,
    scenario_id: str,
    year: int = 2050,
) -> list[dict]:
    """
    Post-calculation risk hotspot insights from modelled EAD data.
    Returns a list of insight dicts sorted by severity.
    """
    if annual_df is None or annual_df.empty or not assets:
        return []

    insights: list[dict] = []
    sc_df = annual_df[annual_df["scenario_id"] == scenario_id]
    if sc_df.empty:
        return []

    asset_map = {a.id: a for a in assets}
    total_value = sum(a.replacement_value for a in assets)

    # ── Top-risk asset ────────────────────────────────────────────────────────
    yr_df = sc_df[sc_df["year"] == year]
    if not yr_df.empty:
        by_asset = yr_df.groupby("asset_id")["ead"].sum().sort_values(ascending=False)
        if not by_asset.empty:
            top_id = by_asset.index[0]
            top_ead = by_asset.iloc[0]
            top_asset = asset_map.get(top_id)
            if top_asset:
                ead_pct = top_ead / top_asset.replacement_value * 100
                total_ead = yr_df["ead"].sum()
                top_share = top_ead / total_ead * 100 if total_ead > 0 else 0
                level = "error" if ead_pct >= 2.0 else "warning" if ead_pct >= 0.5 else "info"
                insights.append({
                    "level": level,
                    "icon": "🏆",
                    "title": f"Highest-risk asset: {top_asset.name}",
                    "body": (
                        f"In **{year}** under the selected scenario, **{top_asset.name}** "
                        f"accounts for **{top_share:.0f}%** of portfolio EAD "
                        f"({top_ead:,.0f} | {ead_pct:.2f}% of asset value). "
                        f"Consider prioritising adaptation investment for this asset."
                    ),
                })

                # ── Stranded asset flag ──────────────────────────────────────
                if "pv" in sc_df.columns:
                    asset_pv = sc_df[sc_df["asset_id"] == top_id]["pv"].sum()
                    stranded_pct = asset_pv / top_asset.replacement_value * 100
                    if stranded_pct >= 15:
                        insights.append({
                            "level": "error",
                            "icon": "🚨",
                            "title": f"Potential stranded asset: {top_asset.name}",
                            "body": (
                                f"Cumulative discounted climate damages for **{top_asset.name}** "
                                f"represent **{stranded_pct:.1f}%** of replacement value over 2025–2050. "
                                f"This exceeds the 15% threshold indicative of stranded asset risk."
                            ),
                        })

    # ── Dominant hazard ───────────────────────────────────────────────────────
    if "hazard" in sc_df.columns and not yr_df.empty:
        by_hazard = yr_df.groupby("hazard")["ead"].sum().sort_values(ascending=False)
        if not by_hazard.empty:
            dom_haz = by_hazard.index[0]
            dom_val = by_hazard.iloc[0]
            total_ead = yr_df["ead"].sum()
            dom_pct = dom_val / total_ead * 100 if total_ead > 0 else 0
            haz_labels = {
                "flood": "River & Coastal Flood", "wind": "Extreme Wind",
                "wildfire": "Wildfire", "heat": "Extreme Heat",
                "cyclone": "Tropical Cyclone", "water_stress": "Water Stress",
            }
            if dom_pct >= 40:
                insights.append({
                    "level": "info",
                    "icon": "📊",
                    "title": f"Portfolio dominated by {haz_labels.get(dom_haz, dom_haz)} risk",
                    "body": (
                        f"**{haz_labels.get(dom_haz, dom_haz)}** accounts for "
                        f"**{dom_pct:.0f}%** of projected portfolio EAD in {year}. "
                        f"A hazard-specific adaptation strategy (e.g. flood barriers, cool roofs) "
                        f"could yield disproportionately high risk reduction."
                    ),
                })

    # ── Rapid EAD escalation (2025 → target year) ────────────────────────────
    yr_2025 = sc_df[sc_df["year"] == 2025]
    yr_tgt  = sc_df[sc_df["year"] == year]
    if not yr_2025.empty and not yr_tgt.empty:
        by_asset_2025 = yr_2025.groupby("asset_id")["ead"].sum()
        by_asset_tgt  = yr_tgt.groupby("asset_id")["ead"].sum()
        common = by_asset_2025.index.intersection(by_asset_tgt.index)
        if not common.empty:
            escalation = (by_asset_tgt[common] - by_asset_2025[common]) / by_asset_2025[common].clip(lower=1)
            fast_ids = escalation[escalation >= _ESCALATION_PCT].sort_values(ascending=False).head(3)
            if not fast_ids.empty:
                names = [asset_map[i].name for i in fast_ids.index if i in asset_map]
                pcts  = [f"{v*100:.0f}%" for v in fast_ids.values]
                bullet_lines = "\n".join(f"- **{n}** (+{p})" for n, p in zip(names, pcts))
                insights.append({
                    "level": "warning",
                    "icon": "📈",
                    "title": f"Rapidly escalating EAD: {len(fast_ids)} asset(s)",
                    "body": (
                        f"These assets show the fastest EAD growth from 2025 to {year} "
                        f"under the selected scenario:\n{bullet_lines}\n\n"
                        f"Early adaptation action yields the greatest NPV benefit for fast-escalating assets."
                    ),
                })

    # ── Geographic risk hotspot ───────────────────────────────────────────────
    if not yr_df.empty:
        # Build country → EAD mapping
        country_ead: dict[str, float] = {}
        for _, row in yr_df.iterrows():
            a = asset_map.get(row["asset_id"])
            if a:
                country_ead[a.region] = country_ead.get(a.region, 0) + row["ead"]
        if country_ead:
            top_country = max(country_ead, key=country_ead.get)
            top_country_ead = country_ead[top_country]
            total_ead = yr_df["ead"].sum()
            country_share = top_country_ead / total_ead * 100 if total_ead > 0 else 0
            if country_share >= 40 and len(country_ead) > 1:
                insights.append({
                    "level": "info",
                    "icon": "🗺️",
                    "title": f"Geographic risk concentration: {top_country}",
                    "body": (
                        f"**{country_share:.0f}%** of projected portfolio EAD in {year} "
                        f"originates from assets in **{top_country}**. "
                        f"Country-level climate policies and physical hazard trends "
                        f"in this region warrant close monitoring."
                    ),
                })

    # ── Sort: error → warning → info ─────────────────────────────────────────
    order = {"error": 0, "warning": 1, "info": 2}
    insights.sort(key=lambda x: order.get(x["level"], 9))
    return insights


def render_insights_html(insights: list[dict]) -> str:
    """
    Render a list of insight dicts as a single HTML string using BSR color palette.
    Call with st.markdown(render_insights_html(insights), unsafe_allow_html=True).
    """
    if not insights:
        return ""

    palette = {
        "error":   ("#FEECEC", "#C0392B", "#E74C3C"),   # bg, border, icon-bg
        "warning": ("#FEF6E4", "#D68910", "#F39C12"),
        "info":    ("#EAF4FB", "#1A6FA5", "#2E86C1"),
    }

    blocks = []
    for ins in insights:
        lvl = ins.get("level", "info")
        bg, border, icon_bg = palette.get(lvl, palette["info"])
        icon  = ins.get("icon", "ℹ️")
        title = ins.get("title", "")
        body  = ins.get("body", "").replace("\n", "<br>")

        # Simple markdown bold → html
        import re
        body = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", body)

        blocks.append(f"""
<div style="
    background:{bg};
    border-left:4px solid {border};
    border-radius:6px;
    padding:12px 16px;
    margin-bottom:10px;
    font-size:14px;
    line-height:1.5;
">
  <div style="font-weight:700;font-size:15px;margin-bottom:4px;">
    {icon}&nbsp; {title}
  </div>
  <div style="color:#333;">{body}</div>
</div>""")

    return "\n".join(blocks)
