# Ludhiana Carbon Indicators

Soil organic carbon stock (0–30 cm) and annual net primary production for
Ludhiana District, Punjab, on a 250 m grid — with uncertainty, an independent
cross-check, and a dashboard that serves exactly what the analysis produced.

> **Status: census (v2).** Every figure below comes from a fresh Earth Engine
> extraction (`notebooks/00_gee_extraction.ipynb`, project `my-projects-510917`,
> run 2026-10-07) of all 71,197 lattice cells touching the district, weighted by
> each cell's share inside the geoBoundaries ADM2 polygon. The v1 exports are
> kept for the audit ([AUDIT.md](AUDIT.md)).

## Results

| Quantity | Estimate | Check |
|---|---|---|
| Soil organic carbon stock, 0–30 cm (SoilGrids `ocs`) | **10.54 MtC** | 10.18 MtC inside the Census 2011 (Datameet) boundary; 10.12 MtC from the repaired v1 sample |
| Mean SOC density over valid soil (342,426 ha) | **30.77 tC/ha** | v1 sample 30.68 tC/ha |
| MOD17 net primary production 2024, as the product reports | **0.335 MtC/yr** | 0.95 tC/ha/yr over 351,622 ha |
| Rice + wheat NPP from reported yields (lower bound) | **3.34 MtC/yr** | 90% range 2.70–4.07 |

- **The soil stock is 2.3× the previously reported 4.4–4.5 MtC.** The v1 column
  `SOC_mean` was SoilGrids `ocs` — a 0–30 cm carbon *stock* in t/ha — but every
  earlier version read it as carbon *content* and multiplied it by bulk density
  and depth again (AUDIT.md, F14).
- Rebuilding the stock from SoilGrids SOC × BD × 30 cm × (1 − coarse fraction)
  gives 14.46 MtC. SoilGrids models `ocs` directly, and the two disagree by a
  median factor of 1.35 here; the headline uses `ocs`, the product's own stock
  prediction, and the gap is a measure of model uncertainty that no interval
  above includes.
- The stock and the flux have different dimensions and are never summed.
- MOD17 captures about 10% of the carbon that demonstrably passes through the
  district's crops. It is not fit for crop carbon flux here (AUDIT.md, F4).
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
   are recorded in `IIRS/Carbon_Stocks/v2/manifest.json`.
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

## Run it

```bash
python -m venv .venv && .venv\Scripts\activate          # Windows
pip install -r requirements-dev.txt
copy .env.example .env                                   # then edit if using databases
```

| Step | Notebook | Needs | Writes |
|---|---|---|---|
| 0 | `notebooks/00_gee_extraction.ipynb` | Earth Engine project `my-projects-510917` | `IIRS/Carbon_Stocks/v2/ludhiana_cells_v2.csv.gz` (committed) |
| 1 | `notebooks/01_data_audit.ipynb` | raw exports | `results/audit_findings.json`, figures |
| 2 | `notebooks/02_carbon_pipeline.ipynb` | v2 table (falls back to v1 exports) | `results/` — every published number |
| 3 (optional) | `notebooks/03_publish_databases.ipynb` | PostgreSQL/PostGIS, MongoDB | database copies of `results/` |
| 4 | `notebooks/04_location_map.ipynb` | internet (first run) | `boundaries/punjab_*`, `results/fig_location.png` |
| 5 | `notebooks/05_soilgrids_uncertainty.ipynb` | `maps.isric.org` reachable, or the four GeoTIFFs it lists | `results/soilgrids_uncertainty.json` (re-run 02 after) |

Dashboard (no database needed):

```bash
cd IIRS/Carbon_Stocks/carbon_project/backend
python app.py                      # http://localhost:5000
```

`DB_MODE` in `.env` selects `files` (default, reads `results/`), `local`
(PostgreSQL + MongoDB) or `cloud` (Supabase + Atlas). Database modes fall back
to the files if a database is unreachable, and every response says which
source it used.

Tests: `pytest tests/` (46 tests; those needing `results/carbon_cells.csv` skip
until the pipeline has run).

## Layout

```
config.py                  constants, cell key, soil QC, loaders
estimators.py              survey estimators, interpolation, crop NPP, census totals
notebooks/                 00 extraction · 01 audit · 02 pipeline · 03 publish · 04 map · 05 uncertainty
results/                   pipeline outputs (the only source the dashboard reads)
IIRS/Carbon_Stocks/        raw Earth Engine exports (v1), boundaries/, v2/ census inputs
IIRS/Carbon_Stocks/carbon_project/   Flask backend + Leaflet/Chart.js frontend
tests/                     invariants for keys, units, QC, estimators, results, API
docs/DATA_DICTIONARY.md    every column, its unit and provenance
AUDIT.md                   every defect found, evidence, fix, status
project_report.md          the written report
archive/                   superseded scripts, documents and outputs (history only)
```

## Data sources

ISRIC SoilGrids 2.0 · MODIS MOD17A3HGF v6.1 · SRTM · Sentinel-2 (v2 NDVI) ·
ESA WorldCover 2021 (v2) · basemaps © Esri, © OpenStreetMap contributors, © CARTO · district crop statistics as reported by the Ludhiana
agriculture department · IPCC (2019) Refinement, Vol. 4, Table 11.1a.
