# Audit

Single record of every defect found in this project, its evidence, its fix and
its status. It replaces `DEFECT_LEDGER.md` and `REVIEW_FINDINGS.md` (kept in
`archive/` for history). Every number below is reproduced by
`notebooks/01_data_audit.ipynb` (written to `results/audit_findings.json`) or
`notebooks/02_carbon_pipeline.ipynb`, and each finding is guarded by a test in
`tests/`.

**Status key** — FIXED: corrected in code and verified. MITIGATED: the v1
interim pipeline works around it; the root cause is fixed by re-extraction
(`notebooks/00_gee_extraction.ipynb`). OPEN: needs data the repository does not
have.

| ID | Finding | Effect on published numbers | Status |
|---|---|---|---|
| F1 | Unmasked SoilGrids nodata diluted every soil band | SOC model R² 0.95 was an artefact; on clean cells 0.19–0.20 | MITIGATED |
| F2 | `Grid_ID` is a random integer, not a cell key | 2,155 real cells deleted; NDVI joined across unrelated cells | FIXED |
| F3 | MOD17 scale factor never applied | NPP flux 10× too high | FIXED |
| F4 | MOD17 is unfit for crop flux in this landscape | Corrected flux is ~9% of a yield-based lower bound | OPEN — product limitation |
| F5 | 500 m NPP target duplicated across 250 m cells | Random-split R² for NPP uninterpretable | FIXED (not used) |
| F6 | Four climate covariates are position proxies | Most NPP model skill was position | FIXED |
| F7 | SoilGrids depth interval unrecorded; no coarse-fragment term | Unknown bias in the stock | MITIGATED |
| F8 | Old de-duplication rule biased the grid | Removed the least-agricultural cells | FIXED |
| F9 | Grid not clipped to an official boundary | Grid covers 94.7% of the Census area | MITIGATED |
| F10 | Extraction script missing from the repository | Provenance of every input unverifiable | MITIGATED |
| F11 | Dashboard served hard-coded and stale figures | Values shown did not match any single run | FIXED |
| F12 | Root and backend `requirements.txt` were UTF-16 and Windows-pinned | Project not installable elsewhere | FIXED |
| F13 | First rebuild dropped cells with *w* < 0.5 from the soil total | Total biased low by ~0.9% | FIXED |

---

## F1 — Unmasked nodata diluted every soil band

**Evidence.** Every soil band has a minimum of exactly 0; in 773 of 20,000
sample rows sand, clay, bulk density and SOC are *all* 0. Undiluted bulk density
is near-constant (median 1.500, sd 0.024 g/cm³), yet 1,527 rows lie between 0
and 1.40. In those rows the *ratios* between bands are unchanged
(sand/BD 25.7 vs 24.9; SOC/BD 19.5 vs 20.5): each band was multiplied by the
same valid fraction *w*. 98.5% of the 782 zero-bulk-density sample cells are
non-agricultural (built-up, water) — exactly where SoilGrids has no prediction.

A shared multiplicative factor induces strong positive correlation between all
bands. Remove it and the physics returns:

| Pair | As extracted | Undiluted cells | After repair (value / *w*) |
|---|---|---|---|
| sand × clay | +0.839 | −0.674 | −0.677 |
| BD × SOC | +0.966 | −0.266 | −0.257 |
| clay × SOC | +0.950 | +0.325 | +0.339 |

**Consequence for the model** (random forest, 8 × 8 spatial blocks, 5 folds):

| Configuration | n | R² random | R² spatial | RMSE spatial (g/kg) |
|---|---|---|---|---|
| As extracted, 6 features | 20,000 | 0.968 | 0.955 | 0.163 |
| As extracted, bulk density alone | 20,000 | 0.951 | 0.950 | 0.172 |
| Undiluted, 6 features | 17,691 | 0.429 | **0.191** | 0.168 |
| Undiluted, bulk density alone | 17,691 | 0.115 | 0.092 | 0.178 |
| Undiluted, coordinates only | 17,691 | 0.774 | 0.158 | 0.172 |

RMSE barely moves while R² collapses: the high score came from variance the
dilution created, not from skill. (This table uses 200 trees and minimum leaf 2,
matching the original model; the pipeline's experiment uses 300 trees and
minimum leaf 5 and gives R² 0.200 against 0.173 for coordinates alone.)

**Fix.** v1: `config.soil_qc` classifies each cell full (BD ≥ 1.40), partial
(0 < BD < 1.40) or nodata (BD = 0) and repairs partial cells by `value / w`; no
cell is deleted, and totals use no predictive model. For a partial cell the
stock contribution is SOC_diluted × 1.50 × 3 × area — *w* cancels — so every
partial cell enters the totals. Only cells with *w* ≥ 0.5 serve as
interpolation sources, because their per-cell values are precise. v2: the extraction masks before reducing and
exports the valid fraction per cell.

