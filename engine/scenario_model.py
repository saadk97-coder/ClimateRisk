"""
Climate scenario definitions: NGFS Phase V (2023), IEA WEO 2023, IPCC AR6 SSPs.

Sources
-------
NGFS Phase V Technical Note (Nov 2023):
  https://www.ngfs.net/sites/default/files/medias/documents/ngfs_climate_scenarios_phase_v.pdf
NGFS Scenarios Portal:
  https://www.ngfs.net/ngfs-scenarios-portal/

IEA World Energy Outlook 2023:
  https://www.iea.org/reports/world-energy-outlook-2023

IPCC AR6 WG1 SPM Table 1 (temperature ranges by SSP):
  https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/
IPCC AR6 WG1 Chapter 11 (weather extremes):
  https://www.ipcc.ch/report/ar6/wg1/chapter/chapter-11/
IPCC AR6 WG1 Chapter 12 (regional climates):
  https://www.ipcc.ch/report/ar6/wg1/chapter/chapter-12/

Hazard scaling factors derived from:
  Tabari (2020), Science of The Total Environment — flood frequency scaling
    https://doi.org/10.1016/j.scitotenv.2020.140612
  Knutson et al. (2020) — tropical cyclone intensity changes
    https://doi.org/10.1175/BAMS-D-18-0194.1
  Jolly et al. (2015) — fire weather index trends
    https://doi.org/10.1038/ncomms8537
  Zhao et al. (2021) — heat stress economic impacts
    https://doi.org/10.1038/s41586-021-03305-z
"""

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# NGFS Phase V scenarios (November 2023, updated GCAM 6.0 / REMIND-MAgPIE 3.2)
# Warming = global mean surface temperature above 1850–1900 pre-industrial baseline
# Source: https://www.ngfs.net/ngfs-scenarios-portal/
# ---------------------------------------------------------------------------
NGFS_V_SCENARIOS: Dict[str, dict] = {
    "net_zero_2050": {
        "label": "Net Zero 2050",
        "provider": "NGFS Phase V",
        "ssp": "SSP1-1.9",
        "category": "orderly",
        "description": (
            "Immediate, globally co-ordinated action achieves net-zero CO₂ by 2050. "
            "Warming limited to 1.5 °C. Requires rapid, deep decarbonisation across all sectors."
        ),
        "warming": {2025: 1.2, 2030: 1.3, 2040: 1.4, 2050: 1.5, 2060: 1.5, 2080: 1.5, 2100: 1.4},
        "color": "#1a9641",
        "source_url": "https://www.ngfs.net/ngfs-scenarios-portal/",
    },
    "below_2c": {
        "label": "Below 2 °C",
        "provider": "NGFS Phase V",
        "ssp": "SSP1-2.6",
        "category": "orderly",
        "description": (
            "Strong climate policies limit warming well below 2 °C with high probability. "
            "Orderly transition with co-ordinated policy action."
        ),
        "warming": {2025: 1.2, 2030: 1.4, 2040: 1.55, 2050: 1.7, 2060: 1.75, 2080: 1.8, 2100: 1.8},
        "color": "#78c679",
        "source_url": "https://www.ngfs.net/ngfs-scenarios-portal/",
    },
    "divergent_net_zero": {
        "label": "Divergent Net Zero",
        "provider": "NGFS Phase V",
        "ssp": "SSP1-1.9",
        "category": "disorderly",
        "description": (
            "NEW in Phase V. Net-zero achieved by 2050 but via divergent sectoral pathways — "
            "faster action in some regions/sectors offset by slower progress elsewhere. "
            "Higher near-term transition risk than 'Net Zero 2050'."
        ),
        "warming": {2025: 1.2, 2030: 1.35, 2040: 1.5, 2050: 1.6, 2060: 1.55, 2080: 1.5, 2100: 1.4},
        "color": "#addd8e",
        "source_url": "https://www.ngfs.net/ngfs-scenarios-portal/",
    },
    "delayed_transition": {
        "label": "Delayed Transition",
        "provider": "NGFS Phase V",
        "ssp": "SSP2-4.5",
        "category": "disorderly",
        "description": (
            "Policies delayed until 2030, then sharp transition. "
            "Higher physical risk in near term; stranded-asset risk from sudden late action."
        ),
        "warming": {2025: 1.2, 2030: 1.7, 2040: 1.9, 2050: 2.0, 2060: 2.2, 2080: 2.3, 2100: 2.4},
        "color": "#fd8d3c",
        "source_url": "https://www.ngfs.net/ngfs-scenarios-portal/",
    },
    "ndcs_only": {
        "label": "NDCs Only",
        "provider": "NGFS Phase V",
        "ssp": "SSP2-4.5",
        "category": "hot_house",
        "description": (
            "Countries implement current Nationally Determined Contributions only. "
            "No additional policy beyond stated pledges. Moderate overshoot of Paris targets."
        ),
        "warming": {2025: 1.2, 2030: 1.8, 2040: 2.1, 2050: 2.5, 2060: 2.7, 2080: 3.0, 2100: 3.0},
        "color": "#f03b20",
        "source_url": "https://www.ngfs.net/ngfs-scenarios-portal/",
    },
    "current_policies": {
        "label": "Current Policies",
        "provider": "NGFS Phase V",
        "ssp": "SSP5-8.5",
        "category": "hot_house",
        "description": (
            "Business as usual — no new climate policies beyond those already enacted. "
            "Highest physical risk trajectory."
        ),
        "warming": {2025: 1.2, 2030: 1.9, 2040: 2.4, 2050: 3.0, 2060: 3.5, 2080: 4.3, 2100: 4.3},
        "color": "#bd0026",
        "source_url": "https://www.ngfs.net/ngfs-scenarios-portal/",
    },
    "fragmented_world": {
        "label": "Fragmented World",
        "provider": "BSR Climate Scenarios 2025",
        "ssp": "SSP3-7.0",
        "category": "hot_house",
        "description": (
            "NEW in BSR Climate Scenarios 2025 (NGFS Phase V). "
            "Divergent national policies and weak international co-ordination mean climate "
            "action fractures along geopolitical fault lines. Some regions impose aggressive "
            "carbon pricing while others lock in fossil infrastructure — producing simultaneous "
            "high physical risk AND high transition risk. The most pessimistic risk profile "
            "because both channels compound each other: assets face both chronic damage and "
            "stranded-asset exposure. Peak transition risk hits 2030–2040 in regulated markets; "
            "physical risk compounds beyond 2040 everywhere."
        ),
        "warming": {2025: 1.2, 2030: 1.7, 2040: 2.2, 2050: 2.8, 2060: 3.3, 2080: 3.8, 2100: 4.0},
        "color": "#7B2D8B",   # purple — distinct; signals dual-channel risk
        "source_url": "https://www.bsr.org/en/reports/bsr-climate-scenarios-2025",
        "transition_risk": "high",
        "physical_risk": "high",
        "note": (
            "Unique risk profile: unlike Current Policies (high physical, low transition) or "
            "Net Zero 2050 (low physical, high near-term transition), Fragmented World combines "
            "both. Assets in carbon-regulated jurisdictions face stranded-asset risk; those in "
            "unregulated jurisdictions face accelerating physical damage without policy offsets."
        ),
    },
}

