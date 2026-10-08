# Data dictionary

Provenance for the original sample exports is inferred from the data and
checked in `IIRS/Scrpit/01_data_quality.ipynb` (Q1–Q10). Census columns are
produced by `IIRS/Scrpit/00_gee_extraction.ipynb`, whose manifest records every
asset and parameter.

## Earth Engine sample exports (`IIRS/Carbon_Stocks/`)

| File | Rows | Key | Notes |
|---|---|---|---|
| `BGD_for_all_grids(GEOM).csv` | 66,700 | WKT → `cell_id` | soil and terrain for every cell; no SOC |
| `AGD_for_all_grids_geom.csv` | 66,700 | row-aligned with BGD | climate/vegetation for every cell; no NPP |
| `Below_Ground_Data_geom.csv` | 20,000 | WKT → `cell_id` | random sample of the grid, with SOC |
| `Above_ground_data_geom.csv` | 20,000 | row-aligned with the BG sample | same sample, with NPP |
| `ndvi_monthly_ludhiana_all_66790.csv` | 66,700 | `Grid_ID` only | no geometry; attributable for 62,431 cells |

| Column | Unit as stored | Source (inferred) | Notes |
|---|---|---|---|
| `Grid_ID` | — | `ee.Image.random`-type column | **not an identifier** (Q1) |
| `agri_class` | 0/1 | unknown classification | |
| `Ag/NonAg_m` | fraction | unknown | agricultural fraction of the cell |
| `DEM_mean`, `Slope_mean` | m, degrees | SRTM-like | |
| `sand_pct`, `clay_pct` | % | SoilGrids (÷10 applied in export) | diluted where `0 < bd < 1.40` (Q4) |
| `bd_gcm3` / `BD_g_cm3` | g/cm³ | SoilGrids `bdod` (÷100 applied) | diluted; used to estimate *w* |
| `SOC_mean` | **t/ha** | SoilGrids `ocs` 0–30 cm organic carbon **stock** (Q10) | not SOC content despite the name; diluted |
| `Agricultur` | MOD17 DN | MOD17A3HGF `Npp` | ×0.0001 kgC/m² (Q6); NaN outside product domain |
| `Kharif_Pre`, `Rabi_Preci` | mm | interpolated rainfall | position proxies (Q9) |
| `LST_Sept20`, `Rabi_LST_2` | °C | land-surface temperature | position proxies (Q9) |
| `Kharif_pea`, `Rabi_Peak_` | NDVI | seasonal peak NDVI | |
| `Kharif_Lud` (`NDWI_Khari` in AGD), `NDWI_Rabi_` | index | NDWI | |
| `NDVI_Jun24` … `NDVI_May25` | NDVI | monthly composite, sensor unrecorded | Aug 2024: 48% of rows missing in the file; 52% of grid cells lack a usable value once unattributable IDs are excluded |

## Boundaries (`IIRS/Carbon_Stocks/boundaries/`)

| File | Source | Licence | Area |
|---|---|---|---|
| `ludhiana_geoboundaries_adm2.geojson` | geoBoundaries gbOpen IND ADM2 | CC BY 4.0 | 369,961 ha (default) |
| `punjab_state_geoboundaries_adm1.geojson` | geoBoundaries gbOpen IND ADM1 | CC BY 4.0 | location map only |
| `punjab_districts_geoboundaries_adm2.geojson` | geoBoundaries gbOpen IND ADM2, 22 Punjab districts (pre-2021; no Malerkotla) | CC BY 4.0 | location map only |
| `ludhiana_census2011_datameet.geojson` | Datameet Census 2011 districts | ODbL | 358,482 ha (sensitivity) |

Both simplified at 0.0001° (~10 m); area change < 0.001%. Census 2011 reports 376,700 ha.

## Census table (`IIRS/Carbon_Stocks/v2/ludhiana_cells_v2.csv.gz`)

