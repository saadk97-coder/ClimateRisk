# Data-refresh scripts

Tooling to refresh the provisional transition-risk data contracts from their real
sources. None of these are needed to run the engine or the test suite — the
committed JSON files are self-contained.

## `fetch_ngfs_prices.py` — carbon prices (READY, license-free)

Pulls `Price|Carbon` live from the IIASA NGFS Phase 5 Scenario Explorer
(anonymous read, no login) and writes the engine's carbon-price schema.

```bash
pip install pyam-iamc
python scripts/fetch_ngfs_prices.py            # writes carbon_prices_ngfs.refreshed.json (safe)
python scripts/fetch_ngfs_prices.py --inplace  # overwrite the calibrated file (adopt)
```

- Default writes a **separate** `carbon_prices_ngfs.refreshed.json` so the
  calibrated file backing the tests is untouched. Verified: adopting the refresh
  keeps all transition tests green.
- Pulls 6 scenarios (net_zero_2050, below_2c, delayed_transition, fragmented_world,
  ndcs_only, current_policies). `divergent_net_zero` and the three IEA scenarios
  have no NGFS Phase-V analog and keep their placeholder values.
- **Units:** NGFS reports `US$2010/tCO2`. The script records this in `_meta` and
  does not silently convert; pass `--deflator 1.15` to rebase to ~USD2020.
- Real prices are materially higher than the Appendix-D placeholders
  (e.g. Net Zero 2050 advanced 2050: 410 → 870), so adopting changes reported
  DCF/OpEx dollars. Adopt deliberately.

## `build_io_matrix.py` — I-O matrix (CANDIDATE, license-free)

Builds a 20-sector world direct-requirements matrix from the real EXIOBASE-3
industry-by-industry MRIO (all 49 regions summed to WORLD totals), via `pymrio`
(public Zenodo download, no login).

```bash
pip install pymrio
python -c "import pymrio; pymrio.download_exiobase3(storage_folder='exio', years=[2019], system='ixi')"
python scripts/build_io_matrix.py exio/IOT_2019_ixi.zip
```

- Writes `io_matrix.candidate.json` for review. The current `io_matrix.json` has
  **already been adopted** from this builder (EXIOBASE-3 2019 WORLD totals); re-run
  to refresh and diff before re-adopting.
- Verified: the adopted matrix keeps all transition tests green
  (structurally valid: entries in [0,1], column sums < 1, Leontief diagonal > 1
  and column-dominant).
- The 163→20 concordance embeds judgement calls (electricity T&D → power_renewable;
  fuel extraction → oil_upstream; non-Al non-ferrous metals & construction →
  manufacturing_general; transport/finance/waste/public services → services).
  EXIOBASE cannot split ICE/EV vehicles or commercial/residential real estate, so
  those two twin sectors are copied from their sibling (flagged in `_meta`).
  **Review the concordance before adopting.**

## Not yet automatable

- **`cc_exposure_proxy.json` (Sautner CCExposure).** The public OSF file carries
  ISIN/GVKEY/CUSIP but **no sector column**; binning firms into the 20-sector
  taxonomy needs GVKEY→GICS, which requires an S&P/Compustat licence. No sound
  license-free rebuild — the calibrated sector-median proxy is retained.