# ---------------------------------------------------------------------------
# IEA World Energy Outlook 2023 scenarios
# Source: https://www.iea.org/reports/world-energy-outlook-2023
# ---------------------------------------------------------------------------
IEA_WEO_2023_SCENARIOS: Dict[str, dict] = {
    "iea_nze": {
        "label": "Net Zero Emissions (NZE)",
        "provider": "IEA WEO 2023",
        "ssp": "SSP1-1.9",
        "category": "orderly",
        "description": (
            "The energy sector reaches net-zero CO₂ by 2050. "
            "Consistent with keeping the rise in global mean temperatures to 1.5 °C."
        ),
        "warming": {2025: 1.2, 2030: 1.3, 2040: 1.4, 2050: 1.5, 2060: 1.5, 2080: 1.5, 2100: 1.5},
        "color": "#1a9641",
        "source_url": "https://www.iea.org/reports/world-energy-outlook-2023",
    },
    "iea_aps": {
        "label": "Announced Pledges (APS)",
        "provider": "IEA WEO 2023",
        "ssp": "SSP1-2.6",
        "category": "orderly",
        "description": (
            "All climate commitments (NDCs + net-zero pledges) are met in full and on time. "
            "Limits warming to ~1.7 °C by 2100."
        ),
        "warming": {2025: 1.2, 2030: 1.45, 2040: 1.6, 2050: 1.7, 2060: 1.75, 2080: 1.8, 2100: 1.8},
        "color": "#74c476",
        "source_url": "https://www.iea.org/reports/world-energy-outlook-2023",
    },
    "iea_steps": {
        "label": "Stated Policies (STEPS)",
        "provider": "IEA WEO 2023",
        "ssp": "SSP2-4.5",
        "category": "hot_house",
        "description": (
            "Only policies enacted as of mid-2023 are implemented. "
            "Warming of ~2.4 °C by 2100."
        ),
        "warming": {2025: 1.2, 2030: 1.6, 2040: 1.95, 2050: 2.4, 2060: 2.6, 2080: 2.8, 2100: 2.9},
        "color": "#fd8d3c",
        "source_url": "https://www.iea.org/reports/world-energy-outlook-2023",
    },
}

# ---------------------------------------------------------------------------
# IPCC AR6 SSP scenarios (best estimate / median warming)
# Source: IPCC AR6 WG1 SPM Table 1
# https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/
# ---------------------------------------------------------------------------
IPCC_AR6_SCENARIOS: Dict[str, dict] = {
    "ssp1_19": {
        "label": "SSP1-1.9",
        "provider": "IPCC AR6",
        "ssp": "SSP1-1.9",
        "category": "orderly",
        "description": "Very low emissions; ~1.0 °C median by 2100 (range 0.3–1.8 °C).",
        "warming": {2025: 1.1, 2030: 1.1, 2040: 1.2, 2050: 1.4, 2060: 1.4, 2080: 1.3, 2100: 1.0},
        "color": "#1a9641",
        "source_url": "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/",
    },
    "ssp1_26": {
        "label": "SSP1-2.6",
        "provider": "IPCC AR6",
        "ssp": "SSP1-2.6",
        "category": "orderly",
        "description": "Low emissions; ~1.8 °C median by 2100 (range 1.0–2.6 °C).",
        "warming": {2025: 1.2, 2030: 1.3, 2040: 1.5, 2050: 1.7, 2060: 1.8, 2080: 1.8, 2100: 1.8},
        "color": "#78c679",
        "source_url": "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/",
    },
    "ssp2_45": {
        "label": "SSP2-4.5",
        "provider": "IPCC AR6",
        "ssp": "SSP2-4.5",
        "category": "intermediate",
        "description": "Intermediate emissions; ~2.7 °C median by 2100 (range 1.7–3.7 °C).",
        "warming": {2025: 1.2, 2030: 1.4, 2040: 1.8, 2050: 2.1, 2060: 2.3, 2080: 2.6, 2100: 2.7},
        "color": "#fecc5c",
        "source_url": "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/",
    },
    "ssp3_70": {
        "label": "SSP3-7.0",
        "provider": "IPCC AR6",
        "ssp": "SSP3-7.0",
        "category": "hot_house",
        "description": "High emissions; ~3.6 °C median by 2100 (range 2.3–5.0 °C).",
        "warming": {2025: 1.2, 2030: 1.5, 2040: 2.0, 2050: 2.4, 2060: 2.7, 2080: 3.3, 2100: 3.6},
        "color": "#f03b20",
        "source_url": "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/",
    },
    "ssp5_85": {
        "label": "SSP5-8.5",
        "provider": "IPCC AR6",
        "ssp": "SSP5-8.5",
        "category": "hot_house",
        "description": "Very high emissions; ~4.4 °C median by 2100 (range 3.3–5.7 °C).",
        "warming": {2025: 1.2, 2030: 1.6, 2040: 2.2, 2050: 2.8, 2060: 3.3, 2080: 4.0, 2100: 4.4},
        "color": "#bd0026",
        "source_url": "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/",
    },
}

# BSR Climate Scenarios 2025 — the four canonical BSR scenarios (NGFS Phase V aligned)
# Source: https://www.bsr.org/en/reports/bsr-climate-scenarios-2025
BSR_2025_SCENARIOS: Dict[str, dict] = {
    k: NGFS_V_SCENARIOS[k]
    for k in ["net_zero_2050", "delayed_transition", "current_policies"]
    if k in NGFS_V_SCENARIOS
}
BSR_2025_SCENARIOS["fragmented_world"] = NGFS_V_SCENARIOS["fragmented_world"]

# Master dict (backward-compatible — NGFS Phase V is the default set)
SCENARIOS: Dict[str, dict] = {**NGFS_V_SCENARIOS, **IEA_WEO_2023_SCENARIOS, **IPCC_AR6_SCENARIOS}

SCENARIO_PROVIDERS = {
    "BSR Climate Scenarios 2025": BSR_2025_SCENARIOS,
    "NGFS Phase V": NGFS_V_SCENARIOS,
    "IEA WEO 2023": IEA_WEO_2023_SCENARIOS,
    "IPCC AR6": IPCC_AR6_SCENARIOS,
}

PROVIDER_SOURCES = {
    "BSR Climate Scenarios 2025": "https://www.bsr.org/en/reports/bsr-climate-scenarios-2025",
    "NGFS Phase V": "https://www.ngfs.net/ngfs-scenarios-portal/",
    "IEA WEO 2023": "https://www.iea.org/reports/world-energy-outlook-2023",
    "IPCC AR6": "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/",
}

