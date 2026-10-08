"""Ludhiana soil carbon: public Streamlit app.

Reads only what the pipeline wrote to results/ (and the district boundaries).
It never computes a published number, so it cannot drift from the report.

Run locally:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
BOUNDARIES = ROOT / "data" / "boundaries"
REPO = "https://github.com/sathwikramaka/carbon-stock-estimation-ludhiana"
GRID_STEP_DEG = 0.002245788210302635

# Earth palette (validated: dataviz validate_palette.js, light mode on silt surface)
SILT, PANEL, INK, MUTED = "#E7E6DF", "#F1F0EA", "#2A231C", "#6B6257"
SOIL, CROP, CANAL, OCHRE = "#8F4E1C", "#3F8A35", "#1F67A8", "#A97A0E"
SOIL_RAMP = ["#EFE6D4", "#D9C29C", "#B98F5E", "#8F5F33", "#5E3B1D", "#36210F"]   # light -> dark, one hue
CROP_RAMP = ["#EEF1E2", "#C9DBA6", "#97BE6E", "#629A42", "#3A7228", "#1F4A16"]

st.set_page_config(page_title="Ludhiana soil carbon", page_icon="🌾", layout="wide",
                   initial_sidebar_state="collapsed")


# ── Data ─────────────────────────────────────────────────────────
@st.cache_data
def load():
    summary = json.loads((RESULTS / "district_summary.json").read_text())
    unc_path = RESULTS / "soilgrids_uncertainty.json"
    unc = json.loads(unc_path.read_text()) if unc_path.exists() else None
    ndvi = pd.DataFrame(json.loads((RESULTS / "ndvi_monthly.json").read_text()))
    cells = pd.read_parquet(RESULTS / "carbon_cells.parquet")
    boundary = json.loads((BOUNDARIES / "ludhiana_geoboundaries_adm2.geojson").read_text())
    return summary, unc, ndvi, cells, boundary


def ramp_rgba(values: np.ndarray, ramp: list[str], lo: float, hi: float) -> np.ndarray:
    """Map values to RGBA with a stepped-interpolated ramp; NaN -> transparent."""
    stops = np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in ramp], dtype=float)
    missing = np.isnan(values)
    t = np.clip((np.where(missing, lo, values) - lo) / (hi - lo), 0, 1) * (len(ramp) - 1)
    i = np.clip(np.floor(t).astype(int), 0, len(ramp) - 2)
    f = (t - i)[..., None]
    rgb = stops[i] * (1 - f) + stops[i + 1] * f
    alpha = np.where(missing, 0, 235)[..., None]
    return np.concatenate([rgb, alpha], axis=-1).astype(np.uint8)


@st.cache_data
def raster(column: str, ramp_name: str, lo: float, hi: float):
    """Exact 250 m lattice image of one column, as a data URL plus its lon/lat bounds."""
    cells = load()[3]
    r, c = cells["grid_row"].to_numpy(), cells["grid_col"].to_numpy()
    r0, c0 = r.min(), c.min()
    img = np.full((r.max() - r0 + 1, c.max() - c0 + 1), np.nan, dtype=float)
    vals = cells[column].to_numpy(dtype=float)
    vals = np.where(cells["cell_area_ha"].to_numpy() > 0, vals, np.nan)      # outside the district: blank
    img[r - r0, c - c0] = vals
    rgba = ramp_rgba(img[::-1], SOIL_RAMP if ramp_name == "soil" else CROP_RAMP, lo, hi)  # north up
    buf = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(buf, format="PNG", optimize=True)
    url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    bounds = [c0 * GRID_STEP_DEG, r0 * GRID_STEP_DEG, (c.max() + 1) * GRID_STEP_DEG, (r.max() + 1) * GRID_STEP_DEG]
    return url, bounds


def hero_aspect() -> float:
    """Width/height of the district on the ground: a degree of longitude is cos(lat) of a degree of latitude."""
    cells = load()[3]
    cols = cells["grid_col"].max() - cells["grid_col"].min() + 1
    rows = cells["grid_row"].max() - cells["grid_row"].min() + 1
    return cols * np.cos(np.radians(cells["lat"].mean())) / rows


def nearest_cell(cells: pd.DataFrame, lat: float, lon: float) -> pd.Series:
    d = (cells["lat"] - lat) ** 2 + ((cells["lon"] - lon) * np.cos(np.radians(lat))) ** 2
    return cells.loc[d.idxmin()]


# ── Style ────────────────────────────────────────────────────────
st.html(f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&family=Public+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  html, body, [class*="st-"], .stMarkdown, .stTabs button p {{ font-family: "Public Sans", system-ui, sans-serif; }}
  .stApp {{ background: {SILT}; }}
  #MainMenu, footer, header [data-testid="stToolbar"] {{ visibility: hidden; }}
  .block-container {{ padding-top: 2.2rem; max-width: 1180px; }}
  h1, h2, h3, h1 *, h2 *, h3 *, [data-testid="stHeading"] *, .serif {{ font-family: "Source Serif 4", Georgia, serif !important; color: {INK}; letter-spacing: -0.01em; }}
  h1 {{ font-weight: 600; font-size: clamp(2rem, 4.2vw, 3.1rem); line-height: 1.08; margin-bottom: .3rem; }}
  h2 {{ font-weight: 600; font-size: 1.55rem; margin-top: 1.4rem; }}
  p, li {{ color: {INK}; line-height: 1.6; max-width: 65ch; text-wrap: pretty; }}
  h1, h2, h3 {{ text-wrap: balance; }}
  body, .stApp {{ font-variant-numeric: tabular-nums; }}
  .lede {{ font-family: "Source Serif 4", Georgia, serif; font-size: 1.32rem; line-height: 1.5; max-width: 60ch; color: {INK}; }}
  .quiet {{ color: {MUTED}; font-size: .92rem; }}
  .stTabs [data-baseweb="tab-list"] {{ gap: 1.6rem; border-bottom: 1px solid #CFCBBE; }}
  .stTabs [data-baseweb="tab"] {{ padding: .4rem 0; background: transparent; }}
  .stTabs [aria-selected="true"] p {{ color: {INK}; font-weight: 600; }}
  .stTabs [data-baseweb="tab-highlight"] {{ background: {SOIL} !important; }}
  .facts {{ display: grid; grid-template-columns: 1.6fr 1.2fr 1fr; gap: 1.4rem 2.6rem; margin: 1.8rem 0 .8rem; }}
  .fact {{ border-top: 2px solid #CFC9BA; padding-top: .7rem; }}
  .fact:first-child {{ border-top-color: {SOIL}; }}
  @media (max-width: 768px) {{ .facts {{ grid-template-columns: 1fr; }} }}
  .fact b {{ display: block; font-family: "Source Serif 4", Georgia, serif; font-size: 1.9rem; font-weight: 600; color: {INK}; }}
  .fact span {{ color: {MUTED}; font-size: .93rem; }}
  [data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"],
  [data-testid="stSliderThumbValue"] * {{ white-space: nowrap !important; max-width: none !important; width: max-content; }}
  .kpis {{ display: grid; grid-template-columns: 1.5fr repeat(4, 1fr); gap: 1.2rem 2rem; margin: 1.4rem 0 .4rem; }}
  .kpi {{ border-top: 2px solid #CFC9BA; padding-top: .6rem; }}
  .kpi:first-child {{ border-top-color: {SOIL}; }}
  .kpi b {{ display: block; font-family: "Source Serif 4", Georgia, serif; font-size: 1.85rem; font-weight: 600; color: {INK}; }}
  .kpi span {{ display: block; color: {MUTED}; font-size: .9rem; line-height: 1.4; }}
  .kpi em {{ font-style: normal; color: #6E5108; font-weight: 600; }}
  @media (max-width: 900px) {{ .kpis {{ grid-template-columns: 1fr 1fr; }} }}
  .cellcard {{ background: {PANEL}; border-radius: 4px; padding: 1rem 1.2rem; }}
  .cellcard h4 {{ margin: 0 0 .5rem; font-family: "Source Serif 4", Georgia, serif; }}
  .cellcard table {{ width: 100%; border-collapse: collapse; font-size: .92rem; }}
  .cellcard td {{ padding: .3rem .4rem .3rem 0; border-bottom: 1px solid #E2DED3; vertical-align: top; }}
  .cellcard td:first-child {{ color: {MUTED}; width: 46%; }}
  .cellcard td:last-child {{ text-align: right; font-weight: 600; }}
  .legend {{ display: flex; align-items: flex-start; gap: 1rem; color: {MUTED}; font-size: .88rem; flex-wrap: wrap; }}
  .legend i {{ display: inline-block; width: 220px; height: 10px; border-radius: 4px; }}
  .legend small {{ display: flex; justify-content: space-between; width: 220px; }}
  a, a:visited {{ color: {SOIL}; text-underline-offset: 3px; }}
  :focus-visible {{ outline: 2px solid {SOIL}; outline-offset: 2px; }}
  .stTabs button {{ min-height: 44px; }}
</style>
""")

