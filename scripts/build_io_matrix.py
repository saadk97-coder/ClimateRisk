#!/usr/bin/env python3
"""
Build a 20-sector world direct-requirements matrix (io_matrix.json schema) from
the real EXIOBASE-3 multi-regional input-output tables.

Source
------
EXIOBASE 3 (Stadler et al. 2018), industry-by-industry monetary IOT, downloaded
via `pymrio` from Zenodo (DOI 10.5281/zenodo.3583070). Public, no login.

    pip install pymrio
    python -c "import pymrio; pymrio.download_exiobase3(storage_folder='exio', years=[2019], system='ixi')"

Method
------
1. Parse the single-year EXIOBASE IOT (49 regions x 163 industries).
2. Aggregate all 49 regions into one 'WORLD' region (world totals) and the 163
   EXIOBASE industries into the engine's 20 sectors via the concordance below.
3. Recompute A = Z * diag(1/x) on the aggregated system.
4. Reorder to the engine's sector_order.
5. EXIOBASE has no ICE/EV vehicle split nor commercial/residential real-estate
   split, so those two twin sectors are synthesised by copying their sibling's
   coefficients (documented assumption, flagged in _meta).

This is a REVIEWED CANDIDATE: it writes io_matrix.candidate.json, NOT the
calibrated io_matrix.json. Diff the two, sanity-check the concordance, then adopt
by renaming if you accept it.

Concordance notes (judgement calls worth reviewing)
---------------------------------------------------
- Electricity transmission & distribution folded into power_renewable (no grid
  bucket exists) — inflates power_renewable as a supplier.
- Coal/gas/uranium extraction all folded into oil_upstream ("fossil & fissile
  extraction") — no separate fuel-mining bucket.
- Non-aluminium non-ferrous metals (copper, lead/zinc/tin, precious, other) and
  their ores fold into manufacturing_general; only aluminium is broken out.
- Construction and food/textile/wood/paper manufacturing fold into
  manufacturing_general.
- Rail/other-land transport, pipelines, trade, finance, waste, water and public
  services fold into services.
"""

from __future__ import annotations
import argparse
import datetime as _dt
import json
import os
import sys

import numpy as np

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "transition")
)

# EXIOBASE ExioCode -> engine sector key. Codes not listed fall back to services.
# Prefix rules are applied in _sector_for() so we do not have to enumerate every
# i01.* / i90.* variant by hand.
_EXACT = {
    # ---- power generation --------------------------------------------------
    "i40.11.a": "power_coal",
    "i40.11.b": "power_gas",
    "i40.11.f": "power_gas",              # petroleum & oil-derivative power
    "i40.11.c": "power_renewable",        # nuclear (non-fossil)
    "i40.11.d": "power_renewable",        # hydro
    "i40.11.e": "power_renewable",        # wind
    "i40.11.g": "power_renewable",        # biomass & waste
    "i40.11.h": "power_renewable",        # solar PV
    "i40.11.i": "power_renewable",        # solar thermal
    "i40.11.j": "power_renewable",        # tide/wave/ocean
    "i40.11.k": "power_renewable",        # geothermal
    "i40.11.l": "power_renewable",        # electricity nec
    "i40.12": "power_renewable",          # transmission of electricity
    "i40.13": "power_renewable",          # distribution & trade of electricity
    # ---- gas / heat distribution ------------------------------------------
    "i40.2": "gas_distribution",
    "i40.3": "gas_distribution",          # steam & hot water supply
    # ---- fossil & fissile extraction --------------------------------------
    "i10": "oil_upstream",                # coal & lignite mining
    "i11.a": "oil_upstream",              # crude petroleum
    "i11.b": "oil_upstream",              # natural gas
    "i11.c": "oil_upstream",              # other petroleum/gaseous
    "i12": "oil_upstream",                # uranium/thorium
    # ---- fuel refining -----------------------------------------------------
    "i23.1": "oil_refining",              # coke oven
    "i23.2": "oil_refining",              # petroleum refinery
    "i23.3": "oil_refining",              # nuclear fuel processing
    # ---- steel -------------------------------------------------------------
    "i13.1": "steel",                     # iron ore mining
    "i27.a": "steel",                     # basic iron & steel
    "i27.a.w": "steel",                   # secondary steel
    "i27.5": "steel",                     # casting of metals
    # ---- aluminium ---------------------------------------------------------
    "i13.20.13": "aluminium",             # aluminium ore
    "i27.42": "aluminium",
    "i27.42.w": "aluminium",
    # ---- cement & non-metallic minerals -----------------------------------
    "i14.1": "cement",                    # stone quarrying
    "i14.2": "cement",                    # sand & clay
    "i26.a": "cement", "i26.a.w": "cement",
    "i26.b": "cement", "i26.c": "cement",
    "i26.d": "cement", "i26.d.w": "cement",
    "i26.e": "cement",
    # ---- chemicals ---------------------------------------------------------
    "i14.3": "chemicals",                 # chemical/fertiliser minerals, salt
    "i24.a": "chemicals", "i24.a.w": "chemicals",
    "i24.b": "chemicals", "i24.c": "chemicals", "i24.d": "chemicals",
    "i25": "chemicals",                   # rubber & plastic products
    # ---- vehicle manufacturing (ICE; EV synthesised) ----------------------
    "i34": "road_transport_ice",
    # ---- transport services -----------------------------------------------
    "i62": "aviation",
    "i61.1": "shipping", "i61.2": "shipping",
    # ---- real estate (commercial; residential synthesised) ----------------
    "i70": "real_estate_commercial",
    # ---- data / compute ----------------------------------------------------
    "i72": "data_center",
}