# ---------------------------------------------------------------------------
# Hazard intensity scaling factors per ΔT (multipliers on 1995–2014 baseline)
# All values are median estimates; see source studies above.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# BSR Climate Scenarios 2025 — Regional Qualitative Narratives
# Source: BSR (2025) Climate Scenarios 2025, https://www.bsr.org/en/reports/bsr-climate-scenarios-2025
# Aligned with NGFS Phase V; narratives cover physical risk, transition risk, and financial
# implications by region and decade. Designed for cross-functional scenario planning.
#
# Regions map to hazard_fetcher zone keys + ISO3 groups:
#   EUR  = Europe (GBR, EU/EEA, NOR, CHE)
#   USA  = North America (USA, CAN, MEX)
#   CHN  = East Asia (CHN, JPN, KOR, TWN)
#   IND  = South/Southeast Asia (IND, PAK, BGD, IDN, PHL, THA, VNM)
#   AUS  = Oceania (AUS, NZL, Pacific islands)
#   BRA  = Latin America (BRA, COL, ARG, PER, CHL)
#   MEA  = Middle East & Africa (SAU, UAE, ZAF, NGA, EGY, MAR)
#   global = Default
# ---------------------------------------------------------------------------
BSR_NARRATIVES: Dict[str, Dict[str, Dict[str, Dict[str, str]]]] = {
    "net_zero_2050": {
        "EUR": {
            "2030s": {
                "physical": "Near-term physical risks remain moderate — European flood events intensify along Rhine, Danube, and Thames catchments (~10–15% higher 1-in-50-yr flood flows), while southern Europe enters chronic drought. Heat waves breach 40°C in Iberia and Southern France more frequently (3–4× vs. 1990s baseline).",
                "transition": "EU Green Deal + Carbon Border Adjustment Mechanism drive the continent's most accelerated industrial decarbonisation. Carbon prices rise to €80–120/t CO₂ by 2030. Fossil-intensive sectors — cement, steel, petrochemicals — face regulatory and market pressure; green hydrogen and offshore wind attract massive capital inflows.",
                "financial": "Real estate in coastal and floodplain locations begins to face insurance repricing. Corporate issuers in high-carbon sectors confront rising cost of debt as sustainability-linked finance becomes mainstream. Transition-ready companies benefit from EU Taxonomy-aligned green finance at below-market rates.",
            },
            "2040s": {
                "physical": "Physical risk stabilises under Net Zero trajectory but accumulated warming (1.4–1.5°C) already locks in more intense Mediterranean droughts. Alpine glacier retreat accelerates, threatening hydropower and water supply for industry. Heat mortality in older, dense urban stock (Barcelona, Milan, Paris) increases significantly.",
                "transition": "Fossil fuel divestment is near-complete in institutional portfolios. Energy system almost fully decarbonised; industrial transformation largely delivered. Remaining transition risk is concentrated in real estate (renovation wave compliance — EU EPBD standards) and agriculture (land-use change obligations).",
                "financial": "Properties below EU EPBD minimum energy performance ratings face value discounts of 5–15%. Climate-adjusted insurance premiums for Mediterranean properties reflect drought and wildfire exposure. Green-certified infrastructure assets command premium valuations.",
            },
            "2050s": {
                "physical": "Europe stabilises near 1.5°C warming. Residual physical risks — coastal flooding for low-lying Netherlands and North Sea coasts, Mediterranean wildfire and water stress — are material but manageable under well-funded adaptation. Nature-based solutions widely deployed.",
                "transition": "Transition largely complete. Remaining financial risk is concentrated in physical adaptation capex requirements and litigation risk for past inaction. Carbon markets are stable; stranded fossil assets largely written down.",
                "financial": "Property values in climate-resilient, energy-efficient stock outperform. Infrastructure operators with demonstrable physical resilience attract long-term sovereign and pension capital.",
            },
        },
        "USA": {
            "2030s": {
                "physical": "Coastal flood risk accelerates on Atlantic and Gulf coasts (sea level rise compounds storm surge on top of 1-in-100-yr baseline). Midwest and South face intensifying extreme heat (40+ days >35°C in Texas, Florida, Southeast). Western wildfire seasons lengthen by 3–4 weeks; drought conditions intensify across Southwest (Colorado River basin stress).",
                "transition": "Federal climate policy remains contested but IRA-driven clean energy investment reshapes the energy system from below. State-level policies (California, Northeast) drive near-term transition risk for utilities and auto OEMs. Carbon pricing remains politically limited at federal level but sector-specific regulation accelerates.",
                "financial": "Coastal real estate markets in Florida, Gulf Coast face accelerating insurance withdrawal (State Farm, Allstate have already exited). Mortgage-backed securities with climate exposure face repricing as FHFA/SEC climate disclosure rules take effect. Clean energy companies and grid-hardening infrastructure see large capital inflows.",
            },
            "2040s": {
                "physical": "Heat stress in Sun Belt cities becomes an acute public health and operational challenge. Phoenix, Miami, Houston face 60+ days above 38°C annually. Agricultural productivity falls across the Great Plains; water stress intensifies for industrial users in the Colorado/Rio Grande basins.",
                "transition": "US economy substantially decarbonised in power and light transport; heavy industry and buildings lag. Remaining transition risk concentrated in midstream fossil fuel infrastructure (pipelines, refineries) facing stranded-asset risk under state and municipal litigation.",
                "financial": "Stranded asset risk materialises for refineries and LNG infrastructure in states with net-zero commitments. Adaptation investment in water infrastructure, grid resilience, and coastal protection creates large public and private investment opportunities.",
            },
            "2050s": {
                "physical": "Sea level rise commits low-lying Gulf and Atlantic coastal communities to managed retreat or persistent flood cycles. Residual physical risk locked in by 1.5°C warming is manageable with sustained adaptation investment.",
                "transition": "Transition substantially complete. Remaining transition risk in agriculture (methane, land use) and aviation/shipping.",
                "financial": "Infrastructure with demonstrable climate resilience — hardened grids, flood-protected logistics — trades at premium multiples.",
            },
        },
        "CHN": {
            "2030s": {
                "physical": "East Asian monsoon intensifies; pluvial and fluvial flooding in Yangtze, Yellow, and Pearl River Deltas more frequent (1-in-20-yr events occur every 10 years by 2035). Typhoon intensification raises wind and storm surge risk for coastal megacities (Shanghai, Guangzhou, Shenzhen). North China faces severe water stress; South China more intense precipitation.",
                "transition": "China's carbon neutrality by 2060 pledge drives the world's largest energy transition. National ETS expands; coal power phase-out accelerates. Manufacturing exporters face EU CBAM tariff exposure from 2026. Transition risk is front-loaded in coal provinces and steel/cement capacity.",
                "financial": "Coal-heavy provinces (Shanxi, Inner Mongolia) face significant economic transition risk. High-tech and renewables manufacturers are major beneficiaries. Real estate in low-lying coastal SEZs faces long-term flood risk discount.",
            },
            "2040s": {
                "physical": "Intensified Yellow River and Yangtze flooding becomes baseline expectation. Compound events (typhoon + extreme precipitation + tidal surge) threaten critical infrastructure in Pearl River Delta.",
                "transition": "Energy system largely decarbonised; remaining transition risk in heavy industry (steel, cement, chemicals). Carbon price converges toward global level; competitive dynamics for Chinese manufacturers depend on global carbon border mechanisms.",
                "financial": "Green bond market (world's largest) continues to attract global capital. Property developers in flood-prone coastal zones face growing discount; inland climate-resilient cities see relative outperformance.",
            },
            "2050s": {
                "physical": "At 1.5°C, physical risks stabilise. Sea level rise is locked in but manageable for well-defended coastal cities. Water stress in North China remains a structural challenge requiring ongoing investment.",
                "transition": "Transition substantially complete. China is now a net exporter of clean technology; residual transition risk in fossil fuel state enterprises.",
                "financial": "Green industrial policy creates durable competitive advantages in EVs, batteries, and solar manufacturing.",
            },
        },
        "IND": {
            "2030s": {
                "physical": "South and Southeast Asia face the most acute near-term physical risks globally. Wet bulb temperatures in South Asia approach physiological survivability limits (32–33°C wet bulb) during peak summer in Indo-Gangetic Plain. Monsoon variability intensifies — both droughts and floods become more frequent. Cyclone intensity in Bay of Bengal and Arabian Sea increases.",
                "transition": "India's transition is driven by energy security as much as climate policy. Rapid solar deployment reduces coal dependency; however, coal remains a near-term bridge. Just transition challenges are significant for coal mining communities.",
                "financial": "Outdoor labour productivity losses from heat stress create a structural drag on GDP growth (ILO estimates 4–5% reduction in working hours by 2030 in peak-heat regions). Agricultural income volatility increases in rain-fed farming regions.",
            },
            "2040s": {
                "physical": "Sea level rise threatens low-lying river deltas (Ganges-Brahmaputra, Mekong). Bangladesh faces existential risk to coastal agricultural land. Extreme precipitation events in Philippines, Vietnam, Indonesia cause repeated infrastructure damage.",
                "transition": "Regional energy systems become cleaner; manufacturing supply chains for global firms face scrutiny for Scope 3 emissions. Carbon tariffs from EU and US begin to affect export-oriented industries.",
                "financial": "Insurance gaps widen in the region: 90%+ of natural catastrophe losses are uninsured. Physical asset devaluation accelerates in coastal and drought-exposed zones without adaptation investment.",
            },
            "2050s": {
                "physical": "Residual risks at 1.5°C are meaningful but manageable with adaptation. Key challenge is avoiding maladaptation — investments that solve one risk while creating another.",
                "transition": "Clean energy transition creates industrial development opportunity; risk is left-behind fossil fuel infrastructure.",
                "financial": "Climate-resilient supply chain infrastructure commands premium risk ratings from global investors.",
            },
        },
        "AUS": {
            "2030s": {
                "physical": "Australian bushfire seasons lengthen and intensify — fire weather index days above 'severe' threshold increase 40–60% in SE Australia. Bleaching events on Great Barrier Reef become annual. Extreme rainfall events intensify in Queensland and NSW (echoes 2022 Brisbane floods). Coastal erosion accelerates.",
                "transition": "Australia's transition is politically contested but economically forced. LNG export revenues at risk as Asian demand shifts; iron ore and metallurgical coal face long-run demand decline. Clean energy investment expanding rapidly in offshore wind and green hydrogen for export.",
                "financial": "Agricultural assets in drought-exposed zones face valuation discount. Property insurance in bushfire and flood corridors reprices dramatically; some markets becoming uninsurable. Fossil fuel export revenues create sovereign balance sheet exposure.",
            },
            "2040s": {
                "physical": "Heat stress in inland Australia intensifies; urban heat islands in Sydney, Melbourne make outdoor work hazardous for more weeks per year. Water availability for agriculture in Murray-Darling Basin structurally reduced.",
                "transition": "Coal and LNG export revenues fall structurally; sovereign revenues require diversification. Green hydrogen export industry emerges as major opportunity.",
                "financial": "Real estate in coastal and bushfire-prone corridors continues to reprice. Infrastructure assets with embedded climate resilience attract long-term institutional capital.",
            },
            "2050s": {
                "physical": "At 1.5°C, Australia's physical risks are better contained. Wildfire and heat stress remain elevated vs. pre-industrial but stabilise. Reef and marine ecosystem damage is partially locked in.",
                "transition": "Largely complete for electricity sector; residual in mining and agriculture.",
                "financial": "Green export economy (hydrogen, critical minerals for clean tech) emerges as a growth driver.",
            },
        },
        "BRA": {
            "2030s": {
                "physical": "Amazon dieback risk increases at 1.5°C+ but remains below critical tipping point thresholds. Deforestation interacts with warming to intensify drought in eastern Amazon and Cerrado. Extreme rainfall in southern Brazil and Andes intensifies. São Paulo water supply faces increased stress.",
                "transition": "Brazil's biofuels and land-based carbon markets create transition opportunities, but enforcement of deforestation moratoriums remains critical. Agriculture sector faces supply chain pressure from EU deforestation regulation (EUDR).",
                "financial": "Agricultural commodity exporters face EUDR compliance costs and market access risks. Forest carbon credits provide revenue stream but with permanence risk. Urban real estate in flood-prone favela zones faces persistent uninsured loss.",
            },
            "2040s": {
                "physical": "Amazon remains the key risk: dieback threshold (2–2.5°C) approached under higher scenarios but avoided here. Cerrado agricultural zones face water stress and productivity decline. Southern cities face intensified pluvial flooding.",
                "transition": "Biofuel and green hydrogen exports create economic opportunities. Transition risk for oil sector (Petrobras) remains significant.",
                "financial": "Forest-backed financial instruments gain credibility and scale; agricultural land in climate-resilient zones commands premium.",
            },
            "2050s": {
                "physical": "Stabilisation at 1.5°C prevents worst-case Amazon dieback. Residual flood and drought risks managed through nature-based solutions and watershed management.",
                "transition": "Green economy transition largely complete; Brazil is a major exporter of low-carbon energy and food.",
                "financial": "Biodiversity-positive investment products attract large ESG capital flows.",
            },
        },
        "MEA": {
            "2030s": {
                "physical": "Middle East and North Africa face some of the world's sharpest physical risk trajectories. Summer temperatures in Gulf states exceed 50°C for extended periods, limiting outdoor activity. North Africa faces intensified drought (30–40% reduction in rainfall in Atlas region and Sahel fringe). Sub-Saharan Africa faces intensified flash flooding, locust outbreaks, and agricultural disruption.",
                "transition": "Gulf states face structural economic transition risk from oil revenue decline under global net-zero. MENA energy transition is slower given resource endowments, but renewable energy (solar) deployment is rapid and cost-competitive. Sub-Saharan Africa faces energy access and just transition challenges.",
                "financial": "Sovereign wealth funds of oil-exporting states are repositioning toward diversified assets. Real estate and commercial development in Gulf cities faces long-term habitability risk without adaptation.",
            },
            "2040s": {
                "physical": "Wet-bulb temperatures during Gulf summer approach human survivability limits without cooling. Agricultural collapse risk in parts of sub-Saharan Africa accelerates food insecurity and migration pressures.",
                "transition": "Oil revenues declining structurally; economic diversification strategies (Vision 2030, NEOM) face climate-related viability questions. North African renewable energy exports to Europe become a major economic opportunity.",
                "financial": "Insurance penetration remains very low across the region; physical asset losses are largely uninsured. Sovereign credit ratings for oil-dependent states face downgrade pressure.",
            },
            "2050s": {
                "physical": "Even at 1.5°C, residual physical risks in MENA are severe: heat, water stress, and sea level rise on Nile Delta are structural challenges. Adaptation investment requirements are among the highest globally as % of GDP.",
                "transition": "Transition pressure on fossil fuel economies is permanent. Gulf states that diversify successfully (UAE) vs. those that do not (less-diversified producers) diverge sharply in economic outcomes.",
                "financial": "Climate adaptation bonds and blended finance instruments from DFIs become critical for MENA sovereign financing.",
            },
        },
        "global": {
            "2030s": {
                "physical": "Global mean warming of 1.3–1.4°C above pre-industrial brings increased frequency of extreme events: 1-in-50-yr heat waves now occur every 10–15 years. Flood frequencies increase 10–20% globally. Fire weather conditions worsen on all inhabited continents.",
                "transition": "Net Zero 2050 requires the most rapid energy transition in history: coal power phase-out by 2035, EV transition accelerating, industrial decarbonisation underway. Carbon pricing expands to cover 60%+ of global emissions by 2030.",
                "financial": "Capital flows toward climate solutions accelerate ($3–4T/yr needed). Brown assets face progressive repricing. Early movers in adaptation and clean tech command premium multiples.",
            },
            "2040s": {
                "physical": "Warming stabilises near 1.5°C; physical risks plateau but do not fall. Irreversible losses (coral reefs, glaciers, permafrost) are locked in. Adaptation becomes the primary focus.",
                "transition": "Global energy transition largely delivered. Remaining transition risk in heavy industry, agriculture, and developing economies.",
                "financial": "Green asset premium becomes structural. Stranded fossil assets fully written off from institutional portfolios. Climate VaR becomes standard disclosure metric.",
            },
            "2050s": {
                "physical": "Stabilisation at 1.5°C; residual physical risks well below higher-warming scenarios. Nature-based solutions deployed at scale for carbon removal and ecosystem resilience.",
                "transition": "Transition complete for major emitting sectors. Long-term sovereign debt and infrastructure assets reflect stabilised physical risk trajectories.",
                "financial": "Climate risk is fully integrated into pricing across all asset classes; a new stable equilibrium for capital markets.",
            },
        },
    },

    "fragmented_world": {
        "EUR": {
            "2030s": {
                "physical": "Physical risks in Europe track above Net Zero 2050 trajectory — warming reaches 1.7°C by 2030 as global action falters. Alpine glaciers retreat faster; Rhine and Danube flood frequencies increase ~20%. Mediterranean wildfires intensify significantly; southern European drought becomes semi-permanent.",
                "transition": "The EU drives aggressive unilateral climate action — CBAM tariffs, higher carbon prices (€120–180/t CO₂ by 2030) — while trading partners fail to reciprocate. European exporters face competitiveness headwinds; industries relocate capacity to less-regulated jurisdictions ('carbon leakage'). EU Taxonomy compliance costs are front-loaded.",
                "financial": "Dual risk channel: European industrial assets face high transition costs AND rising physical damage simultaneously. Carbon-intensive sectors (steel, cement, aviation) experience compressed margins. Real estate in flood, wildfire, and coastal zones faces insurance repricing AND renovation compliance costs.",
            },
            "2040s": {
                "physical": "Warming approaches 2.2°C. Extreme heat events in southern Europe intensify; 1-in-10-yr events now occur every 3–5 years. Storm surge risk for North Sea coasts increases materially.",
                "transition": "Carbon leakage becomes politically unsustainable; EU recalibrates CBAM. Transition risk peaks and begins to moderate as global co-ordination partially improves. Stranded fossil assets in European portfolios largely written down by now.",
                "financial": "Highest dual-risk moment: physical and transition risks simultaneously elevated. Companies and real estate assets without active climate management face sharp value impairment.",
            },
            "2050s": {
                "physical": "At 2.8°C, European physical risks are substantially higher than Net Zero trajectory. Coastal flood risk for Rotterdam, Venice, London Thames Barrier reaches design limits. Mediterranean becomes a semi-arid zone requiring major water infrastructure investment.",
                "transition": "Transition substantially complete in Europe; physical risk is now the dominant channel. Residual transition risk in agriculture and land use.",
                "financial": "Physical climate risk premium is structural in European real estate and infrastructure valuations. Green infrastructure with embedded resilience features commands significant premium.",
            },
        },
        "USA": {
            "2030s": {
                "physical": "US physical risks track above orderly transition scenarios. Gulf Coast flood events intensify; Western wildfire seasons expand to year-round in California and Pacific Northwest. Midwest heat dome events intensify; agricultural output variability increases.",
                "transition": "Federal/state policy divergence creates a fractured regulatory landscape. Blue states (California, Northeast) impose aggressive carbon pricing and building codes; red states resist. Corporate sustainability teams face compliance complexity across 50 different regulatory environments. SEC climate disclosure rules face legal challenge.",
                "financial": "Insurance withdrawal from high-risk coastal and wildfire zones accelerates; federal backstops (NFIP) face fiscal stress. Red state/blue state regulatory divergence creates compliance cost bifurcation for national companies.",
            },
            "2040s": {
                "physical": "Gulf Coast faces persistent compound flooding (riverine + storm surge + sea level rise). Phoenix, Houston, Miami face heat emergencies exceeding the capacity of existing cooling infrastructure.",
                "transition": "US policy landscape remains divided; federal carbon pricing stalled. International trade pressure from carbon-border mechanisms (EU CBAM, others) begins to affect US export competitiveness in carbon-intensive sectors.",
                "financial": "Geographic sorting of capital accelerates: money moves from high-physical-risk, low-policy-action states toward climate-resilient, policy-stable jurisdictions. Municipal bond defaults in disaster-prone localities increase.",
            },
            "2050s": {
                "physical": "2.8°C warming produces severe consequences for heat, drought, and coastal flooding. Managed retreat from some Gulf and Atlantic coastal communities becomes unavoidable.",
                "transition": "Patchwork of state and local policies does not achieve national decarbonisation targets; US lags global peers on transition.",
                "financial": "Largest divergence in asset values between climate-resilient and exposed properties of any developed market.",
            },
        },
        "IND": {
            "2030s": {
                "physical": "South and Southeast Asia face the most severe near-term physical risks in the Fragmented World scenario. Wet-bulb temperatures approaching physiological limits hit earlier and more frequently. Monsoon variability reaches extreme levels; consecutive drought-flood cycles damage food systems.",
                "transition": "Least-developed countries lack the capital and policy frameworks to transition rapidly. Coal remains the dominant energy source through 2040 in many parts of South and Southeast Asia. Carbon border tariffs from EU and US begin to affect manufacturing export revenues.",
                "financial": "Labour productivity losses from heat stress reach 5–7% of GDP in peak-heat regions (ILO projections). Agricultural income volatility increases financing risk for rural smallholder lending. Insurance penetration remains below 5%; losses are overwhelmingly uninsured.",
            },
            "2040s": {
                "physical": "Compound risks intensify: cyclone damage, sea level rise on Ganges-Brahmaputra delta, and agricultural water stress compound simultaneously. Climate migration pressures build.",
                "transition": "External pressure (trade, finance) forces partial transition acceleration; technology transfer from developed nations remains contested.",
                "financial": "Development finance from MDBs (World Bank, ADB) becomes critical for both adaptation and transition. Sovereign credit spreads widen for most climate-vulnerable and policy-laggard economies.",
            },
            "2050s": {
                "physical": "At 2.8°C, South Asian physical risks are extremely severe. Some low-lying delta regions face near-permanent seasonal inundation; adaptation at scale is existentially necessary.",
                "transition": "Clean energy transition underway but lagged vs. developed markets; energy access gap closing slowly.",
                "financial": "Climate debt trap risk: sovereign borrowers face simultaneous adaptation financing needs and economic damage from physical risks.",
            },
        },
        "CHN": {
            "2030s": {
                "physical": "East Asian physical risks intensify. Yangtze Basin flooding events 30% more frequent; Yellow River water scarcity increases. South China Sea typhoon intensification creates storm surge risk for coastal SEZs.",
                "transition": "China's domestic transition proceeds (carbon neutrality by 2060 target maintained) but international fragmentation reduces technology co-operation and carbon market linkages. CBAM from EU creates trade friction for Chinese manufacturers.",
                "financial": "Chinese export manufacturers in energy-intensive sectors (steel, aluminium, cement) face carbon tariff exposure. Coastal industrial real estate in flood-prone SEZs faces deferred maintenance risk.",
            },
            "2040s": {
                "physical": "North China water stress reaches critical levels; Yellow River basin faces seasonal flow cessation. Compound typhoon-rainfall events damage coastal infrastructure at increasing frequency.",
                "transition": "China's clean energy deployment continues at pace; transition risk for domestic heavy industry remains elevated through 2040.",
                "financial": "Green finance markets (China's is the world's largest) continue to develop; however, geopolitical fragmentation reduces global investor participation.",
            },
            "2050s": {
                "physical": "2.8°C warming produces severe coastal, water stress, and heat risks in China. Sea level rise commits major delta cities (Shanghai) to sustained adaptation investment.",
                "transition": "Energy transition broadly complete; residual transition risk in fossil fuel state enterprises and coal-dependent provinces.",
                "financial": "Physical risk becomes the dominant valuation driver for Chinese coastal real estate and infrastructure.",
            },
        },
        "AUS": {
            "2030s": {
                "physical": "Australian physical risks escalate rapidly in Fragmented World. Bushfire seasons lengthen by 6–8 weeks; fire weather index days above catastrophic threshold increase 80–100% vs. 1990s. Coral bleaching becomes annual. Extreme rainfall events intensify on east coast.",
                "transition": "Australia's fossil fuel exports (LNG, coal) retain value longer in Fragmented World as global transition is delayed — but this creates lock-in risk. Sovereign fiscal dependency on fossil revenues increases while global demand outlook remains uncertain.",
                "financial": "Australian fossil fuel export revenues elevated near-term but face structural cliff edge in the 2040s as delayed global transition compresses. Insurance market retreat from bushfire and coastal flood zones accelerates. Property market bifurcation between resilient inland areas and exposed coastal/bushfire corridors.",
            },
            "2040s": {
                "physical": "Heat stress in inland Australia reaches levels that make outdoor agricultural work impossible during summer months. Murray-Darling water allocations collapse; major agricultural restructuring required.",
                "transition": "Fossil fuel revenues begin structural decline; sovereign balance sheet exposure requires urgent diversification. Green hydrogen opportunity narrows as competitors (MENA, EU) establish first-mover advantage.",
                "financial": "Stranded fossil fuel infrastructure risk materialises. Agricultural land values in drought zones fall sharply. Climate litigation risk against government for permitting fossil projects increases.",
            },
            "2050s": {
                "physical": "2.8°C+ warming makes parts of outback Australia functionally uninhabitable in summer. Coastal property losses from sea level rise and storm surge become structural.",
                "transition": "Late transition in progress; fossil fuel sector write-downs crystallise on sovereign balance sheet.",
                "financial": "Climate resilient infrastructure (desalination, renewable energy, hardened buildings) commands large premium.",
            },
        },
        "BRA": {
            "2030s": {
                "physical": "Amazon dieback risk increases under Fragmented World warming trajectory. Cerrado and eastern Amazon face intensifying dry seasons; tipping point approaches 2.0–2.5°C threshold. São Paulo water supply from Cantareira system faces recurrent crises. Southern Brazil faces more intense extreme rainfall.",
                "transition": "EUDR and EU deforestation regulations create market access barriers for Brazilian agriculture. Political resistance to deforestation enforcement intensifies under fragmented world conditions. Green and blue carbon markets develop unevenly across regions.",
                "financial": "Commodity exporters face supply chain scrutiny and market access risks. Forest carbon credits grow in volume but permanence risk from rising fire probability reduces credit quality. Urban flood losses in São Paulo, Rio de Janeiro remain predominantly uninsured.",
            },
            "2040s": {
                "physical": "Amazon dieback risk becomes acute near 2.2–2.5°C. Reduced evapotranspiration reduces rainfall for Brazilian agriculture. Cerrado productivity falls; cattle sector relocates. Northeast Brazil faces intensified drought.",
                "transition": "Delayed global transition means Brazilian fossil fuel (Petrobras pre-salt oil) revenues remain elevated longer. This creates a sovereign fiscal dilemma: transition too fast and lose revenue; transition too slow and face CBAM tariffs and stranded assets later.",
                "financial": "Agricultural lenders face increasing credit risk from weather volatility. Green bonds linked to deforestation prevention face scrutiny over additionality and permanence.",
            },
            "2050s": {
                "physical": "Amazon crosses partial tipping point threshold in some projections; eastern Amazon savannification progresses. Physical risk for Brazilian agriculture becomes structurally elevated.",
                "transition": "Late transition under global pressure; fossil revenue cliff edge approaches.",
                "financial": "Nature-based solution assets (intact forest, restored mangroves) trade at structural premium for carbon and biodiversity credits.",
            },
        },
        "MEA": {
            "2030s": {
                "physical": "Middle East and North Africa face acute and compounding physical risks in Fragmented World. Gulf summer temperatures regularly exceed 52–55°C with humidity making outdoor conditions lethal without cooling. North Africa enters severe and persistent drought. Sub-Saharan Africa faces compound climate risks — drought, flood, and agricultural disruption simultaneously.",
                "transition": "Gulf oil states benefit near-term from delayed global transition — elevated fossil fuel revenues extend. However, geopolitical fragmentation and regional instability create new transition risk vectors (carbon tariffs on Gulf exports to EU).",
                "financial": "Sovereign wealth funds of Gulf states accumulate capital while transition window is open, accelerating diversification strategies. North African and sub-Saharan sovereigns face fiscal stress from compound climate damages without adequate insurance or adaptation finance.",
            },
            "2040s": {
                "physical": "Wet bulb temperatures in Gulf exceed survivability limits for outdoor workers without cooling. Egypt's Nile Delta faces saltwater intrusion affecting agricultural land. Sub-Saharan food system stress creates regional migration pressure.",
                "transition": "Global fossil fuel demand begins structural decline even in Fragmented World as cost of alternatives falls below marginal cost. Gulf states face revenue cliff edge; diversification strategies tested.",
                "financial": "Sovereign credit spreads widen for oil-dependent states. Climate migration creates fiscal pressure on receiving countries in MENA and Europe.",
            },
            "2050s": {
                "physical": "2.8°C+ warming makes parts of the Middle East and North Africa functionally uninhabitable in summer without air conditioning. Sea level rise threatens coastal cities (Alexandria, Abu Dhabi).",
                "transition": "Fossil revenue decline accelerates; late transition underway. Renewable energy (solar) becomes dominant in regional power mix driven by cost, not policy.",
                "financial": "Habitability risk becomes a material factor in sovereign bond spreads and infrastructure asset valuations across MENA.",
            },
        },
        "global": {
            "2030s": {
                "physical": "Global warming of 1.7°C by 2030 — above orderly transition trajectories — locks in more severe near-term physical risks. Extreme events intensify simultaneously across all inhabited continents.",
                "transition": "Policy divergence creates uneven transition risk. Some jurisdictions (EU, parts of US, UK, Australia) impose aggressive carbon pricing; others resist. Corporate supply chains face fragmented compliance environments.",
                "financial": "Dual-channel risk makes portfolio management more complex: cannot simply hedge by going 'green' if physical risks also spike. Companies need both physical resilience AND transition readiness simultaneously.",
            },
            "2040s": {
                "physical": "Global warming approaches 2.2°C; physical risks track near the upper end of IPCC AR6 intermediate scenarios. Climate tipping point risks increase.",
                "transition": "Peak dual-risk moment globally: transition costs front-loaded in regulated markets while physical damages accumulate everywhere.",
                "financial": "Climate risk metrics (EALR, climate exposure scores) become standard for credit ratings and corporate valuations. The cost of capital for high-dual-risk assets rises sharply.",
            },
            "2050s": {
                "physical": "2.8°C warming produces severe global physical consequences: sea level rise commits major coastal cities to managed retreat or massive infrastructure investment; agricultural zones shift; water stress intensifies across most subtropical regions.",
                "transition": "Late global co-ordination emerges; transition accelerates in 2040s but misses 2°C target.",
                "financial": "Physical risk is the dominant driver of asset value dispersion globally. Geography, resilience, and adaptation investment become the primary determinants of long-term asset performance.",
            },
        },
    },

    "delayed_transition": {
        "EUR": {
            "2030s": {
                "physical": "Physical risks modestly above Net Zero trajectory in near-term. European floods and heat events intensify at 1.7°C+ by 2030. Mediterranean wildfire season lengthens materially.",
                "transition": "EU continues climate policy action but global co-ordination lags. Carbon prices rise to €100–140/t CO₂. Delayed transition means late-2020s acceleration of industrial decarbonisation creates stranded-asset risk for carbon-intensive capex committed in 2020–2025.",
                "financial": "Assets locked in to fossil infrastructure face accelerated write-downs from 2030 onwards. Real estate renovation costs peak in 2030–2040 as EPBD standards tighten rapidly.",
            },
            "2040s": {
                "physical": "Sharp transition after 2030 slows warming trajectory. By 2040 physical risks stabilise, though 2.0°C warming is already committed. Coastal and river flood frequencies remain elevated.",
                "transition": "Transition peak: maximum policy disruption, regulatory burden, and technology deployment simultaneously. Carbon price reaches €200+/t. Stranded assets crystallise across fossil fuel value chains.",
                "financial": "Dual transition risk peak — real estate retrofit compliance costs peak simultaneously with carbon-intensive sector write-downs. However, transition creates large green infrastructure investment opportunity.",
            },
            "2050s": {
                "physical": "Physical risks stabilise near 2.0–2.4°C. Residual physical damage is elevated vs. Net Zero 2050 but significantly below Current Policies or Fragmented World.",
                "transition": "Transition largely complete. Stranded asset write-downs largely absorbed. Green economy stabilises with lower cost of capital.",
                "financial": "Physical risk management becomes the primary climate finance focus; transition risk substantially priced.",
            },
        },
        "global": {
            "2030s": {
                "physical": "Near-term physical risks elevated — near-term inaction locks in higher warming before the late transition kicks in.",
                "transition": "Low near-term transition risk becomes very high transition risk post-2030 as sudden, sharp policy action compensates for delay. Stranded asset risk is concentrated in assets with 10–20 year capital cycles locked in pre-2030.",
                "financial": "Assets with long economic lives committed under 2020–2030 business-as-usual assumptions face highest stranded-asset risk. Short-cycle, flexible assets are more resilient.",
            },
            "2040s": {
                "physical": "Warming trajectory bends down post-2030 transition shock. Physical risks remain elevated at 2.0°C+ but track below high-emission scenarios.",
                "transition": "Maximum transition disruption globally: policy, technology, and market forces align in an abrupt shift. Carbon pricing reaches global coverage.",
                "financial": "Peak stranded-asset risk for fossil fuel infrastructure globally. Transition-ready companies and green infrastructure experience capital inflows.",
            },
            "2050s": {
                "physical": "Stabilisation at 2.0–2.4°C; physical risks materially above Net Zero but manageable with adaptation.",
                "transition": "Substantially complete. Long-term capital markets stabilise around green infrastructure and climate-resilient assets.",
                "financial": "Green premium for resilient assets is structural; fossil asset discount is permanent.",
            },
        },
    },

    "current_policies": {
        "EUR": {
            "2030s": {
                "physical": "Europe faces accelerating physical risks. Floods, extreme heat, wildfire, and coastal erosion all intensify above orderly transition trajectories. Mediterranean drought becomes chronic.",
                "transition": "Minimal transition risk near-term as global policy action remains limited. EU acts unilaterally but without global follow-through, CBAM effectiveness is reduced. Competitive disadvantage for early-mover European industries vs. unregulated competitors.",
                "financial": "Physical climate risk begins repricing in insurance, mortgage, and infrastructure debt markets. Real estate in exposed zones faces widening discount.",
            },
            "2040s": {
                "physical": "At 2.4°C global mean warming, European extreme events are significantly more frequent and intense. Alpine water supply crisis affects hydropower, industry, and agriculture.",
                "transition": "Minimal policy pressure globally; EU is an outlier. Limited carbon price creates less urgency for corporate transition — but this defers rather than avoids the eventual write-down.",
                "financial": "Physical risk is the dominant financial channel. Insurance premiums in high-risk zones increase 3–5× vs. 2020. Some coastal property markets become uninvestible.",
            },
            "2050s": {
                "physical": "3.0°C+ warming produces severe, compounding physical consequences. European agriculture faces structural disruption. Rhine navigation constraints become seasonal reality.",
                "transition": "Minimal transition has occurred; fossil asset values remain but are at high stranded-asset risk if policy eventually shifts.",
                "financial": "Physical risk becomes the dominant determinant of asset values across all classes. Real estate in resilient locations commands extreme premium.",
            },
        },
        "global": {
            "2030s": {
                "physical": "Global warming of 1.9°C by 2030 locks in more severe event frequencies globally. All major hazard categories (flood, heat, wildfire, drought) intensify simultaneously.",
                "transition": "Near-zero transition risk in this decade — the primary risk is physical, not regulatory. Companies benefit from deferred compliance costs but accumulate physical exposure.",
                "financial": "Physical risk repricing accelerates in insurance, real estate, and infrastructure debt. Cat bond spreads widen; reinsurance capacity tightens.",
            },
            "2040s": {
                "physical": "2.4°C global warming produces severe multi-hazard compounding: heat-drought-fire combinations, intensified tropical cyclones, and coastal flood becoming concurrent in many regions.",
                "transition": "Even under Current Policies, technology-driven transition accelerates in power and transport. Remaining transition risk from regulatory catch-up is deferred but not eliminated.",
                "financial": "Physical risk dominates all asset class valuations. Infrastructure operators, real estate, agriculture, and tourism face structural damage costs.",
            },
            "2050s": {
                "physical": "3.0°C+ warming is catastrophic for many ecosystems and human settlements. Sea level rise commitments are irreversible; tropical regions face survivability challenges without massive adaptation.",
                "transition": "Even in Current Policies, the clean energy transition is largely technology-driven by 2050. However, the physical damage is already locked in.",
                "financial": "Physical climate risk is the dominant macro-financial risk globally, potentially the largest source of asset value impairment in history.",
            },
        },
    },

    "ndcs_only": {
        "global": {
            "2030s": {
                "physical": "Physical risks track between Delayed Transition and Current Policies. Moderate near-term physical risk uplift of 10–20% on event frequencies.",
                "transition": "NDC implementation provides some policy certainty; transition risk is moderate and predictable rather than shock-driven.",
                "financial": "Moderate climate risk premium developing across asset classes. Orderly but incomplete transition creates investable green opportunities without the disruption of sharp policy turns.",
            },
            "2040s": {
                "physical": "2.1–2.5°C warming by 2040 produces significantly elevated physical risks across all hazard categories.",
                "transition": "Gap between NDC targets and 2°C pathway creates pressure for additional policy tightening. Risk of policy surprise increases.",
                "financial": "Asset owners with long-dated exposures begin discounting for eventual policy strengthening and/or accelerating physical damage.",
            },
            "2050s": {
                "physical": "2.5–3.0°C warming produces severe physical risk profiles, especially in tropical, coastal, and Mediterranean climates.",
                "transition": "Further policy tightening likely but late; stranded asset risk in fossil infrastructure materialises.",
                "financial": "Physical and transition risks both elevated. Dual-risk profile resembles Fragmented World in financial impact but without the geopolitical complexity.",
            },
        },
    },
}