summary, unc, ndvi, cells, boundary = load()
soil, npp, crop = summary["soil"], summary["npp"], summary["crop_yield_crosscheck"]
STOCK = soil["stock_mtc"]["estimate"]
U = (unc or {}).get("ludhiana_geoboundaries_adm2", {})
LO, HI = U.get("correlated_90pct_mtc", [None, None])
REBUILT = next((v["estimate"] for v in soil.get("sensitivity", []) if v["variant"].startswith("Rebuilt")), None)
CENSUS = next((v["estimate"] for v in soil.get("sensitivity", []) if "census2011" in v["variant"]), None)
OLD = summary["previous_published"]["soil_stock_mtc"]


MOTION_ESM = "https://cdn.jsdelivr.net/npm/motion@13.3.0/+esm"     # pinned; >= 2 weeks old at build time


def uncertainty_strip() -> str:
    """The one bold element: where the census total sits inside what SoilGrids allows.

    Rendered in a components iframe so Motion can run. The band unfolds outward from the
    central estimate once, when scrolled into view; it is static under reduced motion and
    stays fully visible if the script cannot load.
    """
    axis_max = 30.0
    pct = lambda v: 100 * v / axis_max
    marks = [(OLD, "previously published"), (REBUILT, "rebuilt from SOC x density")]
    ticks = "".join(
        f'<div class="tick reveal" style="left:{pct(v):.2f}%"><span>{v:.1f}<em> {label}</em></span></div>'
        for v, label in marks if v)
    band = (f'<div class="band" style="left:{pct(LO):.2f}%;width:{pct(HI) - pct(LO):.2f}%"></div>'
            f'<div class="bandlabel reveal" style="left:{pct(LO):.2f}%">{LO:.1f}</div>'
            f'<div class="bandlabel reveal" style="left:{pct(HI):.2f}%">{HI:.1f}</div>') if LO else ""
    scale = "".join(f'<div class="scale" style="left:{pct(v):.2f}%">{v:g}</div>' for v in range(0, 31, 5))
    origin = (pct(STOCK) - pct(LO)) / (pct(HI) - pct(LO)) * 100 if LO else 50
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,600&family=Public+Sans:wght@400;600&display=swap" rel="stylesheet">
<script>document.documentElement.classList.add("js");
  setTimeout(() => document.documentElement.classList.remove("js"), 2500);   // never leave the data hidden</script>
