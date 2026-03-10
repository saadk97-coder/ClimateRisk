"""
Page 2 – Scenarios: BSR Climate Scenarios 2025 / NGFS Phase V / IEA WEO 2023 / IPCC AR6
selector, regional qualitative narratives, financial parameters, warming trajectories.
"""

import streamlit as st
import plotly.graph_objects as go
from engine.fmt import fmt as _fmt_cur
from engine.scenario_model import (
    SCENARIOS, SCENARIO_PROVIDERS, PROVIDER_SOURCES, list_scenarios,
    get_bsr_narrative,
)

st.set_page_config(page_title="Scenarios", page_icon="🌡️", layout="wide")

with st.sidebar:
    st.header("Portfolio Summary")
    n = len(st.session_state.get("assets", []))
    total_val = sum(a.replacement_value for a in st.session_state.get("assets", []))
    st.metric("Assets", n)
    st.metric("Total Value", _fmt_cur(total_val, st.session_state.get("currency_code", "GBP")))

st.title("Climate Scenarios & Regional Insights")
st.markdown(
    "Select a scenario framework and configure financial parameters. "
    "Regional qualitative insights (BSR Climate Scenarios 2025) are available "
    "below for each selected scenario."
)

# ── BSR context banner ─────────────────────────────────────────────────────
st.info(
    "**BSR Climate Scenarios 2025** are the qualitative framework underpinning this platform. "
    "They do not have independent damage data — instead, each BSR scenario maps to a quantitative "
    "pathway from NGFS Phase V / IPCC AR6. Select your preferred quantitative framework below; "
    "BSR regional narratives will appear alongside your chosen scenarios. "
    "[BSR Climate Scenarios 2025 ↗](https://www.bsr.org/en/reports/bsr-climate-scenarios-2025)"
)

# ── Scenario Provider ──────────────────────────────────────────────────────
st.subheader("Scenario Framework")

# BSR is not a standalone provider — it annotates the other frameworks
_provider_options = ["NGFS Phase V", "IEA WEO 2023", "IPCC AR6"]
current_provider = st.session_state.get("scenario_provider", "NGFS Phase V")
if current_provider not in _provider_options:
    current_provider = "NGFS Phase V"

col_prov, col_src = st.columns([3, 4])
with col_prov:
    new_provider = st.selectbox(
        "Select quantitative framework",
        _provider_options,
        index=_provider_options.index(current_provider),
        help=(
            "NGFS Phase V is the standard for financial institution TCFD/TNFD disclosure "
            "and covers the same pathways as BSR Climate Scenarios 2025. "
            "IEA WEO 2023 focuses on energy-system trajectories. "
            "IPCC AR6 SSPs underpin all frameworks."
        ),
    )
with col_src:
    st.markdown(
        """
        | Framework | Scenarios | Source |
        |---|---|---|
        | **NGFS Phase V** | 6 (incl. Fragmented World) | [NGFS Portal ↗](https://www.ngfs.net/ngfs-scenarios-portal/) |
        | **IEA WEO 2023** | 3 | [IEA WEO 2023 ↗](https://www.iea.org/reports/world-energy-outlook-2023) |
        | **IPCC AR6** | 5 | [AR6 SPM Table 1 ↗](https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/) |
        | **BSR 2025 overlay** | Narratives on all above | [BSR Report ↗](https://www.bsr.org/en/reports/bsr-climate-scenarios-2025) |
        """
    )

active_scenarios = SCENARIO_PROVIDERS[new_provider]

# ── Scenario selector ──────────────────────────────────────────────────────
st.divider()
st.subheader(f"Select Scenarios — {new_provider}")

if new_provider == "NGFS Phase V":
    st.caption(
        "NGFS Phase V (November 2023) uses GCAM 6.0 and REMIND-MAgPIE 3.2 IAMs with MAGICC7 temperature outputs. "
        "BSR Climate Scenarios 2025 maps directly onto these pathways for quantitative outputs. "
        "[Technical Note ↗](https://www.ngfs.net/sites/default/files/medias/documents/ngfs_climate_scenarios_phase_v.pdf)"
    )
