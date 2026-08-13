# Carbon Stock Estimation — Ludhiana District, Punjab

Grid-based estimation of soil organic carbon and above-ground carbon
assimilation across Ludhiana District using MODIS satellite imagery, SoilGrids
soil data, and Random Forest regression at 250 m resolution — with a Flask API,
PostGIS spatial database, MongoDB document store, and an interactive dashboard.

Academic project, Indian Institute of Remote Sensing (IIRS) — Big Data
Analytics.

---

## Results

| Quantity | Value |
|---|---|
| **Soil organic carbon stock (0–30 cm)** | **5.087 MtC** |
| CO₂ equivalent | 18.65 Mt CO₂e |
| Mean soil carbon density | 12.61 tC/ha |
| Annual above-ground carbon assimilation | 4.332 MtC/yr |
| Grid cells analysed | 64,545 |
| Grid resolution | 250 m × 250 m (6.25 ha per cell) |
| Grid area | 403,406 ha |

**The two carbon figures are reported separately and are not summed.** Soil
organic carbon is a *stock*, accumulated over decades and measured in tonnes.
Net primary productivity is a *flux*, describing carbon fixed in one year and
measured in tonnes per year. Adding them would combine different units and
different time dimensions. In an annual cropping system the distinction matters
particularly, since above-ground biomass is harvested each season and standing
above-ground carbon is close to zero for most of the year.

---

## Model performance

Two validation schemes are reported, because random splitting proved optimistic
on spatially autocorrelated data.

| Model | Random split R² | Spatial block CV R² |
|---|---|---|
| Below-ground (SOC) | 0.9665 | **0.9481** |
| Above-ground (NPP) | 0.5426 | **0.4028** |

A random 80/20 split places adjacent 250 m cells in both training and test sets.
Because neighbouring cells are strongly correlated, the model can retrieve an
answer it has already seen. Spatial block cross-validation partitions the
district into an 8 × 8 geographic grid and holds out whole blocks. **The spatial
CV figures are the defensible measures of predictive skill.**

---

## Method

### Data sources

| Layer | Source | Role |
|---|---|---|
| Net primary productivity | MODIS | Above-ground target |
| Soil organic carbon, texture, bulk density | SoilGrids | Below-ground target and predictors |
| NDVI, 12 monthly composites | Sentinel-2 / Landsat via GEE | Above-ground predictors |
| Elevation, slope | SRTM-derived | Both models |
| Land surface temperature, precipitation | Gridded climate products | Above-ground predictors |

All layers extracted through Google Earth Engine over a 250 m grid covering the
district.

### Carbon equations

```
Soil organic carbon (tC/ha) = SOC (g/kg) × bulk density (g/cm³) × depth (cm) / 10
Above-ground assimilation (tC/ha/yr) = NPP (gC/m²/yr) / 100
```

The soil equation follows IPCC Tier 1 convention for the 0–30 cm layer. MODIS
NPP is already expressed in grams of carbon, so no biomass-to-carbon fraction is
applied.

### Modelling

Random Forest and gradient boosting were trained on a 20,000-cell sample and
applied to all 64,545 cells. Random Forest performed better for both targets and
is used for the reported results.

---

## Validation and corrections

Three substantive corrections were made during validation. All are documented
rather than silently applied, and each reduced the headline figure.

### 1. Unit scaling error in soil organic carbon

Input variables were audited against published physical ranges for Punjab
agricultural soils. SoilGrids reports organic carbon in dg/kg, bulk density in
cg/cm³, and texture in g/kg. Three of the four bands had been rescaled during
the Earth Engine export; organic carbon had not.

Uncorrected, this produced a soil carbon density of 126.1 tC/ha — roughly five
times the upper end of published values, implying 2.8% soil organic carbon in
soils documented at 0.2–0.6%. Applying the correction reduced the soil carbon
estimate from 50.87 MtC to 5.087 MtC.

Model R² values were unchanged by the correction, confirming a pure rescaling.

### 2. Spatial cross-validation

Random splitting was replaced with spatial block cross-validation, reducing
reported above-ground R² from 0.5426 to 0.4028 and below-ground from 0.9665 to
0.9481.

### 3. Separation of flux from stock

The above-ground NPP figure was previously summed with soil carbon to give a
combined total. This was replaced with separate reporting, for the reasons given
above.

### Coordinate proxy analysis

