"""
XLSX export engine — generates formatted, multi-sheet workbooks for all outputs.
Uses openpyxl for full formatting control.
"""

import io
from typing import List, Optional
import pandas as pd
import numpy as np

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
    from openpyxl.utils import get_column_letter
    from openpyxl.chart import BarChart, LineChart, Reference
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False

# Colour palette
HDR_FILL = "1F4E79"   # dark blue
SUB_FILL = "2E75B6"   # medium blue
ALT_FILL = "D6E4F0"   # light blue
WARN_FILL = "FFEB9C"  # amber
ERR_FILL  = "FFC7CE"  # red
OK_FILL   = "C6EFCE"  # green


def _hdr_style(ws, row, fill_hex=HDR_FILL):
    fill = PatternFill("solid", fgColor=fill_hex)
    font = Font(bold=True, color="FFFFFF" if fill_hex in (HDR_FILL, SUB_FILL) else "000000")
    for cell in ws[row]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center")


def _autofit(ws, min_width=10, max_width=40):
    for col in ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=min_width)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(max_len + 2, min_width), max_width)


def _write_df(ws, df: pd.DataFrame, start_row: int = 1, header_fill=HDR_FILL):
    if df is None or df.empty:
        ws.cell(start_row, 1, "No data")
        return
    headers = list(df.columns)
    for j, h in enumerate(headers, 1):
        ws.cell(start_row, j, h)
    _hdr_style(ws, start_row, header_fill)
    for i, row in enumerate(df.itertuples(index=False), start_row + 1):
        for j, val in enumerate(row, 1):
            ws.cell(i, j, val if not (isinstance(val, float) and np.isnan(val)) else None)
    _autofit(ws)


def _add_metadata(ws, metadata: dict):
    ws.cell(1, 1, "Climate Risk Financial Quantification Platform")
    ws.cell(1, 1).font = Font(bold=True, size=14)
    ws.cell(2, 1, "BSR — Business for Social Responsibility")
    ws.cell(3, 1, "Framework: From Climate Science to Corporate Strategy")
    ws.cell(4, 1, "https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf")
    ws.cell(4, 1).font = Font(color="0070C0", underline="single")
    row = 5
    for k, v in metadata.items():
        ws.cell(row, 1, k)
        ws.cell(row, 2, str(v))
        row += 1
    return row + 1


