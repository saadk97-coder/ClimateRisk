#!/usr/bin/env python3
"""
Refresh data/transition/carbon_prices_ngfs.json from the live NGFS Phase V
Scenario Explorer (IIASA), replacing the Appendix-D placeholder values.

Source
------
NGFS Phase V Scenarios Database, hosted by IIASA:
    https://data.ene.iiasa.ac.at/ngfs/
Accessed anonymously via the `pyam` client (no login required for read).

    pip install pyam-iamc            # optional; not needed to run the engine

What it does
------------
Pulls the `Price|Carbon` variable for one IAM (default REMIND-MAgPIE, the model
the methodology cites), maps NGFS scenario names -> the engine's scenario_ids and
NGFS R5 regions -> the engine's advanced/emerging/rest_of_world buckets, samples
2025..2050 at 5-year steps, and writes the engine's carbon-price schema.

IMPORTANT — units & vintage
---------------------------
NGFS `Price|Carbon` is reported in **US$2010/tCO2**. The existing placeholder file
is labelled USD2020. This script records the *actual* source unit in `_meta` and
does NOT silently convert. Pass --deflator 1.0 to keep raw US$2010, or supply a
GDP-deflator factor (e.g. ~1.15 for 2010->2020) if you want to rebase; the factor
used is written to `_meta` for provenance.

Safety
------
By default writes a SEPARATE file (carbon_prices_ngfs.refreshed.json) so the
calibrated file backing the test suite is left untouched. Pass --inplace only
when you have decided to adopt the refresh (and are ready to re-baseline any
tests that pinned the old numbers).

Usage
-----
    python scripts/fetch_ngfs_prices.py
    python scripts/fetch_ngfs_prices.py --model "GCAM 6.0 NGFS" --deflator 1.15
    python scripts/fetch_ngfs_prices.py --inplace
"""

from __future__ import annotations
import argparse
import datetime as _dt
import json
import os
import sys

# NGFS scenario name (as in the explorer) -> engine scenario_id.
# Scenarios with no Phase-V analog (IEA WEO variants, Divergent Net Zero) are
# left to the existing placeholder and reported as untouched.
_SCENARIO_MAP = {
    "Net Zero 2050": "net_zero_2050",
    "Below 2°C": "below_2c",
    "Delayed transition": "delayed_transition",
    "Fragmented World": "fragmented_world",
    "Nationally Determined Contributions (NDCs)": "ndcs_only",
    "Current Policies": "current_policies",
}

# NGFS R5 region -> engine bucket. The engine collapses the world into three
# carbon-price buckets; this is a documented reduction of the NGFS R5 set.
_REGION_MAP = {
    "OECD & EU (R5)": "advanced",
    "Asia (R5)": "emerging",
    "Middle East & Africa (R5)": "rest_of_world",
}

_YEARS = [2025, 2030, 2035, 2040, 2045, 2050]
_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "transition")
)


def _fetch(model: str):
    try:
        import pyam  # noqa
    except ImportError:
        sys.exit("pyam not installed. Run: pip install pyam-iamc")
    import warnings

    warnings.simplefilter("ignore")
    conn = pyam.iiasa.Connection("ngfs_phase_5")
    df = conn.query(
        model=model,
        variable="Price|Carbon",
        scenario=list(_SCENARIO_MAP.keys()),
        region=list(_REGION_MAP.keys()),
    )
    if df is None or df.data.empty:
        sys.exit(f"No Price|Carbon data returned for model {model!r}.")
    return df.data


def _norm(name: str) -> str:
    """Normalise a scenario name for matching. The IIASA API mangles non-ASCII
    (e.g. 'Below 2°C' comes back as 'Below 2?C'), so collapse to lower-case
    alphanumerics-and-spaces before comparing."""
    return " ".join("".join(c if c.isalnum() else " " for c in name).lower().split())