**Retracted claims.** "The SOC target and predictors share SoilGrids provenance,
so R² = 0.95 measures product emulation" and "sand–clay +0.84 and BD–SOC +0.97
show SoilGrids is internally inconsistent" (README, project report §6.2,
DEFECT_LEDGER) are wrong. SoilGrids is consistent; the extraction was not.

## F2 — `Grid_ID` is a random integer

**Evidence.** 66,700 rows and 66,700 distinct polygons, but 64,545 distinct
IDs. Uniform draws from 10⁶ values predict 64,524 distinct; the multiplicity
spectrum matches Poisson (observed 62,431 / 2,075 / 37 / 2 against expected
62,396 / 2,081 / 46 / 1); IDs are uniform across [0, 10⁶). Example: ID 411542
labels two cells 37 km apart. The "duplicates" were never duplicates.

**Fix.** `cell_id = r{row}_c{col}` from each polygon's absolute lattice position
(`config.cell_key`), unique for all 66,700 cells and computed identically in
Earth Engine. `Grid_ID` survives only to attach the NDVI export, which has no
geometry, and only where the ID is unique (62,431 cells); the 4,269 ambiguous
cells get no NDVI rather than a wrong one.

**Retracted claims.** DEFECT_LEDGER H-01 ("byte-identical rows") and the
"Earth Engine export artefact" explanation in the old notebook.

## F3 — MOD17 scale factor never applied

**Evidence.** MOD17A3HGF stores `Npp` as integer DN with scale 0.0001 kgC/m²
(valid range −30,000 to 32,700). The `Agricultur` column is 77% exact integers,
range −3,687 to 2,846, median 1,203. The old pipeline treated DN as gC/m² and
divided by 100.

**Fix.** Flux (tC/ha/yr) = DN × 0.0001 × 10 = DN / 1000 (`config.NPP_DN_TO_TC_HA_YR`).
District flux 3.61 → **0.295 MtC/yr** (95% CI 0.290–0.300).

## F4 — MOD17 is unfit for crop flux here

**Evidence.** (a) An independent yield-based estimate — reported Ludhiana wheat
(245,200 ha at 5.0 t/ha, 2023-24) and paddy (256,600 ha at 7.014 t/ha, 2024)
converted with IPCC (2019) Vol. 4 Table 11.1a factors — puts at least
**3.34 MtC/yr** (90% range 2.70–4.07) through the two main crops. Correctly
scaled MOD17 is 8.8% of that lower bound. (b) MOD17 reports negative annual NPP
in 19.8% of agricultural cells with a value. These negatives are genuine
product values, not contamination: they are as often exact integers as
positives (0.73 vs 0.79), and beyond a single MODIS pixel (0.75–2 km) the
neighbours of negative cells are negative 39.5% of the time against an 18.7%
base rate. MOD17 fill classes (32,761–32,767) would push mixed values up, not
down.

Per hectare the gap is the same: MOD17 averages 0.95 tC/ha/yr on agricultural
cells against at least 13.2 tC/ha/yr for a rice + wheat year. The totals are not
perfectly comparable (the grid covers ~95% of the district; the v1 MOD17 year is
unrecorded while yields are for 2023-24 and 2024), but neither changes the
order of magnitude.

The old dashboard figure (3.71 MtC/yr) looked plausible only because the
skipped scale factor (F3) multiplied an underestimate by ten. The conversion is
fixed by the product specification and must not be adjusted to match
expectations; the product is what should be replaced.

**Correction to the earlier review.** The review document attributed the
negative tail to fill values (−30,000) mixed into cell means. That was wrong;
see the evidence above.

**Status.** OPEN. Options: report the yield-based estimate as the crop flux;
use a crop-specific light-use-efficiency model; or keep MOD17 strictly as a
relative index.

## F5 — Duplicated 500 m target

17,038 non-missing NPP rows hold only 7,378 distinct values; 73% of rows share
their exact target with another row, because up to four 250 m cells sit in one
500 m MODIS pixel. A random split leaks the test target into training. **Fix:**
only spatial-block validation is reported; NPP modelling is a methods
experiment and produces no published number.

## F6 — Climate covariates are position proxies

R² of each covariate from longitude/latitude alone: Kharif_Pre 0.9999,
LST_Sept20 0.9999, Rabi_Preci 0.9999, Rabi_LST_2 0.981. They are smooth
interpolated surfaces with no information at 250 m. **Fix:** excluded
(`config.POSITION_PROXIES`). Without them the NPP model reaches spatial R² 0.339
against 0.318 for coordinates alone.

## F7 — Depth interval and coarse fragments

SoilGrids has no 0–30 cm layer (intervals 0–5, 5–15, 15–30 cm). The v1 export
does not record which band was used. **v2 fix:** thickness-weighted 0–30 cm for
SOC and bulk density, coarse fragments from `cfvo`, and SoilGrids' own 0–30 cm
`ocs` stock exported as a cross-check (the validation step requires agreement
within 35%).