elif new_provider == "IEA WEO 2023":
    st.caption(
        "IEA World Energy Outlook 2023 scenarios cover the global energy system through 2050. "
        "BSR's Net Zero 2050 aligns with NZE; Current Policies aligns with STEPS. "
        "[Full report ↗](https://www.iea.org/reports/world-energy-outlook-2023)"
    )
elif new_provider == "IPCC AR6":
    st.caption(
        "IPCC AR6 Shared Socioeconomic Pathways (SSPs) from the Sixth Assessment Report (2021). "
        "All BSR and NGFS scenarios are grounded in these SSP warming trajectories. "
        "[SPM Table 1 ↗](https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/)"
    )

prev_scenarios = st.session_state.get("selected_scenarios", ["current_policies", "net_zero_2050"])
# Filter to only scenarios in the active provider
prev_in_provider = [s for s in prev_scenarios if s in active_scenarios]
if not prev_in_provider:
    prev_in_provider = list(active_scenarios.keys())[:2]

CATEGORY_ICONS = {
    "orderly":      "🟢",
    "disorderly":   "🟡",
    "intermediate": "🟠",
    "hot_house":    "🔴",
}
FRAGMENTED_ICON = "🟣"   # Purple — dual-risk; visually distinct

cols = st.columns(len(active_scenarios))
new_scenarios = []
for i, (sc_id, sc_data) in enumerate(active_scenarios.items()):
    with cols[i]:
        is_fragmented = sc_id == "fragmented_world"
        cat_icon = FRAGMENTED_ICON if is_fragmented else CATEGORY_ICONS.get(sc_data.get("category", ""), "⚪")

        # Dual-risk badge for Fragmented World
        badge = ""
        if is_fragmented:
            badge = " *(dual-risk)*"
        elif sc_id == "current_policies":
            badge = " *(high physical)*"
        elif sc_id == "net_zero_2050":
            badge = " *(low physical)*"

        checked = st.checkbox(
            f"{cat_icon} **{sc_data['label']}**{badge}",
            value=sc_id in prev_in_provider,
            key=f"sc_{new_provider}_{sc_id}",
        )
        if checked:
            new_scenarios.append(sc_id)

        sc_ssp = sc_data.get("ssp", "")
        prov = sc_data.get("provider", new_provider)
        st.caption(f"*{sc_ssp}* · {prov}")
        st.markdown(f"<small>{sc_data['description'][:200]}{'…' if len(sc_data['description'])>200 else ''}</small>", unsafe_allow_html=True)

        # Warming milestones
        w = sc_data.get("warming", {})
        warming_bits = [f"{yr}: **{w[yr]}°C**" for yr in [2030, 2050, 2080] if yr in w]
        st.caption(" / ".join(warming_bits))

        # Fragmented World — show dual-risk callout
        if is_fragmented:
            st.markdown(
                "<div style='background:#F3E6F8;border-left:3px solid #7B2D8B;padding:6px 10px;"
                "border-radius:4px;font-size:12px;margin-top:4px;'>"
                "⚠️ <b>High physical + high transition risk</b> simultaneously. "
                "Unique dual-channel profile.</div>",
                unsafe_allow_html=True,
            )
        # Source info popover
        src_url = sc_data.get("source_url", "")
        if src_url:
            with st.popover("ℹ️ Source"):
                st.markdown(f"**Provider**: {prov}")
                st.markdown(f"**SSP basis**: {sc_ssp}")
                st.markdown(f"**[Source ↗]({src_url})**")
                note = sc_data.get("note", "")
                if note:
                    st.info(note)
                if is_fragmented:
                    st.markdown(
                        "**Fragmented World** is introduced in BSR Climate Scenarios 2025 "
                        "(aligned with NGFS Phase V Fragmented World scenario). "
                        "It is the only scenario combining high physical risk AND high "
                        "transition risk — assets face both compounding climate damage "
                        "and stranded-asset exposure from divergent regulation."
                    )

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
        help=(
            "Applied to PV of annual climate damages and adaptation benefits. "
            "3.5% = HM Treasury Green Book / standard green finance rate. "
            "Higher rates reduce the present value of long-term physical damage, "
            "potentially underweighting near-2050 risks — consider using 2–3.5% "
            "for long-horizon asset analysis."
        ),
    ) / 100.0
