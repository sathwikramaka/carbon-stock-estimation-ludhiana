# Carbon Stock Estimation for Ludhiana District, Punjab

### A Grid-Based Machine Learning Approach Using Satellite and Gridded Soil Data

**Big Data Analytics — Project Report**
Indian Institute of Remote Sensing (IIRS), Dehradun

---

> **Note on using this draft.** Sections marked `[FILL IN]` need details only you
> have — dataset identifiers, dates, your institutional formatting. Everything
> else is written from the actual outputs of your pipeline and the four
> diagnostic reports. Adapt the voice to your department's conventions.

---

## Abstract

This study estimates soil organic carbon stock and annual above-ground carbon
assimilation across Ludhiana District, Punjab, using a 250 m analysis grid,
satellite-derived vegetation and climate covariates, and gridded soil data.
Random Forest regression was trained on a 20,000-cell sample and applied to
64,545 grid cells covering 403,406 ha.

Soil organic carbon stock in the 0–30 cm layer is estimated at **5.087 million
tonnes of carbon** (18.65 Mt CO₂e), a mean density of 12.61 tC/ha. Annual
above-ground carbon assimilation derived from net primary productivity is
estimated separately at **4.332 MtC/yr**; the two quantities are not combined, as
one is a stock and the other a flux.

Model performance is reported under spatial block cross-validation rather than
random splitting: R² = 0.403 for net primary productivity, and R² = 0.948 for
soil organic carbon — the latter measuring reproduction of a gridded soil product
rather than validated prediction, as target and predictors share provenance. The
above-ground model, whose target is independent of its predictors, is the honest
indication of predictive skill.

A systematic validation phase identified three issues in the initial analysis: a
unit scaling error inflating soil carbon tenfold, score inflation from spatially
autocorrelated train/test splits, and the invalid summation of an annual flux
with an accumulated stock. All three are documented, and each reduced the
reported figure.

The estimation pipeline is implemented end to end with a PostGIS spatial
database, a MongoDB document store for per-cell predictions, a Flask REST API,
and an interactive web dashboard.

**Keywords:** carbon stock, soil organic carbon, Random Forest, spatial
cross-validation, data provenance, Google Earth Engine, PostGIS, Punjab

---

## 1. Introduction

### 1.1 Background

Soil organic carbon is the largest terrestrial carbon pool and a central quantity
in climate mitigation accounting, agricultural sustainability assessment, and
national greenhouse gas inventories. Its measurement at scale is difficult:
direct soil sampling is accurate but expensive and sparse, while remote sensing
offers wide coverage at the cost of indirect inference.

Punjab presents a specific case of interest. Five decades of intensive
rice–wheat cultivation under the Green Revolution have raised agricultural output
substantially while depleting soil organic carbon, with reported contents in the
range of 0.2–0.6% across much of the cultivated area. Quantifying the remaining
soil carbon pool at district scale supports both carbon accounting and soil
health monitoring.

### 1.2 Objectives

1. Construct a 250 m analysis grid over Ludhiana District and extract satellite
   and soil covariates for each cell.
2. Train machine-learning models to predict soil organic carbon and net primary
   productivity from those covariates.
3. Convert model predictions into carbon stock and carbon assimilation estimates
   using established equations.
4. Validate the models under conditions appropriate to spatial data, and quantify
   the reliability of the resulting estimates.
5. Deploy the results through a database-backed web application supporting
   spatial query and visualisation.

### 1.3 Scope

The study covers the full data science lifecycle: data acquisition through Google
Earth Engine, cleaning and feature engineering, model training and evaluation,
database integration, API development, and web deployment. It is a
remote-sensing-based inventory; no field soil samples were collected, and no
ground calibration was performed. This constraint shapes how the below-ground
results must be interpreted, as set out in Sections 6.2 and 7.1.

---

## 2. Study Area

Ludhiana District lies in central Punjab, in the Indo-Gangetic alluvial plain.

