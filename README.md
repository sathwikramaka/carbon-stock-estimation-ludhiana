# Ludhiana Carbon Indicators

Soil organic carbon stock (0–30 cm) and annual net primary production for
Ludhiana District, Punjab, on a 250 m grid — with uncertainty, an independent
cross-check, and a dashboard that serves exactly what the analysis produced.

> **Status: provisional (v1 interim).** The figures below come from the
> existing Earth Engine exports after repairing their known defects
> ([AUDIT.md](AUDIT.md)). Running `notebooks/00_gee_extraction.ipynb` replaces
> them with a census from clean inputs.

## Results

| Quantity | Estimate | Uncertainty |
|---|---|---|
| Soil organic carbon stock, 0–30 cm | **4.549 MtC** | 95% CI 4.546–4.552 (sampling only) |
| Mean SOC density over mapped soil (329,814 ha, a census) | **13.79 tC/ha** | 95% CI 13.78–13.80 |
| MOD17 net primary production, as the product reports | **0.295 MtC/yr** | 95% CI 0.290–0.300 |
| Rice + wheat NPP from reported yields (lower bound) | **3.34 MtC/yr** | 90% range 2.70–4.07 |

- The stock and the flux have different dimensions and are never summed.
- The intervals cover sampling error only. They exclude known biases (unrecorded
  SoilGrids depth interval, no coarse-fragment correction, a grid covering ~95%
  of the district) and SoilGrids' own prediction uncertainty, which is larger.
- MOD17 captures about 9% of the carbon that demonstrably passes through the
  district's crops and reports negative annual NPP in a fifth of agricultural
  cells. It is not fit for crop carbon flux here (AUDIT.md, F4).
- None of this is a carbon-credit quantity: no baseline, additionality,
  permanence or field verification. For cropland soil carbon credits the
  relevant Verra methodology is VM0042 (Improved Agricultural Land Management).

## How the numbers are made

1. **Every cell is kept and keyed by its position.** The 66,700-cell grid is a
   regular lattice; `cell_id = r{row}_c{col}` is unique and reproducible in
   Earth Engine. (The old `Grid_ID` was a random number with 2,155 collisions.)
2. **Soil values are repaired, not modelled.** The original export averaged
   masked SoilGrids pixels as zeros. Bulk density reveals each cell's valid
   fraction *w*; diluted values are divided by *w*, and cells with no valid
   soil are reported as no-data.
3. **District totals come from survey estimators, not a predictive model.** The
   20,000-cell training file passes every balance check for a simple random
   sample of the grid. Bulk density exists for every cell, so the mapped soil
   area is known exactly; the SOC total is the sample's stock density (ratio
   estimator) times that area.
4. **MOD17 is converted per its specification** (DN × 0.0001 kgC/m²) and checked
   against crop yields converted with IPCC (2019) factors.
5. **The map** fills the 46,700 unsampled cells by inverse-distance
   interpolation, checked by cross-validation (SOC R² 0.81). Every value is
   labelled `observed`, `interpolated` or `no soil data`.
6. **Machine learning is reported as a methods result** — random forest under
   spatial-block cross-validation against coordinates-only and mean baselines —
   and produces no published number. On clean data it barely beats position
   alone (SOC R² 0.20 vs 0.17; NPP 0.34 vs 0.32).

## Run it

```bash
python -m venv .venv && .venv\Scripts\activate          # Windows
pip install -r requirements-dev.txt
copy .env.example .env                                   # then edit if using databases
```

| Step | Notebook | Needs | Writes |
|---|---|---|---|
| 0 | `notebooks/00_gee_extraction.ipynb` | Earth Engine project `my-projects-510917` | `IIRS/Carbon_Stocks/v2/` clean inputs |
| 1 | `notebooks/01_data_audit.ipynb` | raw exports | `results/audit_findings.json`, figures |
| 2 | `notebooks/02_carbon_pipeline.ipynb` | raw exports (or v2) | `results/` — every published number |
| 3 (optional) | `notebooks/03_publish_databases.ipynb` | PostgreSQL/PostGIS, MongoDB | database copies of `results/` |

Dashboard (no database needed):

```bash
cd IIRS/Carbon_Stocks/carbon_project/backend
python app.py                      # http://localhost:5000
```

`DB_MODE` in `.env` selects `files` (default, reads `results/`), `local`
(PostgreSQL + MongoDB) or `cloud` (Supabase + Atlas). Database modes fall back
to the files if a database is unreachable, and every response says which
source it used.

Tests: `pytest tests/` (44 tests; those needing `results/carbon_cells.csv` skip
until the pipeline has run).

## Layout

```
config.py                  constants, cell key, soil QC, loaders
estimators.py              survey estimators, interpolation, crop NPP, census totals
notebooks/                 00 extraction · 01 audit · 02 pipeline · 03 publish
results/                   pipeline outputs (the only source the dashboard reads)
IIRS/Carbon_Stocks/        raw Earth Engine exports (v1), boundaries/, and v2/ after re-extraction
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