| Column | Unit | Source |
|---|---|---|
| `cell_id`, `grid_row`, `grid_col` | — | lattice position |
| `cell_area_ha`, `in_district_frac` | ha, fraction | geodesic area; share inside the default boundary |
| `in_ludhiana_geoboundaries_adm2`, `in_ludhiana_census2011_datameet` | fraction | share inside each boundary |
| `soc_030`, `bdod_030`, `sand_030`, `clay_030`, `cfvo_030` | g/kg, g/cm³, %, %, vol % | SoilGrids 2.0, thickness-weighted 0–30 cm |
| `ocs_030_t_ha` | t/ha | SoilGrids `ocs` 0–30 cm, mean over valid pixels — **the headline stock density** |
| `soil_valid_frac` | fraction | share of the cell with a SoilGrids value |
| `npp_gc_m2_yr`, `npp_qc`, `npp_valid_frac` | gC/m²/yr, %, fraction | MOD17A3HGF v6.1, scaled in Earth Engine |
| `cropland_frac`, `builtup_frac`, `water_frac`, `tree_frac` | fraction | ESA WorldCover 2021 |
| `dem_m`, `slope_deg` | m, degrees | SRTM 30 m |
| `NDVI_<MonYY>`, `nobs_<MonYY>` | NDVI, count | Sentinel-2 SR monthly median; clear observations |

## Results (`IIRS/Carbon_Stocks/results/`)

`carbon_cells.csv` — one row per cell:

| Column | Unit | Meaning |
|---|---|---|
| `cell_id` | — | key |
| `lon`, `lat`, `WKT` | degrees | centroid and polygon |
| `cell_area_ha` | ha | geodesic area (inside the boundary in census mode) |
| `soil_status`, `w_soil`, `w_reliable` | — , fraction, bool | full / partial / nodata; valid soil share; per-cell values divided by w are trusted (w ≥ 0.5) |
| `bd_gcm3_rec`, `soc_gkg` | g/cm³, g/kg | bulk density and SOC content (census: SoilGrids 0–30 cm; sample mode: BD / w, SOC content unavailable → empty) |
| `soc_source` | — | observed / interpolated / no soil data |
| `soc_stock_tc_ha` | tC/ha | SoilGrids `ocs` 0–30 cm per hectare of valid soil |
| `soc_stock_tc` | tC | `soc_stock_tc_ha × w_soil × cell_area_ha` |
| `npp_flux_tc_ha_yr`, `npp_flux_tc_yr` | tC/ha/yr, tC/yr | MOD17, DN × 0.0001 kgC/m² |
| `npp_source` | — | observed / interpolated / outside MOD17 domain |

`district_summary.json`, `model_metrics.json`, `ndvi_monthly.json`,
`data_quality.json` — see the notebook that writes each.

## Extra covariates (`IIRS/Carbon_Stocks/v2/ludhiana_cells_extra.csv.gz`, notebook 07)

| Column | Unit | Source |
|---|---|---|
| `npp_2020` … `npp_2024` | gC/m²/yr | MOD17A3HGF v6.1, each year |
| `vv_kharif`, `vh_kharif`, `vhvv_kharif`, `vv_rabi`, `vh_rabi`, `vhvv_rabi` | dB | Sentinel-1 GRD IW seasonal medians (kharif Jun–Oct 2024, rabi Nov 2024–Apr 2025) |
| `lst_kharif`, `lst_rabi`, `lst_annual` | °C | Landsat 8/9 C2 L2 surface temperature, cloud-masked medians |
| `par_<MonYY>` | MJ/m²/month | 0.48 × ERA5-Land monthly downward shortwave |

Per-cell model outputs added to `carbon_cells`: `npp_multiyear_gc_m2_yr` (2020–2024
mean), `npp_lue_tc_ha_yr` (crop light-use-efficiency NPP per ha of cropland, central
ε and CUE), `soc_model`/`npp_model` with `_q05`/`_q95` (quantile-forest mean and
90% interval).