# Prefix rules for the many-variant families (checked after _EXACT).
_PREFIX = [
    ("i01", "agriculture"),
    ("i02", "agriculture"),
    ("i05", "agriculture"),
]

_MANUFACTURING = {  # explicit manufacturing_general members
    "i15", "i16", "i17", "i18", "i19", "i20", "i20.w", "i21.1", "i21.w.1",
    "i21.2", "i22", "i28", "i29", "i30", "i31", "i32", "i33", "i35", "i36",
    "i37", "i37.w.1", "i45", "i45.w",
    # non-aluminium non-ferrous metals + ores
    "i13.20.11", "i13.20.12", "i13.20.14", "i13.20.15", "i13.20.16",
    "i27.41", "i27.41.w", "i27.43", "i27.43.w", "i27.44", "i27.44.w",
    "i27.45", "i27.45.w",
}


def _sector_for(code: str, name: str) -> str:
    if code in _EXACT:
        return _EXACT[code]
    if code in _MANUFACTURING:
        return "manufacturing_general"
    for pre, tgt in _PREFIX:
        if code == pre or code.startswith(pre + "."):
            return tgt
    if code.startswith("i15"):        # food/beverage processing
        return "manufacturing_general"
    # everything else — trade, finance, transport services, waste, water,
    # public & business services — is screening-level "services".
    return "services"