| Attribute | Value |
|---|---|
| Official area | 3,767 km² (376,700 ha) |
| Approximate extent | 30.56° – 31.02° N, 75.35° – 76.34° E |
| Terrain | Flat alluvial plain, low relief |
| Dominant land use | Irrigated agriculture |
| Cropping system | Rice (kharif) – wheat (rabi), double-cropped |
| Irrigation | Canal and tubewell; rainfall is not the limiting input |

The near-universal irrigation is relevant to the interpretation of climate
covariates in this study, discussed in Section 6.4.

`[FILL IN]` — Add a location map showing the district within Punjab and India.

---

## 3. Data

### 3.1 Sources

| Layer | Source | Native resolution | Role |
|---|---|---|---|
| Net primary productivity | MODIS `[FILL IN product ID]` | `[FILL IN]` | Above-ground target |
| Soil organic carbon | SoilGrids | 250 m | Below-ground target |
| Sand, clay, bulk density | SoilGrids | 250 m | Below-ground predictors |
| NDVI, 12 monthly composites | `[FILL IN sensor]` | `[FILL IN]` | Above-ground predictors |
| Elevation, slope | `[FILL IN — SRTM?]` | 30 m | Both models |
| Land surface temperature | `[FILL IN]` | `[FILL IN]` | Above-ground predictors |
| Seasonal precipitation | `[FILL IN]` | `[FILL IN]` | Above-ground predictors |
| Agricultural classification | `[FILL IN]` | — | Land use mask |

All layers were extracted through Google Earth Engine and aggregated to a
250 m × 250 m grid covering the district, giving 6.25 ha per cell.

Note that the below-ground target and three of its six predictors originate from
the same source product. This is a structural property of the design, not an
oversight, and it constrains the interpretation of below-ground model
performance. Section 6.2 quantifies the consequence.

### 3.2 Temporal coverage

NDVI composites span June 2024 to May 2025, covering one complete kharif–rabi
cycle. `[FILL IN]` — state the reference years for NPP, LST and precipitation.

### 3.3 Grid construction and duplicate resolution

The Earth Engine export produced 66,790 rows but only **64,545 unique grid
identifiers**, a duplication of 2,155 cells arising from the export process.
Duplicates were resolved by retaining, for each identifier, the row with the
highest agricultural fraction. Output filenames retain the `66790` label for
continuity with earlier project outputs; all analysis uses 64,545 cells.

The resulting grid covers 403,406 ha against an official district area of
376,700 ha — an overrun of **7.1%**, discussed in Section 6.5.

### 3.4 Sampling

A 20,000-cell sample was extracted with full target values for model training. Of
these, 16,252 fall within agricultural land; 12,602 of those carry non-zero net
primary productivity and form the above-ground training set. All 20,000 cells
were used for the below-ground model.

### 3.5 Missing data

NDVI is incomplete during the monsoon owing to cloud cover:

| Month | Cells missing | Share |
|---|---|---|
| NDVI_Aug24 | 31,396 | 48.6% |
| NDVI_Jul24 | 3,588 | 5.6% |

Gaps were filled with the median value for that month across available cells,
after first attempting to fill from the 20,000-cell sample where overlapping
observations existed. All remaining predictors were median-filled.

### 3.6 Unit verification

Input variables were audited against published physical ranges for Punjab
agricultural soils before analysis was finalised. This identified a scaling error
in the soil organic carbon layer, described in Section 5.4.

---

## 4. Methodology

### 4.1 Overview

```
Earth Engine extraction
        ↓
Cleaning, NDVI merge, unit correction
        ↓
Train/test partition (20,000-cell sample)
        ↓
Random Forest and gradient boosting
        ↓
Model selection on held-out data
        ↓
Prediction across all 64,545 cells
        ↓
Carbon conversion
        ↓
PostGIS + MongoDB → Flask API → dashboard
```

### 4.2 Carbon equations

**Soil organic carbon stock**

```
SOC stock (tC/ha) = SOC (g/kg) × bulk density (g/cm³) × depth (cm) / 10
```

This is the standard equation for soil carbon stock, applied here to the 0–30 cm
layer following IPCC Tier 1 convention. Coarse fragment correction was not
applied; coarse fragments are negligible in the alluvial soils of the study area.