def _interp(series: dict, year: int) -> float:
    """Linear interpolation over available (year -> value) points."""
    if year in series:
        return series[year]
    ys = sorted(series)
    if year <= ys[0]:
        return series[ys[0]]
    if year >= ys[-1]:
        return series[ys[-1]]
    lo = max(y for y in ys if y <= year)
    hi = min(y for y in ys if y >= year)
    frac = (year - lo) / (hi - lo)
    return series[lo] + frac * (series[hi] - series[lo])


def build(model: str, deflator: float) -> dict:
    data = _fetch(model)
    unit = sorted(data.unit.unique())[0]

    # Preserve the mapping blocks (ipcc_fallback_map, region_classification)
    # from the existing file — those are ISO3 groupings, not prices.
    existing_path = os.path.join(_DATA_DIR, "carbon_prices_ngfs.json")
    existing = {}
    if os.path.exists(existing_path):
        with open(existing_path, encoding="utf-8") as fh:
            existing = json.load(fh)

    # Normalised lookup so degree-symbol mangling ('Below 2°C' -> 'Below 2?C')
    # does not drop scenarios.
    returned = {_norm(s): s for s in data.scenario.unique()}

    scenarios: dict = {}
    for ngfs_name, sid in _SCENARIO_MAP.items():
        label = existing.get("scenarios", {}).get(sid, {}).get("label", ngfs_name)
        entry = {"label": label}
        actual = returned.get(_norm(ngfs_name))
        if actual is None:
            continue
        sub = data[data.scenario == actual]
        if sub.empty:
            continue
        for region, bucket in _REGION_MAP.items():
            pts = sub[sub.region == region]
            if pts.empty:
                continue
            raw = {int(r.year): float(r.value) for _, r in pts.iterrows()}
            entry[bucket] = {
                str(y): round(_interp(raw, y) * deflator, 1) for y in _YEARS
            }
        scenarios[sid] = entry

    # Carry forward scenarios with no Phase-V source (IEA, divergent_net_zero).
    untouched = []
    for sid, block in existing.get("scenarios", {}).items():
        if sid not in scenarios:
            scenarios[sid] = block
            untouched.append(sid)

    out = {
        "_meta": {
            "description": (
                "NGFS Phase V carbon prices (Price|Carbon) pulled live from the "
                "IIASA NGFS Phase 5 Scenario Explorer."
            ),
            "model": model,
            "source_unit": unit,
            "deflator_applied": deflator,
            "reported_unit": (
                unit if deflator == 1.0 else f"{unit} x {deflator} (rebased)"
            ),
            "region_mapping": _REGION_MAP,
            "scenario_mapping": _SCENARIO_MAP,
            "scenarios_from_placeholder_no_phase5_source": untouched,
            "retrieved_utc": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "source_url": "https://data.ene.iiasa.ac.at/ngfs/",
        },
        "scenarios": scenarios,
        "ipcc_fallback_map": existing.get("ipcc_fallback_map", {}),
        "region_classification": existing.get("region_classification", {}),
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="REMIND-MAgPIE 3.3-4.8")
    ap.add_argument(
        "--deflator",
        type=float,
        default=1.0,
        help="Multiply raw US$2010 prices by this factor (e.g. 1.15 for USD2020).",
    )
    ap.add_argument(
        "--inplace",
        action="store_true",
        help="Overwrite carbon_prices_ngfs.json instead of writing .refreshed.json",
    )
    args = ap.parse_args()

    out = build(args.model, args.deflator)
    name = "carbon_prices_ngfs.json" if args.inplace else "carbon_prices_ngfs.refreshed.json"
    dest = os.path.join(_DATA_DIR, name)
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    print(f"Wrote {dest}")
    print(f"  model            : {out['_meta']['model']}")
    print(f"  source unit      : {out['_meta']['source_unit']}")
    print(f"  scenarios pulled : {[s for s in out['scenarios'] if s not in out['_meta']['scenarios_from_placeholder_no_phase5_source']]}")
    print(f"  kept placeholder : {out['_meta']['scenarios_from_placeholder_no_phase5_source']}")


if __name__ == "__main__":
    main()