def get_bsr_narrative(scenario_id: str, region: str, decade: str) -> Dict[str, str]:
    """
    Return BSR qualitative narrative for a scenario/region/decade combination.

    Parameters
    ----------
    scenario_id : NGFS/BSR scenario key (e.g. 'net_zero_2050', 'fragmented_world')
    region      : Zone key — EUR, USA, CHN, IND, AUS, BRA, MEA, global
    decade      : '2030s', '2040s', or '2050s'

    Returns dict with keys: 'physical', 'transition', 'financial'
    Falls back to 'global' region if specific region not found.
    Source: BSR Climate Scenarios 2025 https://www.bsr.org/en/reports/bsr-climate-scenarios-2025
    """
    sc_narratives = BSR_NARRATIVES.get(scenario_id, BSR_NARRATIVES.get("current_policies", {}))
    region_narratives = sc_narratives.get(region, sc_narratives.get("global", {}))
    return region_narratives.get(decade, {
        "physical": "Narrative not available for this combination.",
        "transition": "Narrative not available for this combination.",
        "financial": "Narrative not available for this combination.",
    })


# Global default hazard scaling (used when no region-specific scaling is available)
HAZARD_SCALING = {
    "flood": {
        # ~5–8 % per °C from Tabari 2020; AR6 WG1 Ch.11 Box 11.1
        # https://doi.org/10.1016/j.scitotenv.2020.140612
        1.0: 1.05, 1.5: 1.10, 2.0: 1.18, 2.5: 1.28, 3.0: 1.40, 4.0: 1.65, 4.4: 1.80,
    },
    "wind": {
        # Tropical cyclone max intensity +5 % per 2 °C; Knutson et al. 2020
        # https://doi.org/10.1175/BAMS-D-18-0194.1
        1.0: 1.02, 1.5: 1.04, 2.0: 1.07, 2.5: 1.10, 3.0: 1.13, 4.0: 1.20, 4.4: 1.25,
    },
    "wildfire": {
        # Fire Weather Index steep increase; Jolly et al. 2015
        # https://doi.org/10.1038/ncomms8537
        1.0: 1.10, 1.5: 1.20, 2.0: 1.45, 2.5: 1.70, 3.0: 1.90, 4.0: 2.40, 4.4: 2.70,
    },
    "heat": {
        # Cooling degree-day / productivity loss super-linear; Zhao et al. 2021
        # https://doi.org/10.1038/s41586-021-03305-z
        1.0: 1.15, 1.5: 1.30, 2.0: 1.65, 2.5: 2.00, 3.0: 2.40, 4.0: 3.30, 4.4: 3.90,
    },
    "cyclone": {
        # Same as wind but slightly amplified for storm surge component
        1.0: 1.03, 1.5: 1.06, 2.0: 1.10, 2.5: 1.15, 3.0: 1.20, 4.0: 1.32, 4.4: 1.40,
    },
    "coastal_flood": {
        # Coastal flood uses ADDITIVE SLR (metres) rather than a multiplier.
        # The values here are still consumed by get_hazard_multiplier() which
        # returns a multiplicative factor, but the damage engine converts this
        # to an additive offset for coastal_flood (see damage_engine.py).
        # To keep backward compatibility, the scaling is calibrated so that
        # at typical RP100 surge (~2m), the multiplier approximates the
        # additive SLR effect.  See COASTAL_SLR_ADDITIVE_M below.
        #
        # Source: IPCC AR6 WG1 Ch.9 Table 9.9 (Fox-Kemper et al. 2021);
        # Vousdoukas et al. (2018) Nature Communications — extreme sea levels.
        # https://doi.org/10.1038/s41467-018-04692-w
        1.0: 1.05, 1.5: 1.08, 2.0: 1.12, 2.5: 1.18, 3.0: 1.25, 4.0: 1.40, 4.4: 1.50,
    },
    "water_stress": {
        # Chronic water scarcity intensification per °C.
        # Source: WRI Aqueduct 4.0; IPCC AR6 WG2 Ch. 4
        # https://doi.org/10.1175/BAMS-D-20-0218.1
        1.0: 1.10, 1.5: 1.20, 2.0: 1.40, 2.5: 1.65, 3.0: 1.90, 4.0: 2.40, 4.4: 2.80,
    },
}

