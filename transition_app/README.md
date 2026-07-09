# BSR Transition Risk — standalone app

A self-contained Streamlit application for climate **transition** risk, separate from the
physical-risk platform. It reuses the four-layer engine in `engine/transition/` but keeps its
own intake and session state (keys prefixed `tr_`), and organises every output around the
**four TCFD transition-risk categories**.

## Run

```bash
# lean deps are enough (no geospatial stack needed)
pip install streamlit pandas numpy plotly openpyxl
streamlit run transition_app/Home.py
```

Windows PowerShell, compile-free:

```powershell
.venv\Scripts\python.exe -m pip install streamlit pandas numpy plotly openpyxl
.venv\Scripts\python.exe -m streamlit run transition_app/Home.py
```

## Sections

| Section | TCFD transition category | Engine layer |
|---|---|---|
| ① Data Entry | intake (sector, Scope 1/2/3, financials) | — |
| ② Policy & Legal Risk | Policy & Legal (carbon pricing, ETS, litigation) | L1 carbon cost + pass-through |
| ③ Technology Risk | Technology (obsolescence, sunk cost, capex) | L2 learning curves / stranding |
| ④ Market Risk | Market (demand shift, input cost, devaluation) | L3 network + demand-collapse stranding |
| ⑤ Reputation Risk | Reputation (stakeholder perception → cost of capital) | L4 CCExposure |
| ⑥ Results | consolidated financial impact + target gap | L1–L4 |
| ⑦ Methodology & Data | reference + Appendices A–E | — |

Analysis settings (scenarios, Layer-4 routing, σ, enabled layers, discount rate) live in the
sidebar and are shared across all category pages.

## Data entry fields (per entity)

`id`, `name`, `region` (ISO3), `sector` (taxonomy key), `replacement_value`, `annual_revenue`,
`scope1`, `scope2`, `scope3` (tCO₂/yr). CSV import/export and a worked-example loader are on the
Data Entry page. Physical-risk fields are not collected — they are irrelevant to the transition
layer and filled with defaults internally.

## Relationship to the physical-risk app

This app is independent (`streamlit run transition_app/Home.py`). The transition page was removed
from the physical-risk multipage app (`pages/11_TransitionRisk.py`) so the two are fully separate.
Both share the same `engine/` package; only the front ends differ.

## Reference

*BSR Transition Risk Methodology — Implementation v1* (14 pp). Carbon prices: NGFS Phase V
REMIND-MAgPIE via IIASA. I-O structure: EXIOBASE-3 2019 world totals. Pass-through and CCExposure:
sector-median empirical proxies. Screening-grade — not a regulatory disclosure without review.
