# Ludhiana Carbon Indicators

Soil organic carbon stock (0–30 cm) and annual net primary production for
Ludhiana District, Punjab, on a 250 m grid — with uncertainty, an independent
cross-check, and a dashboard that serves exactly what the analysis produced.

> **Status: census (v2).** Every figure below comes from a fresh Earth Engine
> extraction (`notebooks/00_gee_extraction.ipynb`, project `my-projects-510917`,
> run 2026-10-07) of all 71,197 lattice cells touching the district, weighted by
> each cell's share inside the geoBoundaries ADM2 polygon. The v1 exports are
> kept for the audit ([AUDIT](docs/AUDIT.md)).

## Results

| Quantity | Estimate | Check |
|---|---|---|
| Soil organic carbon stock, 0–30 cm (SoilGrids `ocs`) | **10.54 MtC** | 10.18 MtC inside the Census 2011 (Datameet) boundary; 10.12 MtC from the repaired v1 sample |
| Mean SOC density over valid soil (342,426 ha) | **30.77 tC/ha** | v1 sample 30.68 tC/ha |
| SoilGrids' own 90% interval for the stock (errors fully correlated) | **2.2–27.7 MtC** | per cell 7–82 t/ha around a mean of 31 |
| MOD17 net primary production 2024, as the product reports | **0.335 MtC/yr** | 0.95 tC/ha/yr over 351,622 ha |
| Rice + wheat NPP from reported yields (lower bound) | **3.34 MtC/yr** | 90% range 2.70–4.07 |

- **The soil stock is 2.3× the previously reported 4.4–4.5 MtC.** The v1 column
  `SOC_mean` was SoilGrids `ocs` — a 0–30 cm carbon *stock* in t/ha — but every
  earlier version read it as carbon *content* and multiplied it by bulk density
  and depth again (docs/AUDIT.md, F14).
- Rebuilding the stock from SoilGrids SOC × BD × 30 cm × (1 − coarse fraction)
  gives 14.46 MtC. SoilGrids models `ocs` directly, and the two disagree by a
  median factor of 1.35 here; the headline uses `ocs`, the product's own stock
  prediction, and the gap is a measure of model uncertainty that no interval
  above includes.
- **The stock is known only to within a factor of ~10.** SoilGrids' published
  90% prediction interval for `ocs` is about 7–82 t/ha per cell. Summed with
  fully correlated errors (the realistic case for a model's errors across one
  district) that gives 2.2–27.7 MtC. Assuming independent errors would give
  ±0.05 MtC, which is false precision. Field samples are the only way to narrow it.
- The stock and the flux have different dimensions and are never summed.
- MOD17 captures about 10% of the carbon that demonstrably passes through the
  district's crops. It is not fit for crop carbon flux here (docs/AUDIT.md, F4).
- None of this is a carbon-credit quantity: no baseline, additionality,
  permanence or field verification. For cropland soil carbon credits the
  relevant Verra methodology is VM0042 (Improved Agricultural Land Management).

## How the numbers are made

1. **Every cell is kept and keyed by its position.** The grid is a regular
   lattice; `cell_id = r{row}_c{col}` is unique and reproducible in Earth
   Engine. (The old `Grid_ID` was a random number with 2,155 collisions.)
2. **Clean inputs from Earth Engine (v2).** SoilGrids 2.0 is reduced over
   unmasked pixels only, with a valid-soil fraction per cell; 0–30 cm values are
   thickness-weighted; MOD17A3HGF 2024 is scaled per its specification; ESA
   WorldCover, SRTM and monthly Sentinel-2 NDVI come with it. A validation cell
   refuses to write the table if any physical check fails. Inputs and settings
   are recorded in `data/v2/manifest.json`.
3. **Totals are a census, clipped to the district.** Stock = Σ `ocs` × valid
   fraction × area inside the boundary. Two boundaries are carried
   (geoBoundaries ADM2 headline, Census 2011 check), so the boundary choice is
   visible as a sensitivity.
4. **MOD17 is checked** against crop yields converted with IPCC (2019) factors.
5. **The v1 path still runs** (`02_carbon_pipeline.ipynb` falls back to it if the
   v2 table is absent): diluted soil values are repaired by the valid fraction
   *w* from bulk density, totals come from survey estimators on the 20,000-cell
   random sample, and the map is filled by inverse-distance interpolation
   (ocs R² 0.81 under cross-validation). It reproduces the census to within 4%.
