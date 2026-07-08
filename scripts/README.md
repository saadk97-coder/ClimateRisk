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

## Not yet automatable

- **`io_matrix.json` (EXIOBASE-3).** Data is public (Zenodo, `pymrio`), but
  `sector_taxonomy.json` supplies only one anchor EXIOBASE code per aggregated
  sector — a faithful 200→20 concordance still has to be authored by hand. Left
  as a reviewed task rather than a blind pull.
- **`cc_exposure_proxy.json` (Sautner CCExposure).** The public OSF file carries
  ISIN/GVKEY/CUSIP but **no sector column**; binning firms into the 20-sector
  taxonomy needs GVKEY→GICS, which requires an S&P/Compustat licence. No sound
  license-free rebuild — the calibrated sector-median proxy is retained.