Each predictor was tested by fitting it from longitude and latitude alone. Four
climate covariates proved almost perfectly reconstructible from position:

| Feature | R² from coordinates alone |
|---|---|
| LST_Sept20 | 0.9998 |
| Kharif_Pre | 0.9998 |
| Rabi_Preci | 0.9997 |
| Rabi_LST_2 | 0.9608 |

These are interpolated surfaces from products substantially coarser than the
250 m analysis grid. Rabi precipitation ranks highest in permutation importance
(0.348) not because winter rainfall drives productivity in an irrigated system,
but because the rainfall surface correlates 0.879 with longitude while NPP
correlates 0.633 with longitude. The model tracks a district-wide east–west
gradient.

A model excluding all four proxies scored 0.3685 under spatial CV, below the
full model's 0.4028 but above a coordinates-only baseline of 0.3185 —
demonstrating that the retained NDVI and terrain features carry genuine local
information.

Feature importance is reported as permutation importance on held-out data
rather than impurity importance, which favours continuous predictors with many
split points.

---

## Limitations

1. **Shared provenance in soil data.** Sand, clay, bulk density and soil organic
   carbon are all layers of one gridded product. Their mutual correlations range
   0.84–0.97, and two relationships are physically inverted: sand and clay
   correlate +0.84 where competing fractions should oppose, and bulk density
   correlates +0.97 with organic carbon where added organic matter should reduce
   it. The below-ground R² measures agreement within one soil product, not
   accuracy against field measurement.

2. **No field validation.** No independent soil samples were available. The
   estimate is a remote-sensing inventory, not a measured one.

3. **Depth restriction.** 0–30 cm only. Total profile carbon would be higher.

4. **Grid overruns the district boundary** by 7.1% (403,406 ha against an
   official 376,700 ha). Area-corrected soil carbon is 4.750 MtC.

5. **NDVI gaps.** NDVI_Aug24 is missing for 49% of cells due to monsoon cloud,
   filled with monthly medians.

6. **Duplicate grid identifiers.** The export contained 66,790 rows but 64,545
   unique cells; duplicates resolved by retaining the highest agricultural
   fraction per cell. Filenames retain the 66790 label for continuity.

7. **Above-ground is a flux.** A true above-ground biomass stock would require
   allometric, canopy-height, radar, or dedicated biomass products such as GEDI
   or ESA CCI Biomass.

---

## Stack

**Analysis** — Python, scikit-learn, pandas, Google Earth Engine
**Databases** — PostgreSQL + PostGIS (geometry), MongoDB (predictions)
**Backend** — Flask, psycopg2, pymongo
**Frontend** — Leaflet, Chart.js

---

## Repository layout

```
IIRS/
  Carbon_Stocks/
    carbon_project/
      backend/          Flask API
      frontend/         dashboard
    *.csv               inputs and outputs
    *.pkl               trained models
    *_report.txt        diagnostic reports
  Scrpit/
    carbon_stock_pipeline.ipynb
model_diagnostics.py      validation scheme comparison
deep_diagnostics.py       soil provenance and spatial proxy tests
rebuild_honest_models.py  proxy-excluded sensitivity models
units_audit.py            input unit audit against published ranges
update_website_metrics.py publishes validated metrics to the databases
```

---

## Running it

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
PROJECT_ROOT=<absolute path to this folder>
DB_MODE=local
MONGO_URI=mongodb://localhost:27017/
MONGO_DB=carbon_stock_ludhiana
PG_HOST=localhost
PG_PORT=5432
PG_DB=postgres
PG_USER=postgres
PG_PASSWORD=<your password>
```

Run the notebook `IIRS/Scrpit/carbon_stock_pipeline.ipynb` steps 1–10, then:

```bash
cd IIRS/Carbon_Stocks/carbon_project/backend
python app.py
```

Dashboard at `http://localhost:5000`. Health check at `/api/health`.

`DB_MODE=cloud` switches to Supabase and MongoDB Atlas using the corresponding
`.env` variables.

---

## Further work

- Field soil sampling to calibrate the gridded soil product
- Direct extraction of SOC and NPP for all cells rather than prediction, since
  both source products have global coverage
- Clipping the grid to the official district boundary
- Above-ground biomass estimation to replace the NPP proxy
- Spatial cross-validation adopted from the outset

---

## Licence

MIT
