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
import pydeck as pdk
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


# ── Page ─────────────────────────────────────────────────────────
hero_text, hero_map = st.columns([3, 2], gap="large", vertical_alignment="center")
with hero_text:
    st.title("How much carbon is in Ludhiana's topsoil?")
    st.html(f'<p class="lede">About <b>{STOCK:.1f} million tonnes</b> in the top 30 cm. SoilGrids allows '
            f'{LO:.0f} to {HI:.0f}, and it probably runs high.</p>' if LO else
            f'<p class="lede">About <b>{STOCK:.1f} million tonnes</b> in the top 30 cm.</p>')
    st.html('<p class="quiet">A cell-by-cell census of a global soil model. Read it as a map product, '
            'not a measurement.</p>')
with hero_map:
    hero_url, _ = raster("soc_stock_tc_ha", "soil", 26, 36)
    st.html(f'<figure style="margin:0"><img src="{hero_url}" alt="Map of soil carbon stock across Ludhiana district; '
            f'darker is more carbon, blank areas are the city and rivers" style="width:100%;aspect-ratio:{hero_aspect():.3f}">'
            f'<figcaption class="quiet">Soil carbon, 26 to 36 t/ha from light to dark. The pale gap is Ludhiana city.'
            f'</figcaption></figure>')

tab_stock, tab_map, tab_crop, tab_method, tab_data = st.tabs(
    ["Stock", "Map", "Crop productivity", "How it was made", "Download"])

with tab_stock:
    st.iframe(uncertainty_strip(), height=160,                     # our own HTML, built from results/
              alt=f"Census {STOCK:.1f} Mt inside SoilGrids' 90% range {LO:.1f} to {HI:.1f} Mt")
    st.html(f'<p class="quiet">Million tonnes of carbon in the top 30 cm. The census total is {STOCK:.1f} Mt; '
            f'SoilGrids\' own 90% prediction interval, summed with fully correlated errors, runs from {LO:.1f} to {HI:.1f} Mt.</p>')
    st.html(f"""<div class="facts">
      <div class="fact"><b>{soil['mean_density_tc_ha']['estimate']:.1f} t/ha</b><span>average over {soil['soil_area_ha']['estimate']:,} ha of soil
        (built-up land and water excluded)</span></div>
      <div class="fact"><b>{CENSUS:.1f} Mt</b><span>using the Census 2011 district boundary instead of geoBoundaries</span></div>
      <div class="fact"><b>{len(cells):,} cells</b><span>250 m squares, each weighted by its share inside the district</span></div>
    </div>""")
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
        a_ = shc["all"]
        imp = shc["implied_stock_mtc"]
        st.markdown(
            f"At {a_['samples']:,} Soil Health Card points in Ludhiana, lab organic carbon has a median of "
            f"{a_['shc_oc_g_kg_median_corrected']:.1f} g/kg after the standard Walkley-Black correction, against "
            f"{a_['soilgrids_soc_030_g_kg_median']:.1f} g/kg from SoilGrids at the same cells: SoilGrids is "
            f"{a_['median_ratio_soilgrids_over_shc_corrected']:.2f} times higher. Scaling the census by that ratio gives "
            f"about {imp['scaled_to_shc_corrected']:.1f} Mt, still an upper bound because the tests sample only the top 15 cm.")
    st.markdown("**Earlier benchmark.**" if shc else "")
    st.markdown(
        "Soil-test records put Punjab's average topsoil organic carbon at 4.0 g/kg in 2005-06 (Benbi & Brar, 2009). "
        "SoilGrids implies about 6.9 g/kg here over a deeper layer, where carbon is normally lower. The comparison "
        "is coarse, but it points the same way as the wide interval: field samples are needed before this number "
        "supports any decision, and it is not a carbon-credit quantity.")