# Regional hazard scaling adjustments — multiplied on top of global scaling.
# IPCC AR6 WG1 Ch.11-12 shows significant regional variation in hazard response
# to global warming. These factors capture the most material differences.
# Sources: AR6 WG1 Ch.11 (extremes), Ch.12 (regional), Interactive Atlas.
REGIONAL_HAZARD_SCALING_FACTOR: Dict[str, Dict[str, float]] = {
    "EUR": {"flood": 1.15, "wildfire": 1.25, "heat": 0.85, "wind": 0.90, "coastal_flood": 1.10},
    "USA": {"flood": 1.05, "wildfire": 1.20, "heat": 1.10, "wind": 1.05, "coastal_flood": 1.15},
    "CHN": {"flood": 1.20, "wildfire": 0.90, "heat": 1.05, "wind": 1.10, "coastal_flood": 1.15},
    "IND": {"flood": 1.30, "wildfire": 0.80, "heat": 1.25, "wind": 1.15, "coastal_flood": 1.25},
    "AUS": {"flood": 0.90, "wildfire": 1.40, "heat": 1.15, "wind": 0.95, "coastal_flood": 0.95},
    "BRA": {"flood": 1.10, "wildfire": 1.30, "heat": 1.00, "wind": 0.85, "coastal_flood": 0.90},
    "MEA": {"flood": 0.80, "wildfire": 1.10, "heat": 1.35, "wind": 0.90, "coastal_flood": 1.00},
    "global": {"flood": 1.0, "wildfire": 1.0, "heat": 1.0, "wind": 1.0, "coastal_flood": 1.0},
}