6. **Machine learning is reported as a methods result only.** On repaired v1
   data a random forest barely beats position alone (ocs R² 0.20 vs 0.17;
   NPP 0.34 vs 0.32) and produces no published number.

## Public app

A Streamlit version of the results (`app/streamlit_app.py`) is deployed on
Streamlit Community Cloud. It reads only `results/` and the boundaries, so it
always shows the last pipeline run. Run it locally with:

```bash
pip install -r app/requirements.txt
streamlit run app/streamlit_app.py
```

The Flask dashboard in `dashboard/` remains the local version with the
PostgreSQL/MongoDB modes used in notebook 03.

## Run it

```bash
python -m venv .venv && .venv\Scripts\activate          # Windows
pip install -r requirements-dev.txt
copy .env.example .env                                   # then edit if using databases
```

| Step | Notebook | Needs | Writes |
|---|---|---|---|
| 0 | `notebooks/00_gee_extraction.ipynb` | Earth Engine project `my-projects-510917` | `data/v2/ludhiana_cells_v2.csv.gz` (committed) |
| 1 | `notebooks/01_data_audit.ipynb` | raw exports | `results/audit_findings.json`, figures |
| 2 | `notebooks/02_carbon_pipeline.ipynb` | v2 table (falls back to v1 exports) | `results/` — every published number |
| 3 (optional) | `notebooks/03_publish_databases.ipynb` | PostgreSQL 16 + PostGIS, MongoDB (either alone works) | loads `results/` into both, verifies totals, PostGIS spatial-join and MongoDB aggregation examples; enables `DB_MODE=local` |
| 4 | `notebooks/04_location_map.ipynb` | internet (first run) | `boundaries/punjab_*`, `results/fig_location.png` |
| 5 | `notebooks/05_soilgrids_uncertainty.ipynb` | `maps.isric.org` reachable, or the four GeoTIFFs it lists | `results/soilgrids_uncertainty.json` (re-run 02 after) |
| 6 | `notebooks/06_shc_validation.ipynb` | Soil Health Card table from Dataful in `data/raw/` (sign-in; not committed) | `results/shc_validation.json`: SoilGrids vs lab organic carbon at the same cells |

Dashboard (no database needed):

```bash
cd dashboard/backend
python app.py                      # http://localhost:5000
```

On Windows you can double-click `dashboard/run_dashboard.bat` instead.

`DB_MODE` in `.env` selects `files` (default, reads `results/`), `local`
(PostgreSQL + MongoDB) or `cloud` (Supabase + Atlas). Database modes fall back
to the files if a database is unreachable, and every response says which
source it used.

Tests: `pytest tests/` (49 tests; those needing `results/carbon_cells.csv` skip
until the pipeline has run).

## Layout

```
config.py, estimators.py   constants, cell key, soil QC, loaders; survey estimators, census totals
notebooks/                 00 extraction · 01 audit · 02 pipeline · 03 databases · 04 map · 05 uncertainty · 06 soil-test check
data/raw/                  v1 Earth Engine exports, as received (read-only)
data/boundaries/           district and state boundaries (geoBoundaries, Datameet)
data/v2/                   v2 census table + manifest (per-layer CSVs and chunks are git-ignored)
data/soilgrids_quantiles/  SoilGrids ocs quantile GeoTIFFs (native Homolosine)
results/                   pipeline outputs: the only source the dashboard reads
app/                       public Streamlit app (Community Cloud)
dashboard/                 Flask backend + Leaflet/Chart.js frontend (local, database modes)
tests/                     invariants for keys, units, QC, estimators, results, API
docs/                      AUDIT.md (defects, evidence, fixes) · REPORT.md · DATA_DICTIONARY.md
archive/                   superseded scripts, documents and outputs (history only)
```

## Data sources

ISRIC SoilGrids 2.0 · MODIS MOD17A3HGF v6.1 · SRTM · Sentinel-2 (v2 NDVI) ·
ESA WorldCover 2021 (v2) · basemaps © Esri, © OpenStreetMap contributors, © CARTO · district crop statistics as reported by the Ludhiana
agriculture department · IPCC (2019) Refinement, Vol. 4, Table 11.1a.