with col2:
    new_wacc = st.slider(
        "WACC (%) — for DCF",
        min_value=2.0, max_value=20.0,
        value=st.session_state.get("wacc", 0.08) * 100,
        step=0.5,
        help=(
            "Weighted Average Cost of Capital used for climate-adjusted DCF valuation on the DCF page. "
            "Typically 6–12% for real estate and infrastructure. "
            "Climate risk may warrant a higher WACC premium for exposed assets."
        ),
    ) / 100.0
with col3:
    st.markdown("**Reference rates**")
    st.markdown("- HM Treasury Green Book: **3.5%**")
    st.markdown("- NGFS green finance: **3.5%**")
    st.markdown("- [TCFD guidance ↗](https://www.fsb-tcfd.org/recommendations/)")
    with st.popover("ℹ️ Discount rate guidance"):
        st.markdown(
            "**Choosing a discount rate for climate risk:**\n\n"
            "The discount rate determines how heavily future climate damages are weighted "
            "relative to costs today. Key considerations:\n\n"
            "- **3.5%** (HM Treasury Green Book): Standard for UK public projects; "
            "recommended for general climate risk analysis\n"
            "- **2–3%**: Appropriate for long-lived infrastructure (50+ years) where "
            "tail risks compound over decades\n"
            "- **5–8%**: More appropriate for commercial real estate (shorter hold periods)\n"
            "- **>8%**: May underweight post-2040 physical risks significantly\n\n"
            "The Stern Review (2006) used a very low discount rate (~1.4%) to argue for "
            "aggressive early climate action; Nordhaus (2007) used ~5.5% and reached "
            "different conclusions. The choice is a value judgement as well as a "
            "financial one.\n\n"
            "Source: Stern N. (2006) The Economics of Climate Change. "
            "HM Treasury Green Book (2022 update)."
        )

# ── Warming trajectory chart ───────────────────────────────────────────────
st.divider()
st.subheader("Projected Warming Trajectories")

col_chart, col_note = st.columns([4, 1])
with col_note:
    with st.popover("ℹ️ About warming projections"):
        st.markdown(
            "**Global mean surface temperature** above pre-industrial baseline (1850–1900).\n\n"
            "Values shown are **median (50th percentile)** estimates from the respective "
            "scenario framework's Integrated Assessment Model (IAM) ensemble. "
            "Actual warming has significant uncertainty — IPCC AR6 reports likely ranges "
            "of ±0.5–1.0°C around median estimates for most scenarios.\n\n"
            "**Paris Agreement thresholds:**\n"
            "- 1.5°C: Upper limit of the ambitious Paris target\n"
            "- 2.0°C: Outer limit of the Paris Agreement commitment\n\n"
            "The hazard multipliers applied in damage calculations use these warming values "
            "with IPCC AR6 scaling relationships (Tabari 2020, Knutson 2020, Jolly 2015)."
        )

with col_chart:
    fig = go.Figure()
    for sc_id, sc_data in active_scenarios.items():
        if sc_id in new_scenarios:
            yrs = list(sc_data["warming"].keys())
            temps = list(sc_data["warming"].values())
            lwidth = 3 if sc_id == "fragmented_world" else 2
            ldash = "dash" if sc_data.get("category") == "disorderly" else "solid"
            fig.add_trace(go.Scatter(
                x=yrs, y=temps,
                mode="lines+markers",
                name=sc_data["label"],
                line=dict(color=sc_data.get("color", "#888"), width=lwidth, dash=ldash),
                hovertemplate=f"<b>{sc_data['label']}</b><br>Year: %{{x}}<br>Warming: %{{y:.1f}} °C<extra></extra>",
            ))

    fig.add_hline(y=1.5, line_dash="dot", line_color="#27ae60",
                  annotation_text="Paris 1.5 °C", annotation_position="right")
    fig.add_hline(y=2.0, line_dash="dot", line_color="#e67e22",
                  annotation_text="Paris 2.0 °C", annotation_position="right")
    fig.update_layout(
        xaxis_title="Year",
        yaxis_title="Global Mean Warming above pre-industrial (°C)",
        yaxis=dict(range=[0.8, 5.0]),
        hovermode="x unified",
        height=380,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=20, r=80, t=20, b=20),
        plot_bgcolor="white",
        paper_bgcolor="white",
    )
    st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Sources: "
    "[BSR Climate Scenarios 2025](https://www.bsr.org/en/reports/bsr-climate-scenarios-2025) | "
    "[NGFS Phase V (2023)](https://www.ngfs.net/ngfs-scenarios-portal/) | "
    "[IEA WEO 2023](https://www.iea.org/reports/world-energy-outlook-2023) | "
    "[IPCC AR6 WG1 SPM Table 1](https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/)"
)

