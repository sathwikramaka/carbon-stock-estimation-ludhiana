# Archive

History only. Nothing here is used by the current pipeline, and none of these
numbers should be quoted. See `../AUDIT.md` for why each item was superseded.

| Folder | Contents |
|---|---|
| `scripts/` | The five diagnostic/rebuild scripts. Their findings are reproduced in `notebooks/01_data_audit.ipynb`. |
| `docs/` | Old dashboard screenshots, which show retracted figures. The earlier defect ledger and review notes are summarised and superseded by `AUDIT.md`. |
| `notebook_v0/` | The old `carbon_stock_pipeline.ipynb`. Replaced by `notebooks/02_carbon_pipeline.ipynb` and `03_publish_databases.ipynb`. |
| `outputs_v0/` | Every output of the old pipeline: train/test splits, `carbon_all_66790_final.csv`, text reports, plots and, locally only, the `.pkl` models (~450 MB, git-ignored). Built on the diluted soil data, the `Grid_ID` de-duplication and the unscaled MOD17 values. |
| `pre_rebuild_snapshot/` | Local only (git-ignored): copies of files the rebuild overwrote on the author's machine. |