def export_results_xlsx(
    asset_results_df: pd.DataFrame,
    annual_damages_df: Optional[pd.DataFrame],
    portfolio_summary: Optional[dict],
    scenarios: list,
    metadata: dict,
) -> bytes:
    """
    Generate results workbook with sheets:
      1. Portfolio Summary
      2. Asset Results
      3. Annual Damages 2025–2050
      4. Scenario Comparison
      5. Sources & Methodology
    """
    if not _HAS_OPENPYXL:
        buf = io.BytesIO()
        asset_results_df.to_excel(buf, index=False)
        return buf.getvalue()

    wb = Workbook()

    # ── Sheet 1: Summary ─────────────────────────────────────────────
    ws_sum = wb.active
    ws_sum.title = "Portfolio Summary"
    next_row = _add_metadata(ws_sum, metadata)
    if portfolio_summary:
        ws_sum.cell(next_row, 1, "Metric")
        ws_sum.cell(next_row, 2, "Value")
        _hdr_style(ws_sum, next_row)
        next_row += 1
        for k, v in portfolio_summary.items():
            ws_sum.cell(next_row, 1, k)
            ws_sum.cell(next_row, 2, v)
            next_row += 1
    _autofit(ws_sum)

    # ── Sheet 2: Asset Results ────────────────────────────────────────
    ws_ar = wb.create_sheet("Asset Results")
    _write_df(ws_ar, asset_results_df)

    # ── Sheet 3: Annual Damages ───────────────────────────────────────
    if annual_damages_df is not None and not annual_damages_df.empty:
        ws_ann = wb.create_sheet("Annual Damages 2025-2050")
        _write_df(ws_ann, annual_damages_df)

        # Pivot: year × scenario, total EAD
        try:
            pivot = annual_damages_df.pivot_table(
                index="year", columns="scenario_id", values="ead", aggfunc="sum"
            ).reset_index()
            ws_piv = wb.create_sheet("Annual EAD Pivot")
            _write_df(ws_piv, pivot)
        except Exception:
            pass

    # ── Sheet 4: Scenario Comparison ─────────────────────────────────
    if annual_damages_df is not None and not annual_damages_df.empty:
        ws_sc = wb.create_sheet("Scenario Comparison")
        sc_summary_rows = []
        for sc in scenarios:
            sc_df = annual_damages_df[annual_damages_df["scenario_id"] == sc]
            if sc_df.empty:
                continue
            from engine.scenario_model import SCENARIOS
            sc_label = SCENARIOS.get(sc, {}).get("label", sc)
            total_ead = sc_df["ead"].sum()
            total_pv = sc_df["pv"].sum()
            mean_ead = sc_df.groupby("year")["ead"].sum().mean()
            sc_summary_rows.append({
                "Scenario": sc_label,
                "Scenario ID": sc,
                "Total EAD 2025–2050 (£)": round(total_ead, 2),
                "Total PV Damages (£)": round(total_pv, 2),
                "Mean Annual EAD (£)": round(mean_ead, 2),
            })
        if sc_summary_rows:
            _write_df(ws_sc, pd.DataFrame(sc_summary_rows))

    # ── Sheet 5: Sources ─────────────────────────────────────────────
    ws_src = wb.create_sheet("Sources & Methodology")
    sources = [
        ["Component", "Source", "Citation", "URL"],
        ["Scenarios", "NGFS Phase V", "NGFS (2023) Climate Scenarios Phase V Technical Note", "https://www.ngfs.net/ngfs-scenarios-portal/"],
        ["Scenarios", "IEA WEO 2023", "IEA (2023) World Energy Outlook", "https://www.iea.org/reports/world-energy-outlook-2023"],
        ["Scenarios", "IPCC AR6", "IPCC WG1 SPM Table 1 (2021)", "https://www.ipcc.ch/report/ar6/wg1/chapter/summary-for-policymakers/"],
        ["Hazard scaling", "Flood", "Tabari (2020) Sci. Total Environ.", "https://doi.org/10.1016/j.scitotenv.2020.140612"],
        ["Hazard scaling", "Wind/Cyclone", "Knutson et al. (2020) BAMS", "https://doi.org/10.1175/BAMS-D-18-0194.1"],
        ["Hazard scaling", "Wildfire", "Jolly et al. (2015) Nature Comms", "https://doi.org/10.1038/ncomms8537"],
        ["Hazard scaling", "Heat", "Zhao et al. (2021) Nature", "https://doi.org/10.1038/s41586-021-03305-z"],
        ["Vulnerability", "Flood (structure)", "FEMA HAZUS 6.0 Technical Manual", "https://www.fema.gov/flood-maps/products-tools/hazus"],
        ["Vulnerability", "Flood (global)", "JRC Global Flood DDFs (Huizinga et al. 2017)", "https://publications.jrc.ec.europa.eu/repository/handle/JRC105688"],
        ["Vulnerability", "Wind", "HAZUS MH Hurricane Technical Manual", "https://www.fema.gov/sites/default/files/2020-09/fema_hazus-hurricane-technical-manual.pdf"],
        ["Vulnerability", "Wildfire", "Syphard et al. (2012) Ecosphere", "https://doi.org/10.1890/ES12-00197.1"],
        ["Vulnerability", "Heat", "IEA/IPCC cooling cost escalation + ILO (2019)", "https://www.ilo.org/global/topics/labour-administration-inspection/resources-library/publications/WCMS_711919"],
        ["Adaptation costs", "General", "FEMA BCA Reference Guide (2019)", "https://www.fema.gov/sites/default/files/2020-02/bca_reference_guide.pdf"],
        ["Adaptation costs", "Flood UK", "Environment Agency FCERM appraisal guidance", "https://www.gov.uk/guidance/flood-and-coastal-erosion-risk-management-research-reports"],
        ["EAD method", "Trapezoidal", "Standard catastrophe modelling (Lloyd's, RMS, AIR)", "https://www.lloyds.com/resources-and-services/lloyds-lab/technical-resources/catastrophe-modelling"],
        ["DCF framework", "BSR", "From Climate Science to Corporate Strategy", "https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf"],
        ["DCF framework", "TCFD", "TCFD Final Report (2017)", "https://www.fsb-tcfd.org/recommendations/"],
        ["Hazard data", "ISIMIP3b", "Frieler et al. (2017) GeoSci. Model Dev.", "https://www.isimip.org/"],
        ["Hazard data", "Regional fallback", "NGFS Hazard Baseline (compiled from above sources)", "See ngfs_hazard_baseline.json"],
    ]
    for r_idx, row_data in enumerate(sources, 1):
        for c_idx, val in enumerate(row_data, 1):
            ws_src.cell(r_idx, c_idx, val)
    _hdr_style(ws_src, 1)
    _autofit(ws_src)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_audit_xlsx(audit_df: pd.DataFrame, metadata: dict) -> bytes:
    """Export detailed calculation audit trail."""
    if not _HAS_OPENPYXL:
        buf = io.BytesIO()
        audit_df.to_excel(buf, index=False)
        return buf.getvalue()

    wb = Workbook()
    ws = wb.active
    ws.title = "Calculation Audit"
    next_row = _add_metadata(ws, metadata)
    ws.cell(next_row, 1, "Step-by-step calculation trace — fully auditable")
    ws.cell(next_row, 1).font = Font(bold=True, italic=True)
    next_row += 1
    _write_df(ws, audit_df, start_row=next_row)
    _autofit(ws)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_adaptation_xlsx(adaptation_df: pd.DataFrame, frontier_df: pd.DataFrame) -> bytes:
    """Export adaptation cost-benefit analysis."""
    if not _HAS_OPENPYXL:
        buf = io.BytesIO()
        adaptation_df.to_excel(buf, index=False)
        return buf.getvalue()

    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Adaptation CBA"
    _write_df(ws1, adaptation_df)

    ws2 = wb.create_sheet("Portfolio Frontier")
    _write_df(ws2, frontier_df)

    ws3 = wb.create_sheet("Methodology")
    notes = [
        ["Metric", "Formula", "Source"],
        ["Capex", "asset_value × capex_pct/100", "FEMA BCA Guide; EA FCERM"],
        ["Annual Opex", "capex × opex_annual_pct/100", "FEMA BCA Guide"],
        ["NPV Benefits", "Σ avoided_EAD × (1+r)^-t  over design life", "Standard NPV"],
        ["Cost–Benefit Ratio", "NPV Benefits / (capex + NPV opex)", "FEMA BCA; HM Treasury Green Book"],
        ["Payback Period", "capex / avoided_EAD_annual (years)", "Standard payback formula"],
        ["Avoided EAD", "baseline_EAD × damage_reduction_pct/100", "Per-measure effectiveness (see Sources)"],
        ["Discount Rate", "3.5% default (HM Treasury Green Book / NGFS green finance rate)", "https://www.gov.uk/government/publications/the-green-book-appraisal-and-evaluation-in-central-government"],
    ]
    for r_idx, row_data in enumerate(notes, 1):
        for c_idx, val in enumerate(row_data, 1):
            ws3.cell(r_idx, c_idx, val)
    _hdr_style(ws3, 1)
    _autofit(ws3)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_dcf_xlsx(dcf_results: list, scenario_comparison_df: pd.DataFrame) -> bytes:
    """Export climate-adjusted DCF results."""
    if not _HAS_OPENPYXL:
        buf = io.BytesIO()
        scenario_comparison_df.to_excel(buf, index=False)
        return buf.getvalue()

    wb = Workbook()

    ws_sc = wb.active
    ws_sc.title = "Scenario Comparison"
    _write_df(ws_sc, scenario_comparison_df)

    for r in dcf_results:
        safe_name = r.label[:28].replace("/", "-")
        ws = wb.create_sheet(safe_name)
        _write_df(ws, r.annual_detail)

    ws_m = wb.create_sheet("Methodology")
    meth = [
        ["Item", "Description", "Reference"],
        ["Base NPV", "NPV = Σ CF_t/(1+WACC)^t + TV/(1+WACC)^T", "Standard DCF"],
        ["Climate-Adjusted NPV", "NPV_climate = Σ (CF_t - ΔDamage_t + ΔSaving_t)/(1+WACC)^t + TV_adj", "BSR Climate Strategy Framework"],
        ["Climate Risk Premium", "Optional: WACC_climate = WACC + λ × physical_risk_score", "TCFD / BSR"],
        ["Terminal Value", "TV = CF_T × (1+g)/(WACC-g)  (Gordon Growth)", "Standard finance"],
        ["Scenario Weighting", "E[NPV] = Σ P(s) × NPV(s)", "TCFD scenario analysis"],
        ["BSR Framework", "From Climate Science to Corporate Strategy", "https://www.bsr.org/reports/BSR_Climate_Science_Corporate_Strategy.pdf"],
        ["TCFD Reference", "Recommendations of the Task Force on Climate-related Financial Disclosures", "https://www.fsb-tcfd.org/recommendations/"],
    ]
    for r_idx, row_data in enumerate(meth, 1):
        for c_idx, val in enumerate(row_data, 1):
            ws_m.cell(r_idx, c_idx, val)
    _hdr_style(ws_m, 1)
    _autofit(ws_m)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def df_to_xlsx(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    """Simple single-sheet export."""
    buf = io.BytesIO()
    if _HAS_OPENPYXL:
        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name
        _write_df(ws, df)
        wb.save(buf)
    else:
        df.to_excel(buf, index=False)
    return buf.getvalue()