with tab_map:
    layer = st.radio("Show", ["Soil carbon stock", "Crop productivity (MOD17)", "Cropland share"],
                     horizontal=True, label_visibility="collapsed")
    spec = {"Soil carbon stock": ("soc_stock_tc_ha", "soil", 26, 36, "t C/ha, 0 to 30 cm"),
            "Crop productivity (MOD17)": ("npp_flux_tc_ha_yr", "crop", 0, 2, "t C/ha/yr"),
            "Cropland share": ("cropland_frac", "crop", 0, 1, "share of cell")}[layer]
    url, b = raster(*spec[:4])
    view = pdk.ViewState(latitude=30.83, longitude=75.86, zoom=9.1, pitch=0)
    deck = pdk.Deck(
        layers=[
            pdk.Layer("BitmapLayer", image=pdk.types.String(url), bounds=b, opacity=0.92),
            pdk.Layer("GeoJsonLayer", boundary, stroked=True, filled=False, get_line_color=[42, 35, 28, 200],
                      line_width_min_pixels=1.4),
        ],
        initial_view_state=view, map_provider="carto", map_style=pdk.map_styles.CARTO_LIGHT_NO_LABELS)
    st.pydeck_chart(deck, height=560)
    ramp = SOIL_RAMP if spec[1] == "soil" else CROP_RAMP
    breaks = np.linspace(spec[2], spec[3], 5)
    fmt = (lambda v: f"{v:.0%}") if spec[0] == "cropland_frac" else (lambda v: f"{v:g}")
    st.html(f'<div class="legend"><div><i style="background:linear-gradient(90deg,{",".join(ramp)})"></i>'
            f'<small>{"".join(f"<span>{fmt(round(v, 2))}</span>" for v in breaks)}</small></div>'
            f'<span>{spec[4]}. Values outside the range take the end colour; blank cells have no data.</span></div>')

    st.subheader("Look up a place")
    towns = {"Ludhiana city": (30.901, 75.857), "Khanna": (30.705, 76.222), "Jagraon": (30.789, 75.473),
             "Samrala": (30.837, 76.191), "Raikot": (30.650, 75.600), "Doraha": (30.800, 76.023),
             "Machhiwara": (30.918, 76.198), "Mullanpur Dakha": (30.858, 75.687)}
    col1, col2, col3 = st.columns([2, 1, 1])
    town = col1.selectbox("Town", list(towns), index=1)
    lat = col2.number_input("Latitude", value=towns[town][0], format="%.4f", step=0.005)
    lon = col3.number_input("Longitude", value=towns[town][1], format="%.4f", step=0.005)
    cell = nearest_cell(cells, lat, lon)
    soc = cell["soc_stock_tc_ha"]
    st.html(f"""<div class="facts">
      <div class="fact"><b>{'No data' if pd.isna(soc) else f'{soc:.1f} t/ha'}</b><span>soil carbon stock, 0 to 30 cm
        {'(no soil data: built-up or water)' if pd.isna(soc) else ''}</span></div>
      <div class="fact"><b>{'No data' if pd.isna(cell['npp_flux_tc_ha_yr']) else f"{cell['npp_flux_tc_ha_yr']:.2f}"}</b><span>MOD17 net primary
        production, t C/ha/yr</span></div>
      <div class="fact"><b>{cell['cropland_frac']:.0%}</b><span>cropland (ESA WorldCover 2021) in cell {cell['cell_id']}</span></div>
    </div>""")
    st.caption("Town coordinates are approximate. Basemap © CARTO, © OpenStreetMap contributors.")

