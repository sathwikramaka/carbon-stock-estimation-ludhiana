# Carbon Stock Estimation — Ludhiana District, Punjab

Grid-based estimation of soil organic carbon and above-ground carbon
assimilation across Ludhiana District using SoilGrids soil data, MODIS
satellite productivity, Sentinel-2 vegetation indices and Random Forest
regression at 250 m resolution — with a Flask API, PostGIS spatial database,
MongoDB document store, and an interactive dashboard.

Academic project, Indian Institute of Remote Sensing (IIRS) — Big Data
Analytics.

**[Open the live dashboard](https://carbon-stock-estimation-ludhiana.streamlit.app/)**

---

## Results

| Quantity | Value |
|---|---|
| **Soil organic carbon stock (0–30 cm)** | **10.54 MtC** |
| CO₂ equivalent | 38.6 Mt CO₂e |
| Mean soil carbon density | 30.77 tC/ha (over 342,426 ha of mapped soil) |
| SoilGrids 90% prediction interval for the stock | 2.2–27.7 MtC |
| Annual above-ground carbon assimilation (MODIS NPP, 2024) | 0.335 MtC/yr |
| MODIS NPP, 2020–2024 mean (range of years) | 0.402 MtC/yr (0.298–0.576) |
| Crop-yield check: rice + wheat NPP (lower bound) | 3.34 MtC/yr (90% range 2.70–4.07) |
| Crop light-use-efficiency NPP (Sentinel-2 fAPAR × ERA5 PAR) | 3.89 MtC/yr (90% range 2.79–5.07) |
| Grid cells analysed | 71,197 |
| Grid resolution | 250 m × 250 m nominal (5.35 ha per cell at this latitude) |
| Grid area inside the district boundary | 369,961 ha |
| Stock inside the Census 2011 boundary | 10.18 MtC |

| Land class | Cells | Soil carbon stock | Density |
|---|---|---|---|
| Agricultural | 60,257 | 9.56 MtC | 30.9 tC/ha |
| Non-agricultural | 10,940 | 0.97 MtC | 29.5 tC/ha |

**The two carbon figures are reported separately and are not summed.** Soil
organic carbon is a *stock*, accumulated over decades and measured in tonnes.
Net primary productivity is a *flux*, describing carbon fixed in one year and
measured in tonnes per year. Adding them would combine different units and
different time dimensions. In an annual cropping system the distinction matters
particularly, since above-ground biomass is harvested each season and standing
above-ground carbon is close to zero for most of the year.

**Uncertainty.** The soil stock is a census of SoilGrids' own 0–30 cm stock
layer. SoilGrids publishes a 90% prediction interval of roughly 7–82 t/ha per
cell; summed with fully correlated errors (the realistic case for one model
across one district) that gives 2.2–27.7 MtC. Rebuilding the stock from
SoilGrids' SOC × bulk density × depth layers gives 14.46 MtC. Field samples are
the only way to narrow these ranges (see *Further work*).

**MODIS NPP and crops.** Two independent estimates agree: reported rice and
wheat yields, converted with IPCC (2019) factors, put at least 3.34 MtC/yr
through the district's two main crops, and a crop light-use-efficiency model
(Monteith 1972) driven by Sentinel-2 fAPAR and ERA5-Land radiation gives
3.89 MtC/yr (2.79–5.07) — 1.16× the yield lower bound, as expected for a total
that also counts carbon the harvest does not. MOD17 reports about 9–10% of
either. MOD17 is therefore reported as the product gives it, and the
crop-based estimates are the better guide to crop carbon flux.

---

## Model performance

All models are **quantile regression forests** (Meinshausen 2006), validated with
**5-fold spatial block cross-validation** over an 8 × 8 grid of geographic
blocks so that no test cell has a training neighbour, and compared with gradient
boosting and two baselines.

| Model | Random Forest R² | Gradient boosting R² | Coordinates-only R² | Training-mean R² | RF RMSE | 90% interval coverage |
|---|---|---|---|---|---|---|
| Above-ground (NPP 2020–24 mean, gC/m²/yr) | **0.550** | 0.529 | 0.392 | −0.021 | 41.5 | 92.8% |
| Below-ground (SOC, t/ha) | **0.451** | 0.435 | 0.224 | −0.016 | 1.40 | 89.0% |

Training sample: 20,000 cells with complete data. Predictors (169): elevation,
slope, ESA WorldCover fractions, twelve monthly Sentinel-2 NDVI composites and
six NDVI seasonal statistics, Sentinel-1 VV/VH backscatter and Landsat 8/9
land-surface temperature for kharif and rabi — each also as its mean over 0.7,
2, 5 and 9 km neighbourhoods — plus coordinates. None is derived from the
targets, so the R² measures real predictive skill. The 90% prediction intervals
cover close to 90% of held-out cells, so they are well calibrated.

**What raised accuracy** (gradient boosting, same folds):

| Feature set | NPP R² | SOC R² |
|---|---|---|
| Cell covariates (terrain, land cover, NDVI) | 0.434 | 0.245 |
| + NDVI seasonal statistics | 0.433 | 0.248 |
| + Sentinel-1 radar and Landsat LST | 0.446 | 0.256 |
| + neighbourhood means (0.7–9 km) | 0.534 | 0.435 |
| + coordinates (final model) | 0.529 | 0.435 |
| NPP: 2024-only target instead of 2020–24 mean | 0.489 | — |
| SOC: + SoilGrids texture/BD layers (same product) | — | 0.461 |

- **Neighbourhood context** is the main gain: both targets are gridded model
  outputs built at coarser support (MOD17 at 500 m with coarse meteorology,
  SoilGrids from 250 m–1 km covariates).
- **Averaging MOD17 over 2020–2024** removes single-year noise (+0.04 R²);
  district MOD17 NPP ranged 0.30–0.58 MtC/yr between those years.
- **Radar and thermal data** add about 0.01 — little beyond NDVI here.

**Block-size sensitivity.** R² depends on how far the model must extrapolate:

| Spatial blocks | NPP R² | SOC R² |
|---|---|---|
| 4 × 4 (~25 km) | 0.509 | 0.325 |
| 8 × 8 (~12 km, reported) | 0.529 | 0.435 |
| 16 × 16 (~6 km) | 0.559 | 0.529 |

> **A note on the R².** SOC varies little across the district (standard
> deviation 1.9 t/ha around 31 t/ha) against SoilGrids' own per-cell
> uncertainty of roughly 7–82 t/ha, so a higher R² against SoilGrids would
> mostly reproduce the product, not the soil. Accuracy against measured soil
> carbon needs field data: `06_shc_validation.ipynb` validates SoilGrids against
> Soil Health Card lab tests and builds a soil-test-calibrated map by regression
> kriging. The district totals do not depend on any model.

Top permutation importances (per covariate, all scales): NPP — coordinates
0.19, kharif VV backscatter 0.04, October NDVI 0.03; SOC — coordinates 0.06,
mean NDVI 0.05, November NDVI 0.05, elevation 0.03.

---

## Method

### Data sources

| Layer | Source | Resolution | Role |
|---|---|---|---|
| Soil organic carbon stock 0–30 cm (`ocs`) | ISRIC SoilGrids 2.0 | 250 m | SOC stock |
| SOC, bulk density, sand, clay, coarse fragments | SoilGrids 2.0 | 250 m | stock sensitivity; model comparison |
| Net primary productivity | MODIS MOD17A3HGF v6.1, 2020–2024 | 500 m | above-ground flux; model target |
| Radar backscatter VV, VH | Sentinel-1 GRD, kharif and rabi medians | 10 m | predictors |
| Land-surface temperature | Landsat 8/9 Collection 2, kharif, rabi, annual medians | 30 m (100 m TIRS) | predictors |
| Photosynthetically active radiation | ERA5-Land monthly | ~11 km | crop light-use-efficiency NPP |
| NDVI, 12 monthly composites | Sentinel-2 SR, Jun 2024 – May 2025 | 10 m | predictors |
| Land cover fractions | ESA WorldCover 2021 | 10 m | predictors, land class |
| Elevation, slope | SRTM | 30 m | predictors |
| Uncertainty quantiles of `ocs` | SoilGrids 2.0 (ISRIC WCS) | 250 m | 90% interval |
| District boundary | geoBoundaries ADM2; Census 2011 (Datameet) | — | grid extent |
| Crop area and yield | Ludhiana agriculture department | district | NPP check |

All layers are extracted through Google Earth Engine (project
`my-projects-510917`) for every 250 m lattice cell that touches the district,
with masked pixels excluded before averaging and the valid fraction of each
cell recorded.

### Carbon equations

```
SOC stock (tC)        = SoilGrids ocs 0–30 cm (t/ha of valid soil) × valid-soil fraction × cell area (ha)
Sensitivity (tC/ha)   = SOC (g/kg) × bulk density (g/cm³) × 30 cm × (1 − coarse fraction) / 10
NPP flux (tC/ha/yr)   = MOD17 DN × 0.0001 kgC/m² × 10 = DN / 1000
CO₂e                  = carbon × 44/12
```

SoilGrids `ocs` is the product's own stock prediction and already accounts for
bulk density and coarse fragments. MODIS NPP is reported directly as carbon, so
no biomass-to-carbon factor is applied. Cell areas are geodesic (WGS84).

### Modelling

Quantile regression forests (300 trees, minimum leaf 5, a third of features
per split, random state 42) predict SOC stock and multi-year NPP from terrain,
land cover, Sentinel-2 NDVI, Sentinel-1 radar and Landsat LST with multi-scale
neighbourhood means and coordinates, and give a 90% prediction interval for
every cell. District totals
are a census of every cell; the models quantify how much of the spatial pattern
the satellite covariates explain.

---

## Validation

### 1. Unit verification

Every input was checked against its product specification and against
physical ranges (`IIRS/Scrpit/01_data_quality.ipynb`). MOD17 NPP is stored as
an integer DN with scale 0.0001 kgC/m², and is converted accordingly. The soil
column `SOC_mean` in the sample export matches SoilGrids `ocs_0-30cm_mean` — a
stock in t/ha — with r = 0.96 and a median ratio of 1.00, so it is used as a
stock, not as a concentration.

### 2. Soil data quality

Where masked SoilGrids pixels enter a cell average as zeros, every soil band
in that cell is scaled by the cell's valid fraction *w*, which creates
artificial positive correlations between bands (sand × clay +0.84, bulk
density × SOC +0.97). The census extraction masks before averaging and records
*w* per cell; on the 62,244 fully valid cells the relationships take their
physical signs (sand × clay −0.70, bulk density × SOC −0.35), and models are
trained only on fully valid cells.

### 3. Spatial cross-validation

A random split places adjacent 250 m cells — and cells sharing one 500 m MODIS
pixel — in both training and test sets, which inflates scores. All reported
skill uses spatial block cross-validation; permutation importance is measured
on the held-out folds.

### 4. Separation of flux from stock

The annual NPP flux and the SOC stock are reported separately, as explained
above.

### 5. Independent checks

- **Boundary:** the stock is computed inside two independent district
  polygons (10.54 vs 10.18 MtC).
- **Stock route:** `ocs` vs SOC × BD × depth (10.54 vs 14.46 MtC).
- **SoilGrids uncertainty:** 5%/50%/95% quantiles fetched on SoilGrids' native
  grid (`05_soilgrids_uncertainty.ipynb`).
- **Crop yields:** MOD17 against an IPCC-factor lower bound from reported
  yields, propagated by Monte Carlo (20,000 draws).
- **Crop light-use efficiency:** Monteith model with Sentinel-2 fAPAR and
  ERA5-Land PAR, 3.89 MtC/yr, against the yield-based 3.34 MtC/yr lower bound.
- **Soil Health Card:** `06_shc_validation.ipynb` compares SoilGrids with
  laboratory organic carbon at the same cells (Walkley–Black × 1.32) and builds
  a regression-kriging map from the tests; verified end to end on synthetic
  soil tests, waiting for the real table.

### Coordinate proxy analysis

Each candidate predictor was tested by fitting it from longitude and latitude
alone. Four interpolated climate layers proved almost perfectly reconstructible
from position:

| Feature | R² from coordinates alone |
|---|---|
| Kharif_Pre (kharif rainfall) | 0.9999 |
| LST_Sept20 | 0.9999 |
| Rabi_Preci (rabi rainfall) | 0.9999 |
| Rabi_LST_2 | 0.9809 |

These are smooth surfaces from products much coarser than the 250 m grid; at
this scale they encode *where* a cell is, not local conditions, and the
district's agriculture depends on irrigation rather than rainfall. They are
excluded from the models, and every model is compared with a coordinates-only
baseline so that position effects are visible.

---

## Limitations

1. **No field measurements.** SOC values are SoilGrids predictions; their
   accuracy in Ludhiana is unknown until checked against soil samples. The
   product's own 90% interval for the district is 2.2–27.7 MtC.
2. **Two routes to a stock.** SoilGrids' `ocs` layer and its SOC × bulk density
   layers differ by a median factor of 1.35 here.
3. **Depth restriction.** The estimate covers 0–30 cm only, following the IPCC
   Tier 1 convention; total profile carbon is higher.
4. **Boundary.** The headline uses geoBoundaries ADM2 (369,961 ha), 1.8% below
   the Census 2011 area of 376,700 ha. Neither is an official Survey of India
   boundary.
5. **NPP product.** MOD17 captures about 10% of the carbon that passes through
   the district's crops; it is not suitable for crop carbon flux here. The
   yield-based estimate covers rice and wheat only and is a lower bound.
6. **Above-ground pool is a flux.** A standing above-ground biomass stock would
   need allometry, canopy height or a dedicated biomass product (GEDI, ESA CCI
   Biomass).
7. **Model skill is moderate.** Satellite covariates explain 55% of NPP
   variation and 45% of SOC variation under spatial validation, less when the
   model must extrapolate further (4 × 4 blocks: 0.51 and 0.33).
8. **Not a carbon-credit quantity.** No baseline, additionality, permanence or
   field verification; for cropland soil carbon credits the relevant Verra
   methodology is VM0042, which requires soil sampling.

---

## Stack

**Analysis** — Python, scikit-learn, pandas, Google Earth Engine
**Databases** — PostgreSQL + PostGIS (geometry), MongoDB (results)
**Backend** — Flask, psycopg2, pymongo
**Frontend** — Leaflet, Chart.js
**Public app** — Streamlit Community Cloud

---

## Repository layout

```
IIRS/
  Carbon_Stocks/
    carbon_project/
      backend/          Flask API (app.py)
      frontend/         dashboard (templates/index.html, static/main.js)
      run_dashboard.bat Windows launcher
    boundaries/         district and state boundaries
    v2/                 Earth Engine census table + manifest
    soilgrids_quantiles/ SoilGrids ocs uncertainty layers
    results/            pipeline outputs: the only source the dashboard reads
    *.csv               Earth Engine sample exports
  Scrpit/
    00_gee_extraction.ipynb        Earth Engine extraction (every cell)
    01_data_quality.ipynb          unit and data-quality checks
    02_carbon_pipeline.ipynb       carbon totals, Random Forest models, results
    03_publish_databases.ipynb     PostGIS + MongoDB loading and spatial queries
    04_location_map.ipynb          location map
    05_soilgrids_uncertainty.ipynb SoilGrids 90% interval
    06_shc_validation.ipynb        Soil Health Card validation + regression kriging
    07_gee_extra_covariates.ipynb  Sentinel-1, Landsat LST, ERA5 PAR, MOD17 2020-2024
app/streamlit_app.py      public dashboard (same frontend, no server needed)
config.py, estimators.py  constants, cell key, loaders; estimators
docs/                     data dictionary, screenshots
tests/                    checks on keys, units, results and the API
project_report.md         full project report
```

---

## Running it

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements-dev.txt
copy .env.example .env          # then edit if using databases
```

Run the notebooks in `IIRS/Scrpit/` in order (00 needs Earth Engine access;
02 writes every published number to `IIRS/Carbon_Stocks/results/`), then:

```bash
cd IIRS/Carbon_Stocks/carbon_project/backend
python app.py
```

Dashboard at `http://localhost:5000` (or double-click
`IIRS/Carbon_Stocks/carbon_project/run_dashboard.bat`). Health check at
`/api/health`.

`DB_MODE` in `.env` selects `files` (default, reads `results/`), `local`
(PostgreSQL + MongoDB, loaded by notebook 03) or `cloud` (Supabase + MongoDB
Atlas). Database modes fall back to the files if a database is unreachable.

Public version: `streamlit run app/streamlit_app.py` serves the same dashboard
without Flask; it is deployed at
<https://carbon-stock-estimation-ludhiana.streamlit.app/>.

Tests: `pytest tests/`.

---

## Further work

- Run `06_shc_validation.ipynb` with the Punjab Soil Health Card table
  (Dataful, sign-in required): it validates SoilGrids against lab tests and
  maps organic carbon from them by regression kriging — the single change that
  would turn the soil figure from a product estimate into a measured one
- Calibrate the crop light-use-efficiency model against flux-tower or
  crop-cut data, so it can replace MOD17 for crop carbon flux
- Above-ground biomass estimation to complement the NPP flux
- Repeat extraction over several years to track change in soil carbon

---

## Licence

MIT