**Above-ground carbon assimilation**

```
AGC (tC/ha/yr) = NPP (gC/m²/yr) / 100
```

MODIS net primary productivity is reported directly in grams of carbon, so no
biomass-to-carbon conversion factor is applied. An earlier version of this
analysis multiplied by 0.47 — the dry-matter carbon fraction — which counted the
conversion twice. This is corrected here.

**CO₂ equivalent**

```
CO₂e = carbon × 44/12
```

### 4.3 Feature sets

**Below-ground (6 features):** agricultural class, elevation, slope, sand
percentage, clay percentage, bulk density.

**Above-ground (22 features):** elevation, slope, kharif and rabi peak NDVI and
precipitation, land surface temperature for two seasons, NDWI, and twelve monthly
NDVI composites.

Grid identifiers and geometry were excluded from both feature sets.

### 4.4 Models

Random Forest and gradient boosting regressors were trained for each target.

| Parameter | Random Forest | Gradient boosting |
|---|---|---|
| Estimators | 300 | 300 |
| Min samples split | 4 | — |
| Min samples leaf | 2 | — |
| Learning rate | — | 0.05 |
| Max depth | unrestricted | 6 |
| Random state | 42 | 42 |

Predictions were clipped at zero, as neither soil carbon nor productivity can be
negative.

Random Forest outperformed gradient boosting for both targets and was used for
the reported results.

### 4.5 Scaling to district level

Below-ground carbon was computed per cell and summed across all 64,545 cells.
Above-ground carbon was computed for agricultural cells only; non-agricultural
cells were assigned zero above-ground assimilation.

### 4.6 System architecture

| Component | Technology | Role |
|---|---|---|
| Analysis | Python, scikit-learn, pandas | Modelling pipeline |
| Spatial store | PostgreSQL + PostGIS | Grid geometry, spatial queries |
| Document store | MongoDB | Per-cell predictions, model metadata |
| API | Flask | REST endpoints |
| Frontend | Leaflet, Chart.js | Map and analytics dashboard |

The API exposes endpoints for district summary, GeoJSON retrieval by bounding
box, per-cell prediction listings, NDVI seasonality, model metrics, and a health
check. Database credentials are supplied through environment variables, with a
mode switch between local and cloud deployment.

---

## 5. Results

### 5.1 Soil organic carbon

| Quantity | Value |
|---|---|
| **Soil organic carbon stock (0–30 cm)** | **5.087 MtC** |
| CO₂ equivalent | 18.65 Mt CO₂e |
| Mean carbon density | 12.61 tC/ha |
| Cells | 64,545 |
| Grid area | 403,406 ha |
| Area-corrected to official boundary | 4.750 MtC |

The mean density of 12.61 tC/ha sits slightly below the 15–35 tC/ha range
reported for Indian agricultural soils. This is consistent with Punjab's
documented soil organic carbon depletion under intensive cultivation, and
corresponds to approximately 0.28% organic carbon — within the 0.2–0.6% range
reported in regional soil surveys.

### 5.2 Above-ground carbon assimilation

| Quantity | Value |
|---|---|
| Annual above-ground carbon assimilation | 4.332 MtC/yr |
| Mean rate | 17.73 tC/ha/yr |
| Mean net primary productivity | 1,460 gC/m²/yr |

The productivity value is consistent with irrigated double-cropped systems, which
reach the upper end of the 600–1,200 gC/m²/yr range typical of rainfed cropland.

### 5.3 Why the two figures are not summed

Soil organic carbon is a **stock** — carbon accumulated in the soil profile over
decades, measured in tonnes. Net primary productivity is a **flux** — carbon
fixed by vegetation during one growing year, measured in tonnes per year. The two
have different units and different time dimensions; their sum has no physical
interpretation.

The distinction is sharper still in an annual cropping system. Above-ground
biomass is harvested and removed each season, so standing above-ground carbon at
any given moment is close to zero. What the productivity figure describes is the
district's annual carbon fixation capacity, not a standing pool.

An earlier version of this analysis reported a combined figure. It is superseded.