## F8 — The old de-duplication rule biased the grid

Keeping the highest `Ag/NonAg_m` row per `Grid_ID` deleted 2,155 real cells
whose mean agricultural fraction was 0.654, against 0.95 for the cells kept from
the same groups; 596 groups were decided by sort order alone. Grid area fell
from 356,894 to 345,364 ha. **Fix:** nothing is deleted.

## F9 — Boundary

The grid sums to 356,894 ha, 94.7% of the Census 2011 area (376,700 ha). Earlier
documents cited 403,406 ha (6.25 ha × 64,545) and 345,364 ha (after F8); both are
wrong.

Two open boundaries are now in `IIRS/Carbon_Stocks/boundaries/`: geoBoundaries
gbOpen ADM2 (369,961 ha; default) and Datameet Census 2011 (358,482 ha;
sensitivity). Against them the v1 grid covers only 93.0% and 96.2% of the
district, and 1,563 of its cells (11,971–12,706 ha) lie outside both. **v2
fix:** `config.build_grid_v2` generates 71,197 lattice cells touching either
boundary, with the fraction of each cell inside each; totals weight by it, and
the second boundary is reported as a sensitivity run.

## F10 — Missing extraction script

Nothing in the repository showed how any input was made. **Fix:**
`notebooks/00_gee_extraction.ipynb` documents and reproduces every layer, writes
a manifest, and refuses v2 inputs that fail physical checks.

## F11 — Dashboard figures

`app.py` returned a hard-coded `FALLBACK_SUMMARY` and `/api/metrics` never read
a database; `main.js` and `index.html` carried 4.3554, 3.7085, 0.9492, 64,545 and
others as fallbacks; `load_carbon()` keyed MongoDB documents by `int(Grid_ID)`,
so colliding IDs overwrote each other on the map. **Fix:** the backend serves
only what the pipeline wrote (`results/`) or the databases loaded from it; the
frontend has no numeric fallbacks; everything is keyed by `cell_id`. Tests
fail if any of the old figures reappear.

## F12 — Requirements

Both `requirements.txt` files were UTF-16 with a Windows-only `pywinpty` pin.
**Fix:** UTF-8, minimum versions, analysis and dashboard dependencies separated.

---

## What the numbers are now (v1 interim)

| Quantity | Previously published | Now |
|---|---|---|
| SOC stock 0–30 cm | 4.3554 MtC | **4.549 MtC** (95% CI 4.546–4.552, sampling error only) |
| Mean SOC density | 12.61 tC/ha | **13.79 tC/ha** of mapped soil (329,814 ha, census) |
| MOD17 NPP flux | 3.7085 MtC/yr | **0.295 MtC/yr** (95% CI 0.290–0.300) |
| Crop-yield NPP (independent) | — | **3.34 MtC/yr** (90% range 2.70–4.07), lower bound |
| SOC model spatial R² | 0.9492 | 0.200 (coordinates alone 0.173) — not used |
| Cells | 64,545 | 66,700 |

The soil stock rises 4.4%, mainly because no real cells are deleted (F8) and
diluted cells are repaired rather than counted at a fraction of their value. It
moves little because the stock is built from product values and few cells were
diluted. What collapses is the claim that a model predicts it. The confidence
interval covers sampling error only; it excludes the known biases above and
SoilGrids' own prediction uncertainty, which is much larger and not yet
propagated (its quantile layers are not on Earth Engine).

## F13 — First rebuild dropped low-*w* cells from the soil total

Found by an independent review of the rebuilt pipeline. Cells with *w* < 0.5
(696 sample rows) had been treated as no-data on the grounds that *w* is
imprecise there. But *w* cancels in a cell's stock, so excluding them only
removed real soil carbon: the total was 4.506 MtC, 0.9% low and outside its own
interval. **Fix:** all partial cells enter the totals; the old rule is kept as
a sensitivity variant. The same review moved the headline to the ratio
estimator × census soil area (SE 0.0017 MtC instead of 0.014), corrected a
denominator in the negative-NPP share, replaced a neighbour test that MODIS
pixel duplication could explain, and led to fixes in the dashboard (one MongoDB
client per process, correct source labels when a collection is empty, licensed
basemaps) and the extraction (terrain reduced at its native 30 m).

## Still open

1. Run `notebooks/00_gee_extraction.ipynb` (needs your Earth Engine account) to
   replace v1 interim figures with a census from clean inputs.
2. Propagate SoilGrids uncertainty (download the Q0.05/Q0.95 layers from ISRIC
   WCS for the district bounding box).
3. Decide how to report crop flux given F4.
4. Field samples, if any become available, to validate SoilGrids locally.