# ── BSR Regional Qualitative Insights ─────────────────────────────────────
if new_scenarios:
    st.divider()
    st.subheader("BSR Regional Qualitative Insights")
    col_hdr, col_hdr_info = st.columns([6, 1])
    with col_hdr:
        st.markdown(
            "Decade-by-decade narrative insights from **BSR Climate Scenarios 2025**, covering "
            "physical risk, transition risk, and financial implications by region."
        )
    with col_hdr_info:
        with st.popover("ℹ️ About BSR Narratives"):
            st.markdown(
                "**BSR Climate Scenarios 2025 — Regional Narratives**\n\n"
                "These qualitative insights are drawn from BSR's flagship scenario publication, "
                "designed for cross-functional corporate scenario planning. They cover:\n\n"
                "- **Physical risk**: hazard intensification trends by region and decade\n"
                "- **Transition risk**: policy, technology, and market dynamics\n"
                "- **Financial implications**: capital flows, asset valuations, credit risk\n\n"
                "Narratives reflect broad regional patterns; site-specific conditions "
                "may differ materially. BSR recommends using these narratives in "
                "workshops with strategy, finance, operations, and legal teams.\n\n"
                "Source: [BSR Climate Scenarios 2025]"
                "(https://www.bsr.org/en/reports/bsr-climate-scenarios-2025)"
            )

    REGION_OPTIONS = {
        "EUR": "Europe (GBR, EU/EEA)",
        "USA": "North America (USA, CAN, MEX)",
        "CHN": "East Asia (CHN, JPN, KOR)",
        "IND": "South & SE Asia (IND, PAK, IDN)",
        "AUS": "Oceania (AUS, NZL)",
        "BRA": "Latin America (BRA, COL, ARG)",
        "MEA": "Middle East & Africa (SAU, ZAF, EGY)",
        "global": "Global (default)",
    }

    col_reg, col_dec = st.columns(2)
    with col_reg:
        narrative_region = st.selectbox(
            "Region",
            list(REGION_OPTIONS.keys()),
            format_func=lambda r: REGION_OPTIONS[r],
            help="Select the region for narrative insights. Choose the region most relevant to your portfolio.",
        )
    with col_dec:
        narrative_decade = st.selectbox(
            "Decade",
            ["2030s", "2040s", "2050s"],
            index=1,
            help="2030s = near-term transition risk; 2040s = peak dual-risk; 2050s = long-term physical risk trajectory",
        )

    # Show narrative cards for each selected scenario
    sc_cols = st.columns(min(len(new_scenarios), 3))
    for i, sc_id in enumerate(new_scenarios):
        sc_data = SCENARIOS.get(sc_id, {})
        sc_label = sc_data.get("label", sc_id)
        sc_color = sc_data.get("color", "#888")
        narrative = get_bsr_narrative(sc_id, narrative_region, narrative_decade)

        with sc_cols[i % len(sc_cols)]:
            # Scenario header strip
            st.markdown(
                f"<div style='background:{sc_color};color:white;padding:8px 12px;"
                f"border-radius:6px 6px 0 0;font-weight:700;font-size:14px;'>"
                f"{sc_label}</div>",
                unsafe_allow_html=True,
            )

            # Physical risk card
            with st.expander("🌊 Physical Risk", expanded=True):
                st.markdown(
                    f"<div style='font-size:13px;line-height:1.5;'>{narrative.get('physical','')}</div>",
                    unsafe_allow_html=True,
                )
            # Transition risk card
            with st.expander("⚡ Transition Risk"):
                st.markdown(
                    f"<div style='font-size:13px;line-height:1.5;'>{narrative.get('transition','')}</div>",
                    unsafe_allow_html=True,
                )
            # Financial implications card
            with st.expander("💰 Financial Implications"):
                st.markdown(
                    f"<div style='font-size:13px;line-height:1.5;'>{narrative.get('financial','')}</div>",
                    unsafe_allow_html=True,
                )

            st.caption(
                f"Source: BSR Climate Scenarios 2025 · {REGION_OPTIONS.get(narrative_region,narrative_region)} · {narrative_decade}"
            )

    st.caption(
        "Qualitative insights: [BSR Climate Scenarios 2025]"
        "(https://www.bsr.org/en/reports/bsr-climate-scenarios-2025) "
        "· Quantitative warming: NGFS Phase V / IPCC AR6"
    )