### 5.4 Unit correction

The audit of input units against published physical ranges revealed that the
Earth Engine export had rescaled three of four soil bands but not the fourth.

| Variable | Native unit | As extracted | Rescaled during export |
|---|---|---|---|
| Bulk density | cg/cm³ | 1.38 g/cm³ | Yes (÷100) |
| Sand | g/kg | 34.3% | Yes (÷10) |
| Clay | g/kg | 25.8% | Yes (÷10) |
| **Organic carbon** | **dg/kg** | **28.33** | **No** |

Uncorrected, this produced a soil carbon density of 126.1 tC/ha — roughly five
times the upper end of published values, implying 2.8% soil organic carbon in
soils documented at 0.2–0.6%.

Applying the correction reduced the soil carbon estimate from 50.87 MtC to
**5.087 MtC**. Model R² values were unchanged, confirming that the correction is
a pure rescaling of the target and that no other model behaviour was affected.

---

## 6. Validation

### 6.1 Two validation schemes

| Model | Random split R² | Spatial block CV R² |
|---|---|---|
| Below-ground (SOC), all features | 0.9665 | **0.9481** |
| Below-ground, without bulk density | 0.9597 | 0.9389 |
| Below-ground, terrain and class only | 0.3021 | 0.2081 |
| Below-ground, coordinates only | 0.6869 | 0.1724 |
| Above-ground (NPP), all features | 0.5426 | **0.4028** |
| Above-ground, process features only | 0.4755 | 0.3685 |
| Above-ground, coordinates only | 0.6127 | 0.3185 |

> **A note on the below-ground R².** The SOC target is SoilGrids-derived, and
> several predictors — sand, clay, bulk density — are also SoilGrids layers.
> Their mutual correlations run 0.84–0.97, and two are physically inverted: sand
> and clay correlate +0.84 where competing texture fractions should oppose one
> another, and bulk density correlates +0.97 with organic carbon where added
> organic matter should reduce it through greater pore space. The 0.9481
> therefore measures how well the model reproduces the SoilGrids surface, not how
> well it predicts measured soil carbon. It is a reproducibility check on a
> gridded product, not a validated soil prediction. The above-ground NPP model,
> whose target is independent of its predictors, is the honest indication of
> predictive skill at 0.4028. Independent field measurements would be required to
> validate the SOC model.

A random 80/20 split places adjacent 250 m cells in both the training and test
sets. Because neighbouring cells are strongly spatially autocorrelated, the model
can effectively retrieve an answer it has already encountered, inflating the
apparent score.

Spatial block cross-validation partitions the district into an 8 × 8 geographic
grid and holds out whole blocks across five folds, so that no test cell has a
training neighbour. The spatial cross-validation figures are reported as the
defensible measures of predictive skill, subject to the provenance caveat above.

Both models substantially outperform a mean-prediction baseline (R² ≈ 0).

### 6.2 Provenance of the below-ground result

The caveat above warrants expansion, because it determines what the below-ground
figure can be claimed to demonstrate.

Gridded soil products such as SoilGrids are themselves machine-learning outputs,
predicted from a shared stack of terrain, climate and spectral covariates. Layers
produced by one model over one covariate set will inherit each other's spatial
structure. The correlation matrix for the training sample shows this directly:

| | sand | clay | bulk density | SOC |
|---|---|---|---|---|
| sand | 1.000 | 0.839 | 0.954 | 0.896 |
| clay | 0.839 | 1.000 | 0.946 | 0.950 |
| bulk density | 0.954 | 0.946 | 1.000 | 0.966 |
| SOC | 0.896 | 0.950 | 0.966 | 1.000 |

Two of these relationships contradict soil physics. Sand and clay are competing
texture fractions and should correlate negatively; here they correlate +0.839.
Bulk density should fall as organic carbon rises, since organic matter creates
pore space; here it rises with organic carbon at +0.966.

