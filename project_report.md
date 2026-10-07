# Carbon Indicators for Ludhiana District, Punjab

### Repairing a gridded Earth Engine extraction, and what a model can and cannot add

**Big Data Analytics — Project Report**
Sathwik Ramaka · M.Sc. Agriculture Analytics · Indian Institute of Remote Sensing (IIRS), Dehradun
`[FILL IN: supervisor, submission date, institutional formatting]`

> Status: v1 interim results. All figures are produced by
> `notebooks/02_carbon_pipeline.ipynb` and can be regenerated from the
> repository. Section 9 states what changes after the planned re-extraction.

---

## Abstract

This study estimates the 0–30 cm soil organic carbon (SOC) stock and annual net
primary production (NPP) of Ludhiana District on a 66,700-cell, 250 m grid built
from SoilGrids 2.0 and MODIS MOD17A3HGF data extracted through Google Earth
Engine. An audit of the extraction found that masked soil pixels had been
averaged as zeros, diluting every soil band in proportion to each cell's valid
fraction; that the grid identifier was a random number with 2,155 collisions;
and that the MOD17 scale factor had never been applied. The dilution created
spurious correlations (sand × clay +0.84, bulk density × SOC +0.97) that allowed
a random forest to report a spatial cross-validated R² of 0.949. Rebuilt, the
same model scores 0.955 with the diluted cells and 0.191 without them, barely
above a model given only coordinates.

Because the 20,000-cell training file behaves in every check as a simple random
sample of the grid, district totals were re-estimated without a predictive
model, using design-based estimators on repaired soil values. The SOC stock is
**4.549 MtC** (95% CI 4.546–4.552, sampling error only), a mean of 13.79 tC/ha
over 329,814 ha of mapped soil. Correctly scaled MOD17 NPP is **0.295 MtC/yr**, which is 8.8% of
an independent lower bound of **3.34 MtC/yr** (90% range 2.70–4.07) computed
from reported rice and wheat yields; MOD17 also reports negative annual NPP in
19.8% of agricultural cells, so it is not fit for crop carbon flux in this
landscape. The results are served by a Flask/PostGIS/MongoDB dashboard that
reads only what the pipeline writes.

**Keywords:** soil organic carbon, SoilGrids, MOD17, Google Earth Engine,
design-based estimation, spatial cross-validation, data provenance, Punjab

---

## 1. Introduction

Soil organic carbon is the largest terrestrial carbon pool and a central quantity
in agricultural sustainability and greenhouse-gas accounting. Punjab's five
decades of intensive rice–wheat cultivation have raised output while depleting
soil carbon, which makes district-scale estimates of the remaining pool useful
for soil-health monitoring.

Gridded global products — SoilGrids for soil properties, MODIS MOD17 for
productivity — make such estimates possible without field sampling, and Google
Earth Engine makes them easy to extract. Ease of extraction is also a risk: a
reducer default, an identifier column or an unapplied scale factor can change a
result by an order of magnitude without raising an error. This project began as
a machine-learning estimate of carbon stock and became, through validation, a
case study in that risk.

### 1.1 Objectives

1. Build a 250 m grid over Ludhiana District with soil, productivity, terrain and
   vegetation covariates.
2. Estimate the district SOC stock and NPP flux with stated uncertainty.
3. Evaluate whether machine learning adds skill beyond simpler baselines under
   validation appropriate to spatial data.
4. Deliver the results through a reproducible pipeline and a database-backed
   web dashboard.

---

## 2. Study area

| Attribute | Value |
|---|---|
| Official area (Census 2011) | 3,767 km² (376,700 ha) |
| Extent | 30.56°–31.02° N, 75.35°–76.34° E |
| Terrain | Flat Indo-Gangetic alluvial plain |
| Cropping | Rice (kharif) – wheat (rabi), double-cropped |
| Irrigation | Tubewell and canal; rainfall is not limiting |
| Paddy 2024 | 256,600 ha at 7,014 kg/ha |
| Wheat 2023-24 | 245,200 ha at about 5,000 kg/ha (in-season figure) |

`[FILL IN: location map — district within Punjab and India]`

---

## 3. Data

### 3.1 Inputs