HAZARD_SCALING_SOURCES = {
    "flood": {
        "citation": "Tabari (2020), Science of the Total Environment. AR6 WG1 Ch.11 Box 11.1.",
        "url": "https://doi.org/10.1016/j.scitotenv.2020.140612",
        "ar6_url": "https://www.ipcc.ch/report/ar6/wg1/chapter/chapter-11/",
    },
    "wind": {
        "citation": "Knutson et al. (2020), Bulletin of the American Meteorological Society.",
        "url": "https://doi.org/10.1175/BAMS-D-18-0194.1",
    },
    "wildfire": {
        "citation": "Jolly et al. (2015), Nature Communications — global fire weather trends.",
        "url": "https://doi.org/10.1038/ncomms8537",
    },
    "heat": {
        "citation": "Zhao et al. (2021), Nature — global labour productivity & heat stress.",
        "url": "https://doi.org/10.1038/s41586-021-03305-z",
    },
    "cyclone": {
        "citation": "Knutson et al. (2020) — tropical cyclone intensity scaling.",
        "url": "https://doi.org/10.1175/BAMS-D-18-0194.1",
    },
    "coastal_flood": {
        "citation": "IPCC AR6 WG1 Ch.9 (Fox-Kemper et al. 2021); Vousdoukas et al. (2018) Nat. Commun.",
        "url": "https://doi.org/10.1038/s41467-018-04692-w",
    },
    "water_stress": {
        "citation": "WRI Aqueduct 4.0 (2023); IPCC AR6 WG2 Ch. 4 (freshwater cycle).",
        "url": "https://www.wri.org/data/aqueduct-water-risk-atlas",
    },
}


