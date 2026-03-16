"""
Page 10 - Model governance, scope, validation posture, and lineage controls.
"""

import pandas as pd
import streamlit as st

from engine.governance import (
    BASELINE_METHOD,
    DCF_POSITIONING,
    METHODOLOGY_VERSION,
    RESULTS_POSITIONING,
    runtime_metadata,
    source_status_rows,
)

st.set_page_config(page_title="Governance", page_icon="🧭", layout="wide")

st.title("Model Governance & Assurance")
st.markdown(
    "This page documents model scope, active data pathways, validation expectations, and "
    "evidence controls for assurance-led review."
)

meta = runtime_metadata()
override_count = sum(
    len(hazard_map) for hazard_map in st.session_state.get("hazard_overrides", {}).values()
)

col1, col2, col3 = st.columns(3)
col1.metric("Methodology version", METHODOLOGY_VERSION)
col2.metric("Active override records", override_count)
col3.metric("Selected scenarios", len(st.session_state.get("selected_scenarios", [])))

st.divider()
st.subheader("Scope")
st.info(RESULTS_POSITIONING, icon="ℹ️")
st.warning(
    "Flood remains a screening-level proxy, not a hydraulic depth model. "
    "Use site-specific engineering and regulatory workflows for design, underwriting, or formal assurance.",
    icon="⚠️",
)

scope_df = pd.DataFrame(
    [
        {"Area": "Core results", "Position": RESULTS_POSITIONING},
        {"Area": "Baseline data pathway", "Position": BASELINE_METHOD},
        {"Area": "DCF", "Position": DCF_POSITIONING},
        {"Area": "Evidence exports", "Position": "Workbook exports carry run metadata, source lineage, method notes, and manual override provenance where applicable."},
    ]
)
st.dataframe(scope_df, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Source Activation Status")
st.caption(
    "The registry includes both active and catalogued sources. Catalogued sources are documented for transparency but are not used automatically in the current baseline flow."
)
st.dataframe(pd.DataFrame(source_status_rows()), use_container_width=True, hide_index=True)

st.divider()
st.subheader("Control Expectations")
st.markdown(
    """
- Manual hazard overrides require an override basis, evidence note, preparer, and UTC timestamp.
- Results and audit workbooks include lineage metadata and a dedicated manual-override sheet when overrides are active.
- Vulnerability downloads now expose alias-resolved control points so the reference surface matches the engine path.
- CSV uploads are validated for required schema, duplicate IDs, coordinate bounds, asset type, and ISO3 region code before import.
- Scenario weights in the DCF page must total 100%; the model no longer silently normalises them.
"""
)

st.divider()
st.subheader("Validation Posture")
validation_df = pd.DataFrame(
    [
        {"Check": "Regression suite", "Expectation": "Run `py -3 -m pytest -q` after installing dev dependencies."},
        {"Check": "Syntax sanity", "Expectation": "Run `py -3 -m compileall .` or targeted module compilation in constrained environments."},
        {"Check": "Workflow smoke test", "Expectation": "Use the sample portfolio and verify Portfolio → Scenarios → Hazards → Results → Audit → Vulnerability → DCF."},
        {"Check": "Evidence review", "Expectation": "Confirm workbook metadata, source sheets, method notes, and override provenance on exported XLSX files."},
    ]
)
st.dataframe(validation_df, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Known Limitations")
st.markdown(
    """
- Acute hazard damage estimates are based on discrete return-period curves and open-source vulnerability functions.
- Water stress is handled through a chronic pathway using Aqueduct-derived damage fractions rather than event-style EP integration.
- Zone overrides remain a preview aid on the Hazards page and do not rewrite portfolio country mapping in the Results engine.
- The DCF module is a scenario-testing tool; replacement-value mode is intentionally labeled as a screening proxy.
"""
)

st.divider()
st.subheader("Runtime Metadata")
st.dataframe(
    pd.DataFrame([{"Field": key, "Value": value} for key, value in meta.items()]),
    use_container_width=True,
    hide_index=True,
)