| Layer | Source | Stored unit | Role |
|---|---|---|---|
| Soil organic carbon | ISRIC SoilGrids 2.0 `soc` | dg/kg | stock |
| Bulk density | SoilGrids `bdod` (rescaled in export) | g/cm³ | stock; dilution diagnostic |
| Sand, clay | SoilGrids (rescaled in export) | % | model experiment |
| Net primary production | MODIS MOD17A3HGF v6.1 `Npp` | DN (× 0.0001 kgC/m²) | flux |
| Elevation, slope | SRTM | m, degrees | model experiment |
| Monthly NDVI, Jun 2024 – May 2025 | `[sensor not recorded in v1]` | index | model experiment |
| Seasonal rainfall, land-surface temperature | `[not recorded]` | mm, °C | excluded (Section 6.4) |
| Agricultural class and fraction | `[not recorded]` | 0/1, fraction | reporting |

The original extraction script was not preserved, so provenance for v1 inputs
was reconstructed from the data (`docs/DATA_DICTIONARY.md`). A replacement
extraction notebook now documents every asset and parameter (Section 9).

### 3.2 Structure of the exports

The grid exports hold 66,700 cells (soil, terrain and climate covariates, no
targets). A second pair of files holds 20,000 cells with SOC and NPP. Every
sample polygon matches a grid polygon exactly, and the sample fraction is
0.29–0.32 in every land class, soil class and 5 × 5 geographic region, with
covariate means indistinguishable from the unsampled cells. Balance checks
cannot prove randomness, but the sample behaves exactly as a simple random
sample of the grid would (`01_data_audit`, S1).

The grid is a regular EPSG:4326 lattice of 0.002245788° squares (250 m at the
equator; about 249.7 m × 214.5 m at Ludhiana, 5.35 ha). Its 66,700 cells cover
356,894 ha, 94.7% of the Census district area.

---

## 4. Audit of the extraction

Each finding below is reproduced in `notebooks/01_data_audit.ipynb` and recorded
in `AUDIT.md` with its status.

### 4.1 Unmasked nodata diluted every soil band

Every soil band has a minimum of exactly zero, and in 773 sample cells all four
soil bands are zero together. Where SoilGrids has a value, bulk density is nearly
constant (median 1.500 g/cm³, sd 0.024), yet 1,527 cells lie between 0 and
1.40 g/cm³. In those cells the ratios between bands are preserved — sand/BD
25.7 against 24.9 in undiluted cells, SOC/BD 19.5 against 20.5 — which is the
signature of every band in a cell being multiplied by the same factor *w*, the
share of the cell with valid SoilGrids pixels. The extraction evidently averaged
masked pixels as zeros. 98.5% of the 782 zero-bulk-density sample cells are
non-agricultural (built-up land and water, where SoilGrids makes no prediction).

A shared multiplicative factor makes all bands correlate positively regardless
of their physics:

| Pair | As extracted | Undiluted cells (BD ≥ 1.40) | Repaired (value / *w*) |
|---|---|---|---|
| sand × clay | +0.839 | −0.674 | −0.677 |
| bulk density × SOC | +0.966 | −0.266 | −0.257 |
| clay × SOC | +0.950 | +0.325 | +0.339 |

Sand and clay are competing fractions and should correlate negatively; organic
matter lowers bulk density. The repaired values recover both relationships.
An earlier draft of this report interpreted the inverted correlations as an
internal inconsistency of SoilGrids. That interpretation is withdrawn: the
product is consistent; the extraction was not.

