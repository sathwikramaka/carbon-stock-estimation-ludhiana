<div align="center">

# 🌾 Carbon Stock Estimation — Ludhiana, Punjab

**How much carbon do Ludhiana's soils hold, and how much do its crops fix each year?**
A 250 m satellite-and-soil census of the whole district, with machine learning, uncertainty and a live dashboard.

[![Live dashboard](https://img.shields.io/badge/Live_dashboard-Open-00d4ff?style=for-the-badge&logo=streamlit&logoColor=white)](https://carbon-stock-estimation-ludhiana.streamlit.app/)
[![Report](https://img.shields.io/badge/Full_report-Read-00ff88?style=for-the-badge&logo=readthedocs&logoColor=white)](project_report.md)
[![Tests](https://img.shields.io/github/actions/workflow/status/sathwikramaka/carbon-stock-estimation-ludhiana/test.yml?branch=main&style=for-the-badge&label=tests)](https://github.com/sathwikramaka/carbon-stock-estimation-ludhiana/actions)

![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![Earth Engine](https://img.shields.io/badge/Google_Earth_Engine-4285F4?logo=google&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?logo=scikitlearn&logoColor=white)
![PostGIS](https://img.shields.io/badge/PostgreSQL_+_PostGIS-4169E1?logo=postgresql&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-47A248?logo=mongodb&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?logo=flask&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)

<img src="docs/screenshots/home.jpg" alt="Carbon Stock Intelligence dashboard" width="900">

</div>

---

## 📊 Key results

| | Result |
|---|---|
| 🟫 **Soil organic carbon stock (0–30 cm)** | **10.54 MtC** · 38.6 Mt CO₂e · 30.8 tC/ha |
| 📏 SoilGrids' own 90% range | 2.2 – 27.7 MtC |
| 🌱 **Crop carbon fixed per year** (two independent methods) | **3.34 – 3.89 MtC/yr** |
| 🛰️ What MODIS NPP reports | 0.34 MtC/yr — about 10% of the crop estimates |
| 🤖 **Random Forest accuracy** (spatial cross-validation) | **R² 0.55** NPP · **R² 0.45** SOC |
| 🗺️ Grid | 71,197 cells of 250 m, clipped to the district |

> Soil carbon is a **stock** (tonnes) and crop carbon a **flux** (tonnes per year) — they are reported separately, never added.

## 🔍 What makes it different

- **Every cell observed** — a census of the whole district, not a sample, with masked satellite pixels excluded before averaging.
- **Honest validation** — models are tested on held-out map blocks, so neighbouring cells never leak answers; 90% prediction intervals are checked (93% / 89% coverage).
- **Independent cross-checks** — MODIS productivity is tested against reported crop yields (IPCC 2019) and a crop light-use-efficiency model built from Sentinel-2 and ERA5.
- **Uncertainty shown, not hidden** — SoilGrids' own quantiles, two district boundaries and two routes to a soil stock.
- **Full data stack** — Earth Engine → notebooks → PostGIS + MongoDB → Flask API → dashboard, with 51 automated tests.

## 🛰️ Data

ISRIC **SoilGrids 2.0** · **MODIS** MOD17A3HGF (2020–2024) · **Sentinel-2** NDVI · **Sentinel-1** radar · **Landsat 8/9** temperature · **ESA WorldCover** · **SRTM** · **ERA5-Land** radiation · district crop statistics

## 🖥️ Dashboard

| Map | Analytics | Model |
|---|---|---|
| <img src="docs/screenshots/map.jpg" width="280"> | <img src="docs/screenshots/analytics.jpg" width="280"> | <img src="docs/screenshots/model.jpg" width="280"> |

Five pages — Home, Map (every 250 m cell, click to inspect), Analytics, Model, Explorer (search and export all cells).
**[Open the live dashboard →](https://carbon-stock-estimation-ludhiana.streamlit.app/)**

## 🚀 Run it yourself

```bash
python -m venv .venv
.venv\Scripts\activate              # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements-dev.txt
```

| Want to… | Do this |
|---|---|
| See the dashboard (no database needed) | Double-click `IIRS/Carbon_Stocks/carbon_project/run_dashboard.bat` → http://localhost:5000 |
| Reproduce the results | Run the notebooks in `IIRS/Scrpit/` in order (00 needs Earth Engine access) |
| Use the databases | Copy `.env.example` to `.env`, set `DB_MODE=local` and your passwords, run `03_publish_databases.ipynb` |
| Run the tests | `pytest tests/` |

<details>
<summary><b>Notebooks</b></summary>

| # | Notebook | What it does |
|---|---|---|
| 00 | `00_gee_extraction` | Extracts soil, NPP, land cover, terrain and NDVI for every cell from Earth Engine |
| 01 | `01_data_quality` | Unit and data-quality checks on the raw exports |
| 02 | `02_carbon_pipeline` | Carbon totals, uncertainty, crop cross-checks, Random Forest models — every published number |
| 03 | `03_publish_databases` | Loads results into PostGIS and MongoDB and verifies the totals |
| 04 | `04_location_map` | Location map |
| 05 | `05_soilgrids_uncertainty` | SoilGrids 90% interval for the stock |
| 06 | `06_shc_validation` | Soil Health Card validation and regression kriging (ready; needs the lab data) |
| 07 | `07_gee_extra_covariates` | Sentinel-1, Landsat temperature, ERA5 radiation, MODIS 2020–2024 |

</details>

<details>
<summary><b>Folder layout</b></summary>

```
IIRS/
  Carbon_Stocks/
    carbon_project/   Flask backend + dashboard frontend, run_dashboard.bat
    boundaries/       district boundaries
    v2/               Earth Engine census tables
    results/          every published number and figure
  Scrpit/             notebooks 00–07
app/                  public Streamlit version of the dashboard
docs/                 data dictionary, screenshots
tests/                automated tests
project_report.md     full report
```

</details>

<details>
<summary><b>Troubleshooting the database mode</b></summary>

The map footer shows where data came from (`data: local` or `data: files-fallback`). If it falls back, open
`http://localhost:5000/api/health` — it states the reason for each database — then re-run
`03_publish_databases.ipynb`, whose last cell stops with an error if a database was not loaded.

</details>

## ⚠️ Limitations

The soil figure is a SoilGrids estimate, not checked against field samples here (the Soil Health Card table is a paid download; the notebook is ready for it). MODIS NPP misses most crop productivity in this irrigated landscape. Details in the [report](project_report.md#7-limitations).

## 👤 Author

**Sathwik Ramaka** — M.Sc. Agriculture Analytics (DAU · AAU · IIRS-ISRO)
Big Data Analytics project, Indian Institute of Remote Sensing, Dehradun
[LinkedIn](https://www.linkedin.com/in/sathwikramaka/) · [GitHub](https://github.com/sathwikramaka)

<sub>MIT licence</sub>