# Additive sea level rise (metres above present-day MHWS) by warming level.
# Source: IPCC AR6 WG1 Ch.9 Table 9.9; Fox-Kemper et al. (2021).
# Regional variation handled via REGIONAL_HAZARD_SCALING_FACTOR coastal_flood entry.
COASTAL_SLR_ADDITIVE_M: Dict[float, float] = {
    0.0: 0.00,
    1.0: 0.10,   # ~2030 under most SSPs
    1.5: 0.18,   # ~2040 SSP2-4.5
    2.0: 0.28,   # ~2050 SSP2-4.5
    2.5: 0.40,   # ~2060 SSP3-7.0
    3.0: 0.55,   # ~2070 SSP5-8.5
    4.0: 0.85,   # late century high emission
    4.4: 1.00,   # upper bound AR6 median
}


def get_slr_additive(scenario_id: str, year: int, region: str = "global") -> float:
    """Return additive sea level rise (m) for a scenario/year/region.

    SLR is fundamentally additive to surge levels, unlike other hazards
    where multiplicative scaling is appropriate.

    NOTE: Regional adjustment is NOT applied here. The IPCC AR6 global median
    SLR values are used directly. Regional variation in coastal flood risk
    (e.g. higher surge in Bay of Bengal vs Mediterranean) is captured by
    the regional factor in get_scenario_multipliers() for the storminess
    component. Applying the regional factor in BOTH places would double-count.
    """
    delta_t = get_warming(scenario_id, year)
    slr = _interp(COASTAL_SLR_ADDITIVE_M, delta_t)
    return slr