Two further tests bear on the interpretation. First, the predictors are largely
interchangeable: removing bulk density entirely changes R² by 0.007, and bulk
density alone reaches 0.950. Second, the result is not merely spatial
memorisation — a coordinates-only model collapses to R² = 0.172 under spatial
cross-validation, and the training sample contains 19,188 distinct
sand/clay/bulk-density combinations across 20,000 cells, ruling out a
lookup-table structure.

The correct characterisation is therefore narrow and specific: the model
reproduces one gridded product from other layers of that same product with high
fidelity. This is a meaningful demonstration that the covariance structure is
learnable, and it is a valid basis for extending SOC values from 20,000 sampled
cells to 64,545. It is not evidence of accuracy against measured soil carbon,
and no such evidence exists in this study.

### 6.3 Feature importance

Feature importance is reported as permutation importance measured on held-out
data. Impurity-based importance, the default in Random Forest implementations,
systematically favours continuous predictors with many candidate split points and
can misrepresent the model's actual dependencies.

### 6.4 Climate covariates as position proxies

Each predictor was tested by fitting it from longitude and latitude alone. Four
covariates proved almost perfectly reconstructible from position:

| Feature | R² from coordinates alone |
|---|---|
| LST_Sept20 | 0.9998 |
| Kharif_Pre | 0.9998 |
| Rabi_Preci | 0.9997 |
| Rabi_LST_2 | 0.9608 |

These are interpolated surfaces derived from products substantially coarser than
the 250 m analysis grid. Across a district spanning roughly 60 km they vary as
smooth gradients with no local detail.

Rabi precipitation ranks highest in permutation importance (0.348). This does not
indicate that winter rainfall drives productivity — the district's agriculture
depends on canal and tubewell irrigation, not rainfall. Rather, the rainfall
surface correlates 0.879 with longitude while net primary productivity correlates
0.633 with longitude. The model is tracking a district-wide east–west gradient.

A sensitivity model excluding all four proxy features scored 0.3685 under spatial
cross-validation — below the full model's 0.4028, but above the coordinates-only
baseline of 0.3185. The retained NDVI, terrain and moisture features therefore
contribute genuine local information, while the climate surfaces contribute
spatial structure. The full model is retained for the reported results, with the
interpretation stated accordingly.

### 6.5 Sensitivity of the carbon estimate

Three alternative above-ground model specifications produced district estimates
spanning 0.013 MtC — **0.02% of the reported figure**. The carbon estimate is
therefore insensitive to above-ground model choice.

Area correction to the official district boundary reduces soil carbon from 5.087
to 4.750 MtC, a 6.6% reduction. This is the largest single source of quantified
uncertainty in the reported figures.

---

## 7. Limitations

**7.1 Shared provenance in the soil data.** As set out in Sections 6.1 and 6.2,
the below-ground target and three of its predictors are layers of a single
gridded product with mutual correlations of 0.84–0.97 and two physically inverted
signs. The reported R² measures agreement within that product rather than
accuracy against field-measured carbon.

**7.2 No field validation.** No independent soil samples were available. The
estimate is a remote-sensing inventory, not a measured one. This is the single
most consequential limitation of the study, and the one that would most improve
the work if addressed.

**7.3 Depth restriction.** The estimate covers 0–30 cm only. Soil carbon extends
below this depth; total profile carbon would be substantially higher. The 30 cm
convention follows IPCC Tier 1 guidance, aiding comparability but understating
the full pool.

**7.4 Grid boundary overrun.** The grid covers 403,406 ha against an official
376,700 ha, a 7.1% overrun. Totals carry this upward bias unless area-corrected.

**7.5 Climate covariates as position proxies.** Four covariates function as
spatial indicators rather than process variables at 250 m resolution, as
documented in Section 6.4.

**7.6 Monsoon NDVI gaps.** NDVI_Aug24 is missing for 49% of cells and was
median-filled, suppressing spatial variation during peak kharif growth —
precisely when the vegetation signal is most informative.

**7.7 Above-ground pool is a flux.** A true above-ground biomass carbon stock
would require allometric relationships, canopy height retrieval, radar
backscatter, or a dedicated biomass product such as GEDI or ESA CCI Biomass.