with tab_crop:
    st.subheader("The satellite product misses most of the crop carbon")
    lo_c, hi_c = crop["total_mtc_p05_p95"]
    fig = go.Figure()
    fig.add_bar(y=["Rice + wheat, from reported yields", "MOD17 satellite estimate (2024)"],
                x=[crop["total_mtc_median"], npp["flux_mtc_per_year"]["estimate"]],
                orientation="h", marker_color=[CROP, CANAL], marker_cornerradius=4, width=0.38,
                error_x=dict(type="data", array=[hi_c - crop["total_mtc_median"], 0],
                             arrayminus=[crop["total_mtc_median"] - lo_c, 0], color=MUTED, thickness=1.2),
                text=[f"{crop['total_mtc_median']:.2f} Mt/yr (at least)", f"{npp['flux_mtc_per_year']['estimate']:.2f} Mt/yr"],
                textposition=["inside", "outside"], insidetextanchor="start", textfont=dict(color=[SILT, INK]), cliponaxis=False,
                hovertemplate="%{y}: %{x:.2f} Mt C per year<extra></extra>")
    fig.update_layout(height=230, margin=dict(l=0, r=90, t=10, b=30), paper_bgcolor=SILT, plot_bgcolor=SILT,
                      font=dict(family="Public Sans, sans-serif", color=INK), showlegend=False,
                      xaxis=dict(title="Million tonnes of carbon per year", gridcolor="#D3CEC1", zeroline=False),
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.markdown(
        f"Carbon in harvested grain, straw and roots of Ludhiana's rice and wheat, from reported yields and IPCC "
        f"(2019) factors, is at least {crop['total_mtc_median']:.1f} Mt per year. MODIS MOD17, correctly scaled, "
        f"reports {npp['flux_mtc_per_year']['estimate']:.2f} Mt: about {crop['mod17_over_crop_ratio']:.0%} of that "
        "lower bound. MOD17 is not fit for crop carbon flux in this irrigated, double-cropped district.")

    st.subheader("Two growing seasons a year")
    peak = ndvi.loc[ndvi["median_ndvi"].idxmax()]
    st.html(f'<p class="quiet">Median greenness across the district rises twice: with rice in the monsoon and with wheat '
            f'through winter, peaking at {peak["median_ndvi"]:.2f} in {peak["month"]}. Low points mark harvest and the '
            f'residue-burning window.</p>')
    nd = ndvi.sort_values("sort_order")
    f2 = go.Figure(go.Scatter(x=nd["month"], y=nd["median_ndvi"], mode="lines+markers",
                              line=dict(color=CROP, width=2), marker=dict(size=8, color=CROP, line=dict(color=SILT, width=2)),
                              hovertemplate="%{x}: NDVI %{y:.2f}<extra></extra>"))
    for season, x0, x1 in [("Kharif (rice)", -0.4, 4.5), ("Rabi (wheat)", 4.5, 10.5)]:
        f2.add_vrect(x0=x0, x1=x1, fillcolor=CROP if "Rabi" in season else OCHRE, opacity=0.07, line_width=0,
                     annotation_text=season, annotation_position="top left",
                     annotation_font=dict(color=MUTED, size=12))
    f2.update_layout(height=300, margin=dict(l=0, r=10, t=30, b=30), paper_bgcolor=SILT, plot_bgcolor=SILT,
                     font=dict(family="Public Sans, sans-serif", color=INK),
                     yaxis=dict(title="Median NDVI (Sentinel-2)", gridcolor="#D3CEC1", range=[0, 0.9]),
                     xaxis=dict(gridcolor=SILT))
    st.plotly_chart(f2, width="stretch", config={"displayModeBar": False})

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
- The soil column was a stock read as a concentration (see the Stock tab).
""")
    st.markdown(f"The code and notebooks are on [GitHub]({REPO}), with the full [audit]({REPO}/blob/main/docs/AUDIT.md) "
                f"and the [project report]({REPO}/blob/main/docs/REPORT.md).")

with tab_data:
    st.subheader("Download the results")
    st.markdown("Every figure on this site comes from these files, written by `notebooks/02_carbon_pipeline.ipynb`.")
    show = cells[["cell_id", "lat", "lon", "soc_stock_tc_ha", "soc_stock_tc", "npp_flux_tc_ha_yr",
                  "cropland_frac", "soil_status"]]
    st.dataframe(show.head(200), width="stretch", hide_index=True,
                 column_config={"soc_stock_tc_ha": st.column_config.NumberColumn("Soil C (t/ha)", format="%.1f"),
                                "soc_stock_tc": st.column_config.NumberColumn("Soil C in cell (t)", format="%.0f"),
                                "npp_flux_tc_ha_yr": st.column_config.NumberColumn("MOD17 NPP (t/ha/yr)", format="%.2f"),
                                "cropland_frac": st.column_config.NumberColumn("Cropland share", format="%.2f")})
    c1, c2 = st.columns(2)
    c1.download_button("Download all cells (CSV)", show.to_csv(index=False).encode(), "ludhiana_carbon_cells.csv",
                       "text/csv", width="stretch")
    c2.download_button("Download district summary (JSON)", json.dumps(summary, indent=2).encode(),
                       "district_summary.json", "application/json", width="stretch")

st.html(f'<p class="quiet" style="margin-top:3rem">Made by Sathwik Ramaka for the M.Sc. Agriculture Analytics '
        f'programme of DAU, AAU and IIRS-ISRO. Data from ISRIC SoilGrids 2.0, NASA MODIS MOD17A3HGF, ESA WorldCover, '
        f'Copernicus Sentinel-2 and geoBoundaries; results last run {summary["run_date"]}.</p>')
