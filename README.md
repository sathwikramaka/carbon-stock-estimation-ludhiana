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
| Crop-yield check: rice + wheat NPP (lower bound) | 3.34 MtC/yr (90% range 2.70–4.07) |
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

**MODIS NPP and crops.** Reported rice and wheat yields, converted with IPCC
(2019) factors, put at least 3.34 MtC/yr through the district's two main crops;
MOD17 reports about 10% of that. MOD17 is therefore reported as the product
gives it, and the yield-based figure is the better guide to crop carbon flux.

---

## Model performance

All models are validated with **5-fold spatial block cross-validation** over an
8 × 8 grid of geographic blocks, so that no test cell has a training neighbour,
and compared with two baselines.

| Model | Random Forest R² | Coordinates-only R² | Training-mean R² | RF RMSE |
|---|---|---|---|---|
| Above-ground (NPP, gC/m²/yr) | **0.401** | 0.346 | −0.019 | 46.2 |
| Below-ground (SOC, t/ha) | **0.236** | 0.224 | −0.016 | 1.65 |
| Below-ground + SoilGrids texture/BD layers | 0.304 | 0.224 | −0.016 | 1.58 |

Training sample: 20,000 cells with complete data. Predictors: elevation, slope,
ESA WorldCover cropland/built-up/tree/water fractions and twelve monthly
Sentinel-2 NDVI composites (June 2024 – May 2025). These predictors are
independent of the targets, so the R² measures real predictive skill.

> **A note on the below-ground R².** SOC varies little across the district
> (standard deviation 1.9 t/ha around 31 t/ha), and most of what varies is a
> smooth regional gradient, which is why a coordinates-only model already
> reaches 0.22. Adding SoilGrids' own texture and bulk-density layers raises R²
> to 0.30, but those layers share the target's model, so that run measures
> agreement within one product rather than independent skill. The district
> totals do not depend on any model: every cell is observed directly.

Top permutation importances: elevation (NPP 0.50, SOC 0.10) and January NDVI,
the rabi wheat peak (SOC 0.26, NPP 0.07).

---

## Method

### Data sources

| Layer | Source | Resolution | Role |
|---|---|---|---|
| Soil organic carbon stock 0–30 cm (`ocs`) | ISRIC SoilGrids 2.0 | 250 m | SOC stock |
| SOC, bulk density, sand, clay, coarse fragments | SoilGrids 2.0 | 250 m | stock sensitivity; model comparison |
| Net primary productivity | MODIS MOD17A3HGF v6.1, 2024 | 500 m | above-ground flux |
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

Random Forest regressors (300 trees, minimum leaf 5, random state 42) predict
SOC stock and NPP from terrain, land cover and monthly NDVI. District totals
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
- **Soil Health Card:** `06_shc_validation.ipynb` compares SoilGrids with
  laboratory organic carbon at the same cells (Walkley–Black × 1.32).

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
7. **Model skill is moderate.** Satellite covariates explain 40% of NPP
   variation and 24% of SOC variation under spatial validation.
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
    06_shc_validation.ipynb        Soil Health Card comparison
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

- Field soil sampling (or Soil Health Card records, `06_shc_validation.ipynb`)
  to calibrate SoilGrids locally — the single change that would turn the soil
  figure from a product estimate into a measured one
- A crop-specific light-use-efficiency model or yield-based estimate in place
  of MOD17 for crop carbon flux
- Above-ground biomass estimation to complement the NPP flux
- Repeat extraction over several years to track change in soil carbon

---

## Licence

MIT