**Repair.** Because undiluted bulk density is near-constant, *w* = BD / 1.50
estimates each cell's valid fraction (`config.soil_qc`). Cells with BD ≥ 1.40
are treated as fully valid (59,089 of 66,700); cells with 0 < BD < 1.40 are
repaired by dividing every soil band by *w* (4,958); cells with BD = 0 carry no
soil value (2,653). No cell is deleted. A repaired cell's stock,
(SOC/*w*)(BD/*w*) × 3 × *w* × area = SOC_diluted × 1.50 × 3 × area, does not
depend on *w*, so every partial cell enters the totals; only cells with
*w* ≥ 0.5 are used as interpolation sources, where the per-cell value itself is
precise.

### 4.2 The grid identifier is a random number

The 66,700 grid rows contain 66,700 distinct polygons but only 64,545 distinct
`Grid_ID` values. If identifiers were drawn uniformly from 10⁶ values, the
expected number of distinct values would be 64,524, and the multiplicity
spectrum would follow a Poisson distribution; the observed spectrum (62,431
singletons, 2,075 pairs, 37 triples, 2 quadruples) matches the expected one
(62,396 / 2,081 / 46 / 1). The column is a random sampling device, not a key.

The earlier pipeline treated the collisions as export duplicates and kept the
row with the highest agricultural fraction. That deleted 2,155 real cells, whose
mean agricultural fraction was 0.654 against 0.95 for the cells retained from the
same groups, and joined NDVI to geographically unrelated cells. All data are now
keyed by `cell_id = r{row}_c{col}`, the cell's absolute position on the lattice.

### 4.3 The MOD17 scale factor was never applied

MOD17A3HGF stores NPP as an integer DN with scale 0.0001 kgC/m². The NPP column
is 77% exact integers in the range −3,687 to 2,846 (median 1,203), i.e. raw DN;
non-integers arise where a 250 m cell straddles 500 m MODIS pixels. The earlier
pipeline divided DN by 100, treating it as gC/m², which overstates the flux
tenfold. The correct conversion is

```
NPP flux (tC/ha/yr) = DN × 0.0001 kgC/m² × 10 = DN / 1000
```

### 4.4 Further findings

- **Duplicated target.** Up to four 250 m cells share one 500 m MODIS value; 73%
  of NPP rows share their exact target with another row, so random train/test
  splits leak the test target.
- **Position proxies.** Seasonal rainfall and land-surface temperature are
  reconstructible from longitude and latitude with R² ≥ 0.98; they are smooth
  interpolated surfaces with no information at 250 m.
- **Depth.** SoilGrids has no 0–30 cm layer and the v1 export does not record
  which interval was used; coarse fragments were not removed.

---

## 5. Methods

### 5.1 Carbon equations

```
SOC stock (tC/ha) = SOC (g/kg) × bulk density (g/cm³) × 30 cm × (1 − coarse fraction) / 10
NPP flux (tC/ha/yr) = MOD17 DN / 1000
```

MOD17 NPP is already expressed as carbon; no biomass-to-carbon factor applies.
The stock (tC) and the flux (tC/yr) have different dimensions and are reported
separately. A cell's stock is its density × *w* × its geodesic area.

### 5.2 Design-based estimation of district totals

Treating the *n* = 20,000 cells as a simple random sample of *N* = 66,700, the
total of a cell quantity *y* has the design-unbiased expansion estimator with a
finite-population-corrected standard error (Cochran, 1977):

```
T̂ = N · ȳ        SE(T̂) = N · √[(1 − n/N) · s²_y / n]
```

For soil, a better estimator is available. The mapped soil area
A = Σ *w* × area is known exactly for every cell, because bulk density was
extracted everywhere. The SOC total is therefore estimated as R̂ × A, where
R̂ = Σ stock / Σ soil area over the sample is the ratio estimator of mean density
with its linearised standard error; SE(T̂) = A × SE(R̂). This uses the known
area and is about eight times more precise than the expansion estimator. NPP
uses the expansion estimator, because its domain is known only at sampled cells.
No predictive model enters the totals; the dilution repair is the only
adjustment. Five sensitivity variants test the soil estimator and repair, and
four test the NPP conversion (Section 6).

### 5.3 Per-cell map

Sampled cells carry their own values. The 46,700 unsampled cells are filled by
inverse-distance weighting (8 nearest sampled cells, power 2). Because the
sample is a random 30% of the grid, the cells being filled are interleaved with
the sample; random-fold cross-validation approximates that prediction geometry
and suits this purpose (Wadoux et al., 2021). It is slightly pessimistic,
because each fold trains on 80% of the sample. Every value
carries a source label (`observed`, `interpolated`, `no soil data`). The map is
for display; totals come from Section 5.2.

### 5.4 Independent check on MOD17

Carbon passing through the district's rice and wheat crops was computed from
reported yields with IPCC (2019) Vol. 4 Table 11.1a factors:

```
crop NPP (tC/ha) = yield × dry-matter fraction × (1 + residue:yield) × (1 + root:shoot) × carbon fraction
```

with dry-matter fraction 0.89, residue:yield 1.3 (wheat) and 1.4 (rice),
root:shoot 0.23 ± 41% and 0.16 ± 35%, and carbon fraction uniform on
0.42–0.47. Yields carry a 10% relative SD and residue ratios 20%, propagated by
Monte Carlo (20,000 draws). This counts carbon in grain, residue and roots only,
so it is a lower bound on NPP.

### 5.5 Machine-learning experiment

Random forests (300 trees, minimum leaf 5) predict SOC from land class, terrain
and repaired texture and bulk density on undiluted cells, and NPP from land
class, terrain, seasonal vegetation indices and 12 monthly NDVI composites (the
four position proxies excluded). Validation is five-fold cross-validation over
an 8 × 8 grid of geographic blocks (Roberts et al., 2017), against two
baselines: the training-fold mean, and a random forest given only coordinates.
Importance is permutation importance on held-out folds (Strobl et al., 2007).

### 5.6 System

| Component | Technology | Role |
|---|---|---|
| Extraction | Earth Engine Python API | `00_gee_extraction.ipynb` |
| Analysis | pandas, scikit-learn, SciPy, pyproj | notebooks 01–02, `config.py`, `estimators.py` |
| Spatial store | PostgreSQL + PostGIS | `grid_cells` polygons keyed by `cell_id`, GiST index |
| Document store | MongoDB | summary, metrics, NDVI, per-cell table |
| API | Flask | summary, metrics, NDVI, GeoJSON by sample or bounding box, paged cells |
| Frontend | Leaflet, Chart.js | home, map, analytics, model, explorer |

The API has three data modes: `files` reads the pipeline's `results/` directly
and needs no database; `local` and `cloud` read the databases and fall back to
the files on failure, reporting the source in every response.

---

## 6. Results

### 6.1 Soil organic carbon stock

| Quantity | Estimate | 95% CI |
|---|---|---|
| **SOC stock, 0–30 cm** | **4.549 MtC** | 4.546–4.552 |
| Mapped soil area (census) | 329,814 ha | — |
| Mean density over mapped soil | 13.79 tC/ha | 13.78–13.80 |

| Sensitivity variant | MtC | 95% CI |
|---|---|---|
| Ratio estimator × census soil area, all diluted cells repaired (headline) | 4.549 | 4.546–4.552 |
| Expansion estimator (ignores the known area) | 4.545 | 4.531–4.560 |
| Only cells with *w* ≥ 0.5 repaired, the rest dropped | 4.506 | 4.490–4.521 |
| All partially diluted cells dropped | 4.362 | 4.344–4.381 |
| No quality control (zeros averaged in) | 4.483 | 4.468–4.499 |

The mean density corresponds to about 3.06 g/kg (0.31%) organic carbon at
1.50 g/cm³, within the 0.2–0.6% reported for Punjab's cultivated soils. Without
quality control a diluted cell contributes *w*² rather than *w* of its stock, so
the total is 1.5% low; the difference is small only because few cells are
diluted. The dilution's main effect was on the apparent skill of the model, not
on the stock. The interval reflects sampling error only. It excludes known
biases — the unrecorded depth interval, no coarse-fragment correction, a grid
covering 94.7% of the district, and cells with BD 1.40–1.50 treated as
undiluted — and SoilGrids' own prediction uncertainty, which is larger.

### 6.2 Net primary production

| Quantity | Estimate | 95% CI |
|---|---|---|
| **MOD17 NPP flux, correctly scaled** | **0.295 MtC/yr** | 0.290–0.300 |
| Area inside the MOD17 domain | 304,063 ha | 302,592–305,533 |
| Mean rate | 0.971 tC/ha/yr | 0.956–0.986 |
| Agricultural cells: mean rate | 0.946 tC/ha/yr | |
| Agricultural cells with negative annual NPP | 19.8% | |

| Sensitivity variant | MtC/yr |
|---|---|
| DN / 1000, negatives kept (headline) | 0.295 |
| Negatives clipped to zero | 0.361 |
| Agricultural cells only | 0.265 |
| Old conversion DN / 100, negatives clipped | 3.610 |

### 6.3 MOD17 against crop yields

| | tC/ha per season (90% range) |
|---|---|
| Wheat | 5.55 (4.10–7.26) |
| Rice | 7.66 (5.72–9.97) |
| **District, rice + wheat** | **3.34 MtC/yr (2.70–4.07)** |

Correctly scaled MOD17 is 8.8% of this lower bound. Per hectare the gap is the
same: MOD17 averages 0.95 tC/ha/yr on agricultural cells, against at least
13.2 tC/ha/yr for one rice + wheat year. (The totals are not perfectly
comparable: the grid covers ~95% of the district, and the v1 MOD17 year is
unrecorded while yields are for 2023-24 and 2024.) Together with negative
annual NPP in a fifth of agricultural cells — implausible for fields that are
harvested twice a year — this shows that MOD17 substantially underestimates
productivity in this irrigated, double-cropped landscape. The earlier figure of
3.7 MtC/yr appeared plausible only because the missing scale factor multiplied
the underestimate by ten. The unit conversion is fixed by the product
specification; the appropriate response is to replace the product for this
purpose, not to adjust the conversion.

### 6.4 What machine learning adds

| Target | Method | R² | RMSE |
|---|---|---|---|
| SOC (g/kg; sd 0.187) | Random forest | 0.200 | 0.167 |
| | Coordinates only | 0.173 | 0.170 |
| | Training mean | −0.006 | 0.188 |
| NPP (gC/m²/yr; sd 122) | Random forest | 0.339 | 99.5 |
| | Coordinates only | 0.318 | 101.0 |
| | Training mean | −0.014 | 123.2 |
| SOC gap filling | IDW, random folds | 0.808 | 0.084 |
| NPP gap filling | IDW, random folds | 0.598 | 77.6 |

Under spatial validation, both models beat the mean but add only 0.02–0.03 R²
over position alone. The leading SOC predictors are bulk density, elevation and
texture; for NPP, elevation dominates, followed by August and October NDVI.
Interpolation from neighbouring sampled cells outperforms both models for
filling the map, as expected for smooth gridded products sampled at 30% density.

The originally published R² of 0.949 for SOC is matched (0.955 in the rebuild)
when the diluted cells are included, and vanishes when they are excluded
(Section 4.1). It measured the extraction defect. (Section 4.1 uses the
original settings, 200 trees and minimum leaf 2, giving 0.191 on clean cells;
the pipeline experiment above uses 300 trees and minimum leaf 5, giving 0.200.)

---

## 7. Discussion

**The defects were silent.** None raised an error. The SOC model looked
excellent, the NPP flux looked agronomically plausible, and the identifier
collisions looked like a minor export quirk. Each was found by asking whether a
number was consistent with the physics or with an independent source, not by
inspecting code.

**Validation choice matters, but so does what is validated.** Spatial
cross-validation was adopted early in this project and correctly reduced
inflated scores, yet it still reported 0.949 for SOC because the inflation came
from the data, not the split. Conversely, random-fold validation is the right
choice for the interpolation step because the prediction targets are
interleaved with the sample. The design should follow the use (Wadoux et al.,
2021).

**A model was not needed for the headline.** Once the sample was recognised as
random, a survey estimator produced the totals with a stated standard error and
no modelling assumptions. Machine learning is retained as an experiment whose
result — little skill beyond position — is informative in its own right.

---

## 8. Limitations

1. **No field measurements.** SOC values are SoilGrids predictions; their local
   accuracy in Ludhiana is unknown, and their uncertainty is not propagated.
2. **Depth and coarse fragments (v1).** The SoilGrids interval behind the v1
   export is unrecorded and coarse fragments were not removed.
3. **Boundary.** The grid covers 94.7% of the Census area and is not clipped to
   an official boundary.
4. **NPP product.** MOD17 is not fit for crop flux here (Section 6.3). The
   yield-based estimate covers only rice and wheat and is a lower bound.
5. **NDVI attribution.** NDVI is attributed by an identifier that collides for
   4,269 cells; those cells carry no NDVI.
6. **Not a credit quantity.** The study establishes no baseline, change over
   time, additionality or permanence. For cropland soil carbon credits the
   relevant Verra methodology is VM0042 (Improved Agricultural Land
   Management), which requires soil sampling.

---

## 9. Re-extraction and further work

`notebooks/00_gee_extraction.ipynb` re-extracts every layer with masking applied
before reduction and the valid fraction exported per cell; generates the grid
from the district boundary with an in-district fraction per cell; computes
thickness-weighted 0–30 cm SoilGrids values, removes coarse fragments and
exports SoilGrids' own 0–30 cm stock as a cross-check; scales MOD17 inside Earth
Engine; and replaces the undocumented NDVI with Sentinel-2 monthly composites
and clear-observation counts. It refuses inputs that fail physical checks. The
pipeline then runs as a census of every cell and needs neither the sample nor
interpolation. Further work, in order of value:

1. Run the re-extraction (requires an Earth Engine account).
2. Propagate SoilGrids uncertainty from its published quantile layers.
3. Replace MOD17 for crop flux with the yield-based estimate or a crop-specific
   light-use-efficiency model.
4. Validate SoilGrids locally against any available soil-test data.

---

## 10. Conclusions

The 0–30 cm soil organic carbon stock of the Ludhiana grid is 4.55 MtC
(13.8 tC/ha over mapped soil), estimated without a predictive model from a
random sample of repaired SoilGrids values and the census soil area. MOD17 NPP, correctly scaled, is 0.30 MtC/yr, an order
of magnitude below the 3.3 MtC/yr lower bound implied by the district's crop
yields; the product is unsuitable for crop flux in this landscape. The
machine-learning models that originally appeared to predict soil carbon with
R² ≈ 0.95 were learning an extraction defect; on clean data they add little
beyond geographic position. The main contribution of the project is a
reproducible demonstration of how ordinary extraction choices can produce
convincing but meaningless results, and a pipeline that checks for them.

---

## References

Breiman, L. (2001). Random forests. *Machine Learning*, 45, 5–32.

Cochran, W. G. (1977). *Sampling Techniques* (3rd ed.). Wiley.

IPCC (2019). *2019 Refinement to the 2006 IPCC Guidelines for National
Greenhouse Gas Inventories*, Volume 4, Chapter 11, Table 11.1a.

ISRIC (n.d.). SoilGrids — frequently asked questions (units and conversion
factors). https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html

Google Earth Engine Data Catalog (n.d.). MOD17A3HGF.061: Terra Net Primary
Production Gap-Filled Yearly Global 500 m.
https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD17A3HGF

Ploton, P., et al. (2020). Spatial validation reveals poor predictive
performance of large-scale ecological mapping models. *Nature Communications*,
11, 4540.

Poggio, L., de Sousa, L. M., Batjes, N. H., Heuvelink, G. B. M., Kempen, B.,
Ribeiro, E., & Rossiter, D. (2021). SoilGrids 2.0: producing soil information
for the globe with quantified spatial uncertainty. *SOIL*, 7, 217–240.

Roberts, D. R., et al. (2017). Cross-validation strategies for data with
temporal, spatial, hierarchical, or phylogenetic structure. *Ecography*, 40,
913–929.

Running, S. W., & Zhao, M. (2021). *MODIS/Terra Net Primary Production
Gap-Filled Yearly L4 Global 500 m SIN Grid V061*. NASA LP DAAC.

Strobl, C., Boulesteix, A.-L., Zeileis, A., & Hothorn, T. (2007). Bias in random
forest variable importance measures. *BMC Bioinformatics*, 8, 25.

The Tribune (2024, 23 April). Wheat harvesting in Ludhiana district (2023-24
area and yield). https://epaper.tribuneindia.com/r/3858221

The Tribune (2025, 5 January). Paddy yield, production hit five-year low in
Ludhiana. https://www.tribuneindia.com/news/ludhiana/paddy-yield-production-hit-5-year-low-down-7-8-per-cent-from-2023/amp

Verra (2023). VM0042 Methodology for Improved Agricultural Land Management,
v2.0. https://verra.org/verra-releases-revised-methodology-for-improved-agricultural-land-management/

Wadoux, A. M. J.-C., Heuvelink, G. B. M., de Bruin, S., & Brus, D. J. (2021).
Spatial cross-validation is not the right way to evaluate map accuracy.
*Ecological Modelling*, 457, 109692.

`[FILL IN: verify page numbers and DOIs against the publications; add Punjab
soil-carbon literature for the 0.2–0.6% range]`

---

## Appendix A — Reproduction

See `README.md`. Every number in this report is in `results/district_summary.json`,
`results/model_metrics.json` or `results/audit_findings.json`; the notebooks that
write them are `02_carbon_pipeline.ipynb` and `01_data_audit.ipynb`.

## Appendix B — Dashboard

`[FILL IN: screenshots of the home, map, analytics, model and explorer pages]`