def _interp(mapping: dict, x: float) -> float:
    keys = sorted(mapping.keys())
    if x <= keys[0]:
        return mapping[keys[0]]
    if x >= keys[-1]:
        return mapping[keys[-1]]
    for i in range(len(keys) - 1):
        lo, hi = keys[i], keys[i + 1]
        if lo <= x <= hi:
            frac = (x - lo) / (hi - lo)
            return mapping[lo] + frac * (mapping[hi] - mapping[lo])
    return 1.0


def get_hazard_multiplier(hazard: str, warming_delta_c: float, region: str = "global") -> float:
    """Return hazard intensity multiplier for a given warming level and region.

    Applies global scaling from HAZARD_SCALING, then adjusts by the regional
    factor from REGIONAL_HAZARD_SCALING_FACTOR (IPCC AR6 WG1 Ch.11-12).
    """
    base_mult = _interp(HAZARD_SCALING.get(hazard, {}), warming_delta_c)
    regional_factors = REGIONAL_HAZARD_SCALING_FACTOR.get(region, REGIONAL_HAZARD_SCALING_FACTOR["global"])
    regional_adj = regional_factors.get(hazard, 1.0)
    # Apply regional adjustment to the excess above 1.0 (the change portion)
    return 1.0 + (base_mult - 1.0) * regional_adj


def get_warming(scenario_id: str, year: int) -> float:
    """Interpolate warming (°C above pre-industrial) for scenario and year."""
    sc = SCENARIOS.get(scenario_id, {})
    w = sc.get("warming", {})
    if not w:
        return 1.2
    return _interp(w, year)


def get_scenario_multipliers(scenario_id: str, year: int, hazard: str, region: str = "global") -> float:
    """Return hazard intensity multiplier for a given scenario, year, hazard, and region."""
    delta_t = get_warming(scenario_id, year)
    return get_hazard_multiplier(hazard, delta_t, region)


def list_scenarios(provider: Optional[str] = None) -> List[dict]:
    if provider and provider in SCENARIO_PROVIDERS:
        src = SCENARIO_PROVIDERS[provider]
    else:
        src = NGFS_V_SCENARIOS  # default
    return [{"id": k, **v} for k, v in src.items()]


def list_horizons() -> List[int]:
    return list(range(2025, 2051))


def list_default_horizons() -> List[int]:
    """Coarse horizons for backward-compat scenario comparison charts."""
    return [2030, 2040, 2050]