<style>
  html, body {{ margin: 0; background: {SILT}; font-family: "Public Sans", system-ui, sans-serif; font-variant-numeric: tabular-nums; }}
  .strip {{ position: relative; height: 150px; margin: 0 18px 0 8px; }}
  .rail {{ position: absolute; top: 58px; left: 0; right: 0; height: 2px; background: #BDB7A8; }}
  .band {{ position: absolute; top: 46px; height: 26px; background: {OCHRE}26; border: 1px solid {OCHRE};
           border-radius: 4px; transform-origin: {origin:.2f}% 50%; }}
  .point {{ position: absolute; top: 40px; width: 4px; height: 38px; background: {SOIL}; border-radius: 2px;
            left: calc({pct(STOCK):.2f}% - 2px); }}
  .pointlabel {{ position: absolute; top: 2px; left: {pct(STOCK):.2f}%; transform: translateX(-50%); white-space: nowrap;
                 font-family: "Source Serif 4", Georgia, serif; font-size: 1.2rem; font-weight: 600; color: {SOIL}; }}
  .bandlabel {{ position: absolute; top: 80px; transform: translateX(-50%); font-size: .85rem; color: #6E5108; font-weight: 600; }}
  .tick {{ position: absolute; top: 52px; width: 1px; height: 14px; background: {MUTED}; }}
  .tick span {{ position: absolute; top: 46px; left: 0; transform: translateX(-50%); white-space: nowrap; font-size: .82rem; color: {MUTED}; }}
  .tick em {{ font-style: normal; }}
  .scale {{ position: absolute; top: 124px; transform: translateX(-50%); font-size: .78rem; color: #7A7266; }}
  .js .band, .js .reveal {{ opacity: 0; }}
  @media (max-width: 640px) {{ .tick em {{ display: none; }} .pointlabel {{ font-size: 1.05rem; }} }}
  @media (prefers-reduced-motion: reduce) {{ .js .band, .js .reveal {{ opacity: 1; }} }}
</style></head><body>
<div class="strip" role="img" aria-label="Census estimate {STOCK:.1f} million tonnes of carbon; SoilGrids 90 percent range {LO} to {HI} million tonnes; previously published {OLD}; rebuilt from SOC and bulk density {REBUILT}">
  <div class="rail"></div>{band}
  <div class="point"></div><div class="pointlabel">{STOCK:.1f} Mt</div>
  {ticks}{scale}
</div>
<script type="module">
  import {{ animate, inView, stagger, MotionGlobalConfig }} from "{MOTION_ESM}";
  const root = document.documentElement;
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) {{ MotionGlobalConfig.skipAnimations = true; root.classList.remove("js"); }}
  inView(".strip", () => {{
    animate(".band", {{ opacity: [0, 1], scaleX: [0.03, 1] }}, {{ type: "spring", stiffness: 70, damping: 18 }})
      .then(() => root.classList.remove("js"));
    animate(".reveal", {{ opacity: [0, 1], y: [6, 0] }}, {{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: stagger(0.08, {{ startDelay: 0.55 }}) }});
  }}, {{ amount: 0.6 }});
</script></body></html>"""


# ── Map helpers ──────────────────────────────────────────────────
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
BASEMAPS = {
    "Satellite": {"version": 8, "sources": {"esri": {"type": "raster", "tiles": [ESRI], "tileSize": 256,
                  "attribution": "Imagery © Esri, Maxar, Earthstar Geographics"}},
                  "layers": [{"id": "esri", "type": "raster", "source": "esri"}]},
    "Streets": "carto-voyager",
    "Plain": "carto-positron",
}
LAYERS = {   # column, ramp, colour range, unit, label
    "Soil carbon stock": ("soc_stock_tc_ha", "soil", 26, 36, "t C/ha", "Soil carbon, 0 to 30 cm"),
    "Crop productivity (MOD17)": ("npp_flux_tc_ha_yr", "crop", 0, 2, "t C/ha/yr", "MOD17 net primary production"),
    "Cropland share": ("cropland_frac", "crop", 0, 1, "share", "Cropland share of cell"),
}
TOWNS = {"Ludhiana city": (30.901, 75.857), "Khanna": (30.705, 76.222), "Jagraon": (30.789, 75.473),
         "Samrala": (30.837, 76.191), "Raikot": (30.650, 75.600), "Doraha": (30.800, 76.023),
         "Machhiwara": (30.918, 76.198), "Mullanpur Dakha": (30.858, 75.687), "Payal": (30.723, 76.069)}


def cell_geojson(df: pd.DataFrame) -> dict:
    """Exact lattice squares for a set of cells, keyed by cell_id."""
    s = GRID_STEP_DEG
    feats = []
    for cid, r, c in zip(df["cell_id"], df["grid_row"], df["grid_col"]):
        x0, y0 = c * s, r * s
        ring = [[x0, y0], [x0 + s, y0], [x0 + s, y0 + s], [x0, y0 + s], [x0, y0]]
        feats.append({"type": "Feature", "id": cid, "geometry": {"type": "Polygon", "coordinates": [ring]}})
    return {"type": "FeatureCollection", "features": feats}


def colorscale(ramp):
    return [[i / (len(ramp) - 1), c] for i, c in enumerate(ramp)]


def fmt_num(v, nd=2, suffix=""):
    return "no data" if pd.isna(v) else f"{v:,.{nd}f}{suffix}"


def cell_card(c: pd.Series) -> str:
    rows = [
        ("Cell", c["cell_id"]),
        ("Centre", f"{c['lat']:.4f} N, {c['lon']:.4f} E"),
        ("Area inside district", fmt_num(c["cell_area_ha"], 2, " ha")),
        ("Soil data", f"{c['soil_status']} ({fmt_num(c['w_soil'] * 100, 0, '%')} of cell)"),
        ("Soil carbon stock, 0 to 30 cm", fmt_num(c["soc_stock_tc_ha"], 1, " t C/ha")),
        ("Soil carbon in this cell", fmt_num(c["soc_stock_tc"], 0, " t C")),
        ("Soil organic carbon content", fmt_num(c["soc_gkg"], 2, " g/kg")),
        ("Bulk density", fmt_num(c["bd_gcm3_rec"], 2, " g/cm³")),
        ("MOD17 NPP (2024)", fmt_num(c["npp_flux_tc_ha_yr"], 3, " t C/ha/yr")),
        ("NPP in this cell", fmt_num(c["npp_flux_tc_yr"], 1, " t C/yr")),
        ("Cropland / built-up", f"{fmt_num(c['cropland_frac'] * 100, 0, '%')} / {fmt_num(c['builtup_frac'] * 100, 0, '%')}"),
        ("Elevation, slope", f"{fmt_num(c['DEM_mean'], 0, ' m')}, {fmt_num(c['Slope_mean'], 1, '°')}"),
        ("Value sources", f"soil {c['soc_source']}; NPP {c['npp_source']}"),
    ]
    body = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return f'<div class="cellcard"><h4>Cell {c["cell_id"]}</h4><table>{body}</table></div>'


def themed(fig, height):
    fig.update_layout(height=height, paper_bgcolor=SILT, plot_bgcolor=SILT,
                      font=dict(family="Public Sans, sans-serif", color=INK),
                      hoverlabel=dict(bgcolor=PANEL, font=dict(family="Public Sans, sans-serif", color=INK)))
    return fig


# ── Page ─────────────────────────────────────────────────────────
hero_text, hero_map = st.columns([3, 2], gap="large", vertical_alignment="center")
with hero_text:
    st.title("How much carbon is in Ludhiana's topsoil?")
    st.html(f'<p class="lede">About <b>{STOCK:.1f} million tonnes</b> in the top 30 cm. SoilGrids allows '
            f'{LO:.0f} to {HI:.0f}, and it probably runs high.</p>' if LO else
            f'<p class="lede">About <b>{STOCK:.1f} million tonnes</b> in the top 30 cm.</p>')
    st.html('<p class="quiet">A cell-by-cell census of 71,197 grid cells from a global soil model. Open the map '
            'to inspect any cell, or filter all of them in the explorer.</p>')
with hero_map:
    hero_url, _ = raster("soc_stock_tc_ha", "soil", 26, 36)
    st.html(f'<figure style="margin:0"><img src="{hero_url}" alt="Map of soil carbon stock across Ludhiana district; '
            f'darker is more carbon, blank areas are the city and rivers" style="width:100%;aspect-ratio:{hero_aspect():.3f}">'
            f'<figcaption class="quiet">Soil carbon, 26 to 36 t/ha from light to dark. The pale gap is Ludhiana city.'
            f'</figcaption></figure>')

tab_over, tab_map, tab_an, tab_ex, tab_method = st.tabs(["Overview", "Map", "Analytics", "Explorer", "Method"])

# Overview
with tab_over:
    rng = f'<em>SoilGrids 90%: {LO:.1f} to {HI:.1f}</em>' if LO else ""
    st.html(f"""<div class="kpis">
      <div class="kpi"><b>{STOCK:.2f} Mt</b><span>soil organic carbon, 0 to 30 cm</span><span>{rng}</span></div>
      <div class="kpi"><b>{soil['mean_density_tc_ha']['estimate']:.1f}</b><span>t C/ha of soil, on average</span></div>
      <div class="kpi"><b>{npp['flux_mtc_per_year']['estimate']:.3f}</b><span>Mt C/yr, MOD17 NPP (2024)</span></div>
      <div class="kpi"><b>{crop['total_mtc_median']:.2f}</b><span>Mt C/yr at least, rice and wheat from yields</span></div>
      <div class="kpi"><b>{len(cells):,}</b><span>grid cells, 250 m</span></div>
    </div>""")
    st.iframe(uncertainty_strip(), height=160,                     # our own HTML, built from results/
              alt=f"Census {STOCK:.1f} Mt inside SoilGrids' 90% range {LO:.1f} to {HI:.1f} Mt")
    st.html(f'<p class="quiet">Million tonnes of carbon in the top 30 cm. The census total is {STOCK:.1f} Mt; '
            f'SoilGrids\' own 90% prediction interval, summed with fully correlated errors, runs from {LO:.1f} to {HI:.1f} Mt.</p>')

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.subheader("Why the earlier figure was less than half this")
        st.markdown(
            "The original export's soil column looked like carbon *content* but was SoilGrids' carbon *stock*, already "
            "in tonnes per hectare. Every earlier version multiplied it by bulk density and depth a second time, which "
            f"produced a plausible-looking {OLD:.1f} Mt. A fresh Earth Engine extraction matched the column to the stock "
            "layer exactly (r = 0.96, ratio 1.00).")
        shc_path = RESULTS / "shc_validation.json"
        shc = json.loads(shc_path.read_text()) if shc_path.exists() else None
        st.subheader("Checked against soil tests" if shc else "Why it may still be too high")
        if shc:
            a_, imp = shc["all"], shc["implied_stock_mtc"]
            st.markdown(
                f"At {a_['samples']:,} Soil Health Card points in Ludhiana, lab organic carbon has a median of "
                f"{a_['shc_oc_g_kg_median_corrected']:.1f} g/kg after the standard Walkley-Black correction, against "
                f"{a_['soilgrids_soc_030_g_kg_median']:.1f} g/kg from SoilGrids at the same cells: SoilGrids is "
                f"{a_['median_ratio_soilgrids_over_shc_corrected']:.2f} times higher. Scaling the census by that ratio "
                f"gives about {imp['scaled_to_shc_corrected']:.1f} Mt, still an upper bound because the tests sample "
                "only the top 15 cm.")
        st.markdown(
            "Soil-test records put Punjab's average topsoil organic carbon at 4.0 g/kg in 2005-06 (Benbi & Brar, 2009). "
            "SoilGrids implies about 6.9 g/kg here over a deeper layer, where carbon is normally lower. Field samples "
            "are needed before this number supports any decision, and it is not a carbon-credit quantity.")
    with right:
        st.subheader("What changed from the first version")
        prev = summary["previous_published"]
        changes = pd.DataFrame({
            "Quantity": ["Soil carbon stock (Mt)", "MOD17 NPP (Mt C/yr)", "Soil model R² (spatial)", "Grid cells"],
            "Before": [f"{prev['soil_stock_mtc']:.2f}", f"{prev['npp_flux_mtc_per_year']:.2f}",
                       f"{prev['soc_r2_spatial']:.2f}", f"{prev['cells']:,}"],
            "Now": [f"{STOCK:.2f}", f"{npp['flux_mtc_per_year']['estimate']:.3f}", "not needed", f"{len(cells):,}"],
        })
        st.dataframe(changes, hide_index=True, width="stretch")
        st.caption("The old R² of 0.95 came from a data defect; every cell is now observed, so no model is used.")

# Map
with tab_map:
    c1, c2, c3 = st.columns([2.2, 1.2, 1.6])
    layer = c1.radio("Colour cells by", list(LAYERS), horizontal=True)
    base = c2.radio("Basemap", list(BASEMAPS), horizontal=True)
    town = c3.selectbox("Go to", ["Whole district"] + list(TOWNS) + ["Custom point"], index=4)
    if town == "Custom point":
        cc1, cc2 = st.columns(2)
        clat = cc1.number_input("Latitude", value=30.85, format="%.4f", step=0.005, min_value=30.4, max_value=31.2)
        clon = cc2.number_input("Longitude", value=75.90, format="%.4f", step=0.005, min_value=75.2, max_value=76.5)
    elif town == "Whole district":
        clat, clon = 30.83, 75.86
    else:
        clat, clon = TOWNS[town]
    radius = st.slider("Show individual cells within (km)", 1.0, 6.0, 3.0, 0.5,
                       help="The whole district is always shown as a colour layer; inside this radius every 250 m "
                            "cell is drawn so you can hover or click it.")
    col, ramp_name, lo, hi, unit, label = LAYERS[layer]
    ramp = SOIL_RAMP if ramp_name == "soil" else CROP_RAMP

    dy = (cells["lat"] - clat) * 111.0
    dx = (cells["lon"] - clon) * 111.0 * np.cos(np.radians(clat))
    overview = town == "Whole district"
    near = cells.iloc[0:0] if overview else cells[(dx ** 2 + dy ** 2 <= radius ** 2) & (cells["cell_area_ha"] > 0)].copy()
    url, b = raster(col, ramp_name, lo, hi)

    custom = np.stack([near["soc_stock_tc_ha"], near["npp_flux_tc_ha_yr"], near["cropland_frac"] * 100,
                       near["soil_status"], near["soc_stock_tc"]], axis=-1)
    trace = go.Choroplethmap(
        geojson=cell_geojson(near), locations=near["cell_id"], featureidkey="id", z=near[col],
        zmin=lo, zmax=hi, colorscale=colorscale(ramp), marker_opacity=0.78,
        marker_line_width=0.6, marker_line_color="rgba(255,255,255,0.55)", customdata=custom,
        colorbar=dict(title=dict(text=unit, side="right"), thickness=12, len=0.6, outlinewidth=0,
                      tickformat=".0%" if col == "cropland_frac" else None),
        hovertemplate=("<b>%{location}</b><br>Soil carbon %{customdata[0]:.1f} t C/ha"
                       "<br>Carbon in cell %{customdata[4]:,.0f} t<br>MOD17 NPP %{customdata[1]:.2f} t C/ha/yr"
                       "<br>Cropland %{customdata[2]:.0f}%<br>Soil data: %{customdata[3]}<extra></extra>"))
    fig = go.Figure(trace)
    fig.update_layout(
        map=dict(style=BASEMAPS[base], center=dict(lat=clat, lon=clon), zoom=8.9 if overview else 12.2 - 0.25 * (radius - 3),
                 layers=[dict(sourcetype="image", source=url, opacity=0.75 if overview else 0.3, below="traces",
                              coordinates=[[b[0], b[3]], [b[2], b[3]], [b[2], b[1]], [b[0], b[1]]])]),
        margin=dict(l=0, r=0, t=0, b=0), clickmode="event+select")
    themed(fig, 600)
    m_left, m_right = st.columns([2.5, 1.5], gap="medium")
    with m_left:
        event = st.plotly_chart(fig, width="stretch", on_select="rerun", selection_mode="points", key="cellmap",
                                config={"scrollZoom": True, "displaylogo": False,
                                        "modeBarButtonsToRemove": ["select2d", "lasso2d"]})
    picked = None
    try:
        pts = event.selection.points if event and event.selection else []
        if pts:
            picked = pts[0].get("location") or near.iloc[pts[0]["point_index"]]["cell_id"]
    except Exception:
        picked = None
    with m_right:
        if picked is None and overview:
            st.html('<p class="quiet">The whole district is shown as a colour layer. Choose a town or a custom '
                    'point above to draw every 250 m cell there; then hover or click a cell for its numbers.</p>')
        elif picked is None:
            d = (dx ** 2 + dy ** 2).where(cells["soc_stock_tc_ha"].notna())     # nearest cell that has soil data
            picked = cells.loc[d.idxmin(), "cell_id"]
            st.caption("Click any cell on the map to see its full record. Showing the cell nearest the chosen point.")
        if picked is not None:
            st.html(cell_card(cells[cells["cell_id"] == picked].iloc[0]))
            st.caption(f"{len(near):,} cells drawn within {radius:g} km. Colours: {label.lower()}, {unit}.")
    st.caption("Imagery © Esri, Maxar, Earthstar Geographics. Street maps © CARTO, © OpenStreetMap contributors. "
               "Town coordinates are approximate.")

# Analytics
with tab_an:
    a1, a2 = st.columns(2, gap="large")
    with a1:
        st.subheader("Soil stock: how much each choice matters")
        sens = pd.DataFrame(soil.get("sensitivity", []))
        if not sens.empty:
            sens = sens.rename(columns={"variant": "Variant", "estimate": "Mt C"})[["Variant", "Mt C"]]
            sens["Mt C"] = sens["Mt C"].map(lambda v: f"{v:.2f}")
            sens["Variant"] = sens["Variant"].map(lambda v: (
                "geoBoundaries district boundary (headline)" if "geoboundaries" in v else
                "Census 2011 district boundary" if "census2011" in v else
                "Rebuilt from SOC x bulk density x 30 cm" if v.startswith("Rebuilt") else v))
            if LO:
                sens.loc[len(sens)] = ["SoilGrids 90% interval, correlated errors", f"{LO:.1f} to {HI:.1f}"]
            st.dataframe(sens, hide_index=True, width="stretch",
                         column_config={"Variant": st.column_config.TextColumn(width="large"),
                                        "Mt C": st.column_config.TextColumn(width="small")})
        st.caption("Boundary choice moves the total by 3%; the soil model itself is the large uncertainty.")
    with a2:
        st.subheader("Crop carbon from reported yields")
        pc = crop["per_crop"]
        st.dataframe(pd.DataFrame({
            "Crop": ["Wheat", "Rice"],
            "Area (ha)": [f"{crop['inputs']['wheat']['area_ha']:,}", f"{crop['inputs']['rice']['area_ha']:,}"],
            "Yield (t/ha)": [crop["inputs"]["wheat"]["yield_t_ha"], crop["inputs"]["rice"]["yield_t_ha"]],
            "Carbon (t C/ha per season)": [f"{pc['wheat']['tc_ha_median']:.2f}", f"{pc['rice']['tc_ha_median']:.2f}"],
        }), hide_index=True, width="stretch")
        st.caption("IPCC (2019) Vol. 4 Table 11.1a factors; grain, straw and roots only, so a lower bound on NPP.")

    st.subheader("The satellite product misses most of the crop carbon")
    lo_c, hi_c = crop["total_mtc_p05_p95"]
    fig = go.Figure()
    fig.add_bar(y=["Rice + wheat, from reported yields", "MOD17 satellite estimate (2024)"],
                x=[crop["total_mtc_median"], npp["flux_mtc_per_year"]["estimate"]],
                orientation="h", marker_color=[CROP, CANAL], marker_cornerradius=4, width=0.38,
                error_x=dict(type="data", array=[hi_c - crop["total_mtc_median"], 0],
                             arrayminus=[crop["total_mtc_median"] - lo_c, 0], color=MUTED, thickness=1.2),
                text=[f"{crop['total_mtc_median']:.2f} Mt/yr (at least)", f"{npp['flux_mtc_per_year']['estimate']:.2f} Mt/yr"],
                textposition=["inside", "outside"], insidetextanchor="start", textfont=dict(color=[SILT, INK]),
                cliponaxis=False, hovertemplate="%{y}: %{x:.2f} Mt C per year<extra></extra>")
    fig.update_layout(margin=dict(l=0, r=90, t=10, b=30), showlegend=False,
                      xaxis=dict(title="Million tonnes of carbon per year", gridcolor="#D3CEC1", zeroline=False),
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(themed(fig, 230), width="stretch", config={"displayModeBar": False})
    st.markdown(
        f"MODIS MOD17, correctly scaled, reports {npp['flux_mtc_per_year']['estimate']:.2f} Mt per year: about "
        f"{crop['mod17_over_crop_ratio']:.0%} of the {crop['total_mtc_median']:.1f} Mt that demonstrably passes through "
        "the district's rice and wheat. It is not fit for crop carbon flux in this irrigated, double-cropped district.")

    st.subheader("Two growing seasons a year")
    peak = ndvi.loc[ndvi["median_ndvi"].idxmax()]
    st.html(f'<p class="quiet">Median greenness rises twice: with rice in the monsoon and with wheat through winter, '
            f'peaking at {peak["median_ndvi"]:.2f} in {peak["month"]}. Low points mark harvest and the residue-burning window.</p>')
    nd = ndvi.sort_values("sort_order")
    f2 = go.Figure(go.Scatter(x=nd["month"], y=nd["median_ndvi"], mode="lines+markers",
                              line=dict(color=CROP, width=2), marker=dict(size=8, color=CROP, line=dict(color=SILT, width=2)),
                              hovertemplate="%{x}: NDVI %{y:.2f}<extra></extra>"))
    for season, x0, x1 in [("Kharif (rice)", -0.4, 4.5), ("Rabi (wheat)", 4.5, 10.5)]:
        f2.add_vrect(x0=x0, x1=x1, fillcolor=CROP if "Rabi" in season else OCHRE, opacity=0.07, line_width=0,
                     annotation_text=season, annotation_position="top left", annotation_font=dict(color=MUTED, size=12))
    f2.update_layout(margin=dict(l=0, r=10, t=30, b=30),
                     yaxis=dict(title="Median NDVI (Sentinel-2)", gridcolor="#D3CEC1", range=[0, 0.9]),
                     xaxis=dict(gridcolor=SILT))
    st.plotly_chart(themed(f2, 300), width="stretch", config={"displayModeBar": False})

# Explorer
with tab_ex:
    st.subheader("Every cell, filterable")
    e1, e2, e3, e4 = st.columns([1.3, 1.6, 1.6, 1.2])
    q = e1.text_input("Cell id contains", placeholder="r13608_c33")
    soc_valid = cells["soc_stock_tc_ha"].dropna()
    soc_rng = e2.slider("Soil carbon (t C/ha)", float(np.floor(soc_valid.min())), float(np.ceil(soc_valid.max())),
                        (float(np.floor(soc_valid.min())), float(np.ceil(soc_valid.max()))), 0.5)
    npp_rng = e3.slider("MOD17 NPP (t C/ha/yr)", 0.0, float(np.ceil(cells["npp_flux_tc_ha_yr"].max() * 10) / 10),
                        (0.0, float(np.ceil(cells["npp_flux_tc_ha_yr"].max() * 10) / 10)), 0.05)
    crop_min = e4.slider("Cropland at least", 0, 100, 0, 5, format="%d%%")
    status = st.multiselect("Soil data", sorted(cells["soil_status"].dropna().unique()),
                            default=sorted(cells["soil_status"].dropna().unique()))
    inside = st.toggle("Only cells inside the district", value=True)

    f = cells
    if inside:
        f = f[f["cell_area_ha"] > 0]
    if q:
        f = f[f["cell_id"].str.contains(q.strip(), regex=False)]
    f = f[f["soil_status"].isin(status)]
    f = f[f["soc_stock_tc_ha"].between(*soc_rng) | (f["soc_stock_tc_ha"].isna() & (soc_rng == (
        float(np.floor(soc_valid.min())), float(np.ceil(soc_valid.max())))))]
    f = f[f["npp_flux_tc_ha_yr"].between(*npp_rng) | f["npp_flux_tc_ha_yr"].isna()]
    f = f[f["cropland_frac"] * 100 >= crop_min]

    st.html(f"""<div class="kpis">
      <div class="kpi"><b>{len(f):,}</b><span>cells match</span></div>
      <div class="kpi"><b>{f['soc_stock_tc'].sum() / 1e6:.3f}</b><span>Mt soil carbon in them</span></div>
      <div class="kpi"><b>{fmt_num(f['soc_stock_tc_ha'].mean(), 1)}</b><span>mean t C/ha</span></div>
      <div class="kpi"><b>{fmt_num(f['npp_flux_tc_ha_yr'].mean(), 2)}</b><span>mean MOD17 t C/ha/yr</span></div>
      <div class="kpi"><b>{fmt_num(f['cell_area_ha'].sum(), 0)}</b><span>ha inside the district</span></div>
    </div>""")
    view = f[["cell_id", "lat", "lon", "cell_area_ha", "soil_status", "soc_stock_tc_ha", "soc_stock_tc", "soc_gkg",
              "bd_gcm3_rec", "npp_flux_tc_ha_yr", "npp_flux_tc_yr", "cropland_frac", "builtup_frac", "DEM_mean",
              "soc_source", "npp_source"]]
    st.dataframe(view, hide_index=True, width="stretch", height=420, column_config={
        "cell_id": "Cell", "lat": st.column_config.NumberColumn("Lat", format="%.4f"),
        "lon": st.column_config.NumberColumn("Lon", format="%.4f"),
        "cell_area_ha": st.column_config.NumberColumn("Area in district (ha)", format="%.2f"),
        "soil_status": "Soil data",
        "soc_stock_tc_ha": st.column_config.NumberColumn("Soil C (t/ha)", format="%.1f"),
        "soc_stock_tc": st.column_config.NumberColumn("Soil C in cell (t)", format="%.0f"),
        "soc_gkg": st.column_config.NumberColumn("SOC (g/kg)", format="%.2f"),
        "bd_gcm3_rec": st.column_config.NumberColumn("Bulk density", format="%.2f"),
        "npp_flux_tc_ha_yr": st.column_config.NumberColumn("NPP (t C/ha/yr)", format="%.3f"),
        "npp_flux_tc_yr": st.column_config.NumberColumn("NPP in cell (t/yr)", format="%.1f"),
        "cropland_frac": st.column_config.ProgressColumn("Cropland", format="percent", min_value=0, max_value=1),
        "builtup_frac": st.column_config.NumberColumn("Built-up", format="percent"),
        "DEM_mean": st.column_config.NumberColumn("Elevation (m)", format="%.0f"),
        "soc_source": "Soil source", "npp_source": "NPP source"})
    st.download_button(f"Download these {len(f):,} cells (CSV)", view.to_csv(index=False).encode(),
                       "ludhiana_cells_filtered.csv", "text/csv")

    g1, g2 = st.columns(2, gap="large")
    with g1:
        h = go.Figure(go.Histogram(x=f["soc_stock_tc_ha"].dropna(), nbinsx=40, marker_color=SOIL,
                                   marker_line=dict(color=SILT, width=1),
                                   hovertemplate="%{x} t C/ha: %{y:,} cells<extra></extra>"))
        h.update_layout(title=dict(text="Soil carbon across the selected cells", font=dict(size=15)),
                        margin=dict(l=0, r=10, t=40, b=30), bargap=0.05,
                        xaxis=dict(title="t C/ha, 0 to 30 cm", gridcolor=SILT), yaxis=dict(title="cells", gridcolor="#D3CEC1"))
        st.plotly_chart(themed(h, 320), width="stretch", config={"displayModeBar": False})
    with g2:
        smp = f.dropna(subset=["soc_stock_tc_ha", "npp_flux_tc_ha_yr"])
        smp = smp.sample(min(len(smp), 4000), random_state=1) if len(smp) else smp
        sc = go.Figure(go.Scattergl(x=smp["npp_flux_tc_ha_yr"], y=smp["soc_stock_tc_ha"], mode="markers",
                                    marker=dict(size=5, color=smp["cropland_frac"], colorscale=colorscale(CROP_RAMP),
                                                cmin=0, cmax=1, opacity=0.7,
                                                colorbar=dict(title="cropland", tickformat=".0%", thickness=10, outlinewidth=0)),
                                    customdata=smp["cell_id"],
                                    hovertemplate="%{customdata}<br>NPP %{x:.2f}, soil C %{y:.1f}<extra></extra>"))
        sc.update_layout(title=dict(text="Productivity against soil carbon (up to 4,000 cells)", font=dict(size=15)),
                         margin=dict(l=0, r=10, t=40, b=30),
                         xaxis=dict(title="MOD17 NPP, t C/ha/yr", gridcolor="#D3CEC1"),
                         yaxis=dict(title="Soil carbon, t C/ha", gridcolor="#D3CEC1"))
        st.plotly_chart(themed(sc, 320), width="stretch", config={"displayModeBar": False})

# Method
with tab_method:
    st.subheader("From satellite archive to district total")
    st.markdown(f"""
1. **Grid.** Every 250 m cell that touches the district, keyed by its position on a fixed lattice
   ({len(cells):,} cells), with the share of each cell inside the boundary.
2. **Extract.** Google Earth Engine averages each layer over the valid pixels in a cell: SoilGrids 2.0 carbon
   stock and soil properties, MODIS MOD17 net primary production (2024), ESA WorldCover, SRTM and Sentinel-2.
   Physical checks must pass before the table is written.
3. **Total.** Stock per cell = carbon density × valid-soil share × area inside the district, summed over every
   cell. No sample, no model.
4. **Uncertainty.** SoilGrids' published 5% and 95% layers, fetched on their native grid and summed.
5. **Check.** Crop carbon from reported yields; a Punjab soil-test benchmark; a database reload that must
   reproduce every total to the tonne.
""")
    st.subheader("What the audit found in the original project")
    st.markdown("""
- Masked soil pixels had been averaged as zeros, diluting every soil value; a model trained on them scored
  R² = 0.95 by learning the dilution. On clean cells it scores 0.20, barely above position alone.
- The cell identifier was a random number: 2,155 real cells were deleted as "duplicates".
- MOD17's scale factor was never applied, inflating crop productivity tenfold.
- The soil column was a stock read as a concentration (see the Overview).
""")
    st.markdown(f"The code and notebooks are on [GitHub]({REPO}), with the full [audit]({REPO}/blob/main/docs/AUDIT.md) "
                f"and the [project report]({REPO}/blob/main/docs/REPORT.md).")
    d1, d2 = st.columns(2)
    d1.download_button("Download all cells (CSV)", cells.to_csv(index=False).encode(),
                       "ludhiana_carbon_cells.csv", "text/csv", width="stretch")
    d2.download_button("Download district summary (JSON)", json.dumps(summary, indent=2).encode(),
                       "district_summary.json", "application/json", width="stretch")

st.html(f'<p class="quiet" style="margin-top:3rem">Made by Sathwik Ramaka for the M.Sc. Agriculture Analytics '
        f'programme of DAU, AAU and IIRS-ISRO. Data from ISRIC SoilGrids 2.0, NASA MODIS MOD17A3HGF, ESA WorldCover, '
        f'Copernicus Sentinel-2 and geoBoundaries; results last run {summary["run_date"]}.</p>')