**7.8 Prediction where direct extraction was possible.** Soil organic carbon is
available globally from the source product, as is net primary productivity.
Extracting both directly for all 64,545 cells would remove the prediction step
and its associated uncertainty. The machine-learning component demonstrates the
modelling workflow required by this project; it is not the most accurate route to
the carbon figures themselves.

---

## 8. System Implementation

`[FILL IN]` — Describe the deployment with reference to your screenshots.

Suggested coverage:

- Database schema: `grid_cells` (PostGIS, MultiPolygon geometry with GIST index),
  `district_summary`, and five MongoDB collections
- API endpoint list and what each returns
- Dashboard pages: home, map, analytics, model, explorer
- Spatial query design: bounding-box retrieval via `ST_Intersects` with
  `ST_MakeEnvelope`
- Configuration through environment variables, with a local/cloud mode switch

Insert the dashboard screenshots here with captions.

---

## 9. Conclusions

Soil organic carbon stock in Ludhiana District's top 30 cm is estimated at 5.087
MtC (4.750 MtC when corrected to the official district boundary), equivalent to
18.65 Mt CO₂. Annual above-ground carbon assimilation is estimated separately at
4.332 MtC/yr.

The above-ground model achieves R² = 0.403 under spatial cross-validation, and
analysis showed that a substantial part of its apparent skill derives from
climate covariates functioning as geographic position indicators. The
below-ground model achieves R² = 0.948, but because its target and several of its
predictors are layers of one gridded soil product, this figure measures
reproduction of that product rather than validated prediction of measured soil
carbon. Independent field sampling would be required to establish the latter.

Three corrections were made during validation, each reducing the reported figure:
a missing unit conversion inflating soil carbon tenfold, adoption of spatial
cross-validation in place of random splitting, and separation of an annual flux
from an accumulated stock. Each is documented with its supporting diagnostic
output.

### 9.1 Recommendations for further work

1. **Field calibration.** Even a modest set of soil samples would allow the
   gridded product to be validated or bias-corrected, converting the below-ground
   estimate from product agreement into measurement. This is the highest-value
   extension of the work.

2. **Direct extraction in place of prediction.** Both source products have global
   coverage; extracting them for all cells would remove the prediction step.

3. **Boundary clipping.** Restricting the grid to the official district polygon
   would remove the 7.1% area bias.

4. **Above-ground biomass estimation.** Replacing the productivity proxy with a
   genuine biomass carbon stock would permit a valid combined inventory.

5. **Spatial cross-validation from the outset.** Any extension of this work
   should adopt spatial blocking as the default validation scheme.

---

## References

`[FILL IN]` — Verify each of the following before including it; check author,
year and journal against the actual publication.

- The source datasets, with their documentation and unit specifications
- IPCC Guidelines for National Greenhouse Gas Inventories, Volume 4 (AFOLU), for
  the soil carbon stock methodology and 30 cm depth convention
- Regional literature on Punjab soil organic carbon status
- Roberts et al., *Ecography* — cross-validation strategies for spatial, temporal
  and hierarchically structured data
- Strobl et al., *BMC Bioinformatics* — bias in Random Forest variable importance
  measures
- Breiman, *Machine Learning* — Random Forests
- Poggio et al., *SOIL* — SoilGrids 2.0, for the product's own description of its
  modelling approach and reported uncertainties

---

## Appendix A — Diagnostic Outputs

The following files in the project repository contain the raw output supporting
Sections 5.4, 6.1, 6.2, 6.4 and 6.5:

| File | Contents |
|---|---|
| `units_audit_report.txt` | Input unit audit against published ranges |
| `diagnostics_report.txt` | Feature cardinality, correlations, permutation importance, ablation, spatial CV, baselines |
| `deep_diagnostics_report.txt` | Soil data provenance tests, rainfall spatial proxy analysis |
| `honest_model_report.txt` | Proxy-excluded model comparison, carbon sensitivity |

Each can be reproduced by running the corresponding script from the project root.

## Appendix B — Reproduction

`[FILL IN]` — Repository URL, environment setup, and run order. The README
contains this information and can be referenced rather than duplicated.