# ── Hazard Sensitivity Table ───────────────────────────────────────────────
if new_scenarios:
    st.divider()
    st.subheader("Hazard Intensity Multipliers")
    col_ht, col_ht_info = st.columns([6, 1])
    with col_ht:
        st.caption(
            "How much more intense each hazard becomes at each scenario's warming level "
            "relative to the 1995–2014 historical baseline. Applied to all damage calculations."
        )
    with col_ht_info:
        with st.popover("ℹ️ Scaling sources"):
            st.markdown(
                "**Hazard scaling methodology:**\n\n"
                "| Hazard | Source | Key finding |\n"
                "|---|---|---|\n"
                "| Flood | Tabari (2020) *Sci. Total Env.* | ~5–8%/°C increase in extreme precipitation |\n"
                "| Wind | Knutson et al. (2020) *BAMS* | Max tropical cyclone intensity +5%/2°C |\n"
                "| Wildfire | Jolly et al. (2015) *Nat. Comms.* | FWI season lengthening; area burned |\n"
                "| Heat | Zhao et al. (2021) *Nature* | Productivity loss super-linear above 2°C |\n"
                "| Water Stress | WRI Aqueduct 4.0 (2023) | ~4%/°C reduction in freshwater availability |\n\n"
                "All scaling is applied against the 1995–2014 historical baseline "
                "(consistent with ISIMIP3b and IPCC AR6 reference period)."
            )

    import pandas as pd
    from engine.scenario_model import get_scenario_multipliers, HAZARD_SCALING_SOURCES
    HAZARDS = ["flood", "wind", "wildfire", "heat", "water_stress"]
    YEARS = [2030, 2040, 2050]

    rows = []
    for sc_id in new_scenarios:
        sc_label = SCENARIOS.get(sc_id, {}).get("label", sc_id)
        for yr in YEARS:
            row = {"Scenario": sc_label, "Year": yr}
            for haz in HAZARDS:
                m = get_scenario_multipliers(sc_id, yr, haz)
                row[haz.replace("_", " ").title()] = f"{m:.2f}×"
            rows.append(row)

    mdf = pd.DataFrame(rows)
    st.dataframe(mdf, use_container_width=True, hide_index=True)

# ── Save ───────────────────────────────────────────────────────────────────
st.divider()
if st.button("💾 Save Configuration", type="primary"):
    st.session_state.scenario_provider = new_provider
    st.session_state.selected_scenarios = new_scenarios
    st.session_state.selected_horizons = list(range(2025, 2051))
    st.session_state.discount_rate = new_discount_rate
    st.session_state.wacc = new_wacc
    st.success(
        f"✅ Saved: **{new_provider}** | **{len(new_scenarios)} scenario(s)** selected | "
        f"Annual 2025–2050 | Discount rate **{new_discount_rate*100:.1f}%** | "
        f"WACC **{new_wacc*100:.1f}%**"
    )
