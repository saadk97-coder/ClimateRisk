#!/usr/bin/env python3
"""
Build the multi-regional (MRIO) direct-requirements matrix for the high-resolution
Layer-3: 20 sectors × 49 EXIOBASE regions = 980×980, from the real EXIOBASE-3 IOT.

Unlike build_io_matrix.py (which sums all regions to one WORLD block), this keeps the
full 49-region structure so cross-region supply chains are explicit. Reuses the same
163→20 sector concordance.

    python scripts/build_io_matrix_mrio.py exio/IOT_2019_ixi.zip

Output (data/transition/):
  io_matrix_mrio.npz        — A (float32, 980×980), compressed
  io_matrix_mrio_meta.json  — sector_order, region_order, provenance
"""

from __future__ import annotations
import argparse
import datetime as _dt
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_io_matrix import _sector_for  # reuse the concordance  # noqa: E402

_DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data", "transition"))


def build(zip_path: str) -> None:
    import pymrio

    clf = pymrio.get_classification("exio3_ixi").sectors
    name_to_code = dict(zip(clf.ExioName, clf.ExioCode))

    io = json.load(open(os.path.join(_DATA_DIR, "io_matrix.json"), encoding="utf-8"))
    sector_order = list(io["_meta"]["sector_order"])

    print(f"Parsing {zip_path} …")
    mrio = pymrio.parse_exiobase3(path=zip_path)
    sectors = list(mrio.get_sectors())
    regions = list(mrio.get_regions())

    sector_agg = [_sector_for(name_to_code.get(s, ""), s) for s in sectors]

    print(f"Aggregating 163→20 sectors, keeping {len(regions)} regions …")
    mrio.aggregate(sector_agg=sector_agg)   # region_agg omitted → keep all regions
    mrio.calc_all()

    A_df = mrio.A  # MultiIndex (region, sector) × (region, sector)
    # reorder sectors within each region to sector_order; region order as-is
    idx = [(r, s) for r in regions for s in sector_order]
    A_df = A_df.reindex(index=idx, columns=idx)
    A = np.nan_to_num(A_df.to_numpy(dtype=np.float64))
    A = np.clip(A, 0.0, None)

    n_sec = len(sector_order)
    raw_colmax = float(A.sum(0).max())
    # Synthesise the two sectors EXIOBASE cannot split, per region block. The twin
    # BUYS like its sibling (column copy — doesn't touch other columns' sums) and the
    # sibling's OUTPUT is SPLIT between the two (row split — preserves column sums, so
    # value added stays positive). alpha = share of combined output assigned to the twin.
    sidx = {s: i for i, s in enumerate(sector_order)}
    alpha = 0.5
    for r_i in range(len(regions)):
        base = r_i * n_sec
        for src, dst in (("road_transport_ice", "road_transport_ev"),
                         ("real_estate_commercial", "real_estate_residential")):
            si, di = base + sidx[src], base + sidx[dst]
            src_row = A[si, :].copy()
            A[:, di] = A[:, si]              # dst buys like src
            A[di, :] = alpha * src_row       # split src's sales …
            A[si, :] = (1.0 - alpha) * src_row  # … between src and dst

    # Numerical hygiene: a few EXIOBASE sectors have ~zero value added (recycling /
    # margin sectors) → column sum ≥ 1. Scale those columns to 0.999 so value added
    # is strictly positive and the Leontief system is well-posed.
    n = A.shape[0]
    csum = A.sum(0)
    n_capped = int((csum >= 1.0).sum())
    scale = np.where(csum >= 1.0, 0.999 / np.clip(csum, 1e-9, None), 1.0)
    A = A * scale  # column-wise
    col_max = A.sum(0).max()
    print(f"max column sum: raw {raw_colmax:.3f} → twin split → capped {col_max:.3f} "
          f"({n_capped} zero-value-added columns scaled)")
    assert col_max < 1.0, f"column sums must be < 1 (max {col_max:.6f})"
    L = np.linalg.inv(np.eye(n) - A)
    assert np.all(np.diag(L) > 1.0 - 1e-9), "Leontief diagonal not > 1"
    print(f"Built {n}×{n} MRIO A. max column sum {col_max:.3f}. Leontief invertible.")

    np.savez_compressed(os.path.join(_DATA_DIR, "io_matrix_mrio.npz"), A=A.astype(np.float32))
    meta = {
        "_meta": {
            "description": "20-sector × 49-region EXIOBASE-3 direct-requirements matrix (MRIO) "
                           "for high-resolution Layer 3. Row/col order = region_order × sector_order.",
            "sources": ["EXIOBASE 3 (Stadler et al. 2018), IOT ixi 2019; DOI 10.5281/zenodo.3583070"],
            "calibration_year": 2019,
            "n_sectors": n_sec, "n_regions": len(regions), "dim": n,
            "sector_order": sector_order,
            "region_order": regions,
            "synthesised_sectors": ["road_transport_ev", "real_estate_residential"],
            "retrieved_utc": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
    }
    with open(os.path.join(_DATA_DIR, "io_matrix_mrio_meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    print("Wrote io_matrix_mrio.npz + io_matrix_mrio_meta.json")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("zip_path")
    build(ap.parse_args().zip_path)


if __name__ == "__main__":
    main()