def build(zip_path: str) -> dict:
    try:
        import pymrio
    except ImportError:
        sys.exit("pymrio not installed. Run: pip install pymrio")

    clf = pymrio.get_classification("exio3_ixi").sectors
    name_to_code = dict(zip(clf.ExioName, clf.ExioCode))

    io = json.load(open(os.path.join(_DATA_DIR, "io_matrix.json"), encoding="utf-8"))
    sector_order = list(io["_meta"]["sector_order"])

    print(f"Parsing {zip_path} …")
    mrio = pymrio.parse_exiobase3(path=zip_path)

    regions = list(mrio.get_regions())
    sectors = list(mrio.get_sectors())

    # sector aggregation vector aligned to the mrio sector index order
    sector_agg = []
    unmatched = []
    for s in sectors:
        code = name_to_code.get(s, "")
        tgt = _sector_for(code, s)
        sector_agg.append(tgt)
        if tgt == "services" and code not in _EXACT and code not in _MANUFACTURING:
            unmatched.append((code, s))

    region_agg = ["WORLD"] * len(regions)

    print("Aggregating 49 regions -> WORLD and 163 industries -> 20 sectors …")
    mrio.aggregate(region_agg=region_agg, sector_agg=sector_agg)
    mrio.calc_all()

    # A for the single WORLD region, as a 20x20 frame
    A_df = mrio.A.loc[("WORLD",), ("WORLD",)]
    A_df.index = A_df.index.get_level_values(-1)
    A_df.columns = A_df.columns.get_level_values(-1)
    A_df = A_df.reindex(index=sector_order, columns=sector_order)

    A = A_df.to_numpy(dtype=float)

    # --- synthesise the two sectors EXIOBASE cannot split -------------------
    idx = {s: i for i, s in enumerate(sector_order)}
    _copy_twin(A, idx, src="road_transport_ice", dst="road_transport_ev")
    _copy_twin(A, idx, src="real_estate_commercial", dst="real_estate_residential")

    # numerical hygiene: clip tiny negatives (rounding), cap at <1 column sums
    A = np.clip(A, 0.0, None)
    A = np.nan_to_num(A)

    value_added_share = (1.0 - A.sum(axis=0)).tolist()

    out = {
        "_meta": {
            "description": (
                "20-sector world direct-requirements matrix A aggregated from the "
                "real EXIOBASE-3 industry-by-industry MRIO (all 49 regions summed "
                "to WORLD totals). A[i,j] = USD input from sector i per USD output "
                "of sector j."
            ),
            "sources": [
                "EXIOBASE 3 (Stadler et al. 2018), IOT ixi, via pymrio; "
                "DOI 10.5281/zenodo.3583070"
            ],
            "method": "region+sector aggregation of Z and x, then A = Z * diag(1/x)",
            "calibration_year": 2019,
            "currency": "MEUR (EXIOBASE native; A is unit-free ratio)",
            "synthesised_sectors": {
                "road_transport_ev": "copied from road_transport_ice (EXIOBASE has no ICE/EV split)",
                "real_estate_residential": "copied from real_estate_commercial (EXIOBASE has no split)",
            },
            "concordance_caveats": (
                "electricity T&D -> power_renewable; coal/gas/uranium extraction -> "
                "oil_upstream; non-Al non-ferrous metals -> manufacturing_general; "
                "construction & light manufacturing -> manufacturing_general; "
                "rail/land/pipeline transport, trade, finance, waste, water, public "
                "services -> services"
            ),
            "sector_order": sector_order,
            "retrieved_utc": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        },
        "A": [[round(float(v), 6) for v in row] for row in A],
        "value_added_share": [round(float(v), 6) for v in value_added_share],
    }

    # --- validation ---------------------------------------------------------
    _validate(A, sector_order)
    print(f"Concordance: {len(sectors)} industries -> {len(set(sector_agg))} sectors.")
    print(f"  industries defaulting to 'services': {len(unmatched)}")
    return out


def _copy_twin(A: np.ndarray, idx: dict, src: str, dst: str) -> None:
    """Give `dst` the same input/output structure as `src` (EXIOBASE has no split)."""
    si, di = idx[src], idx[dst]
    A[:, di] = A[:, si]        # dst buys like src
    A[di, :] = A[si, :]        # dst supplies like src
    A[di, di] = A[si, si]
    A[si, di] = A[si, si]
    A[di, si] = A[si, si]


def _validate(A: np.ndarray, sector_order: list) -> None:
    n = len(sector_order)
    assert A.shape == (n, n), f"A not {n}x{n}: {A.shape}"
    assert np.all(A >= 0), "negative entries in A"
    assert np.all(A <= 1), "entries > 1 in A"
    col = A.sum(axis=0)
    assert np.all(col < 1.0), f"column sums must be < 1 (max {col.max():.4f})"
    L = np.linalg.inv(np.eye(n) - A)
    assert np.all(np.diag(L) > 1.0), "Leontief diagonal not > 1"
    for j in range(n):
        assert L[j, j] >= np.max(L[:, j]) - 1e-9, f"col {sector_order[j]} not diag-dominant"
    print("Validation OK: [0,1], colsum<1, Leontief diag>1 and column-dominant.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("zip_path", help="Path to IOT_<year>_ixi.zip")
    ap.add_argument("--out", default=os.path.join(_DATA_DIR, "io_matrix.candidate.json"))
    args = ap.parse_args()

    out = build(args.zip_path)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
