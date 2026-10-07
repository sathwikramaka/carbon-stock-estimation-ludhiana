"""
units_audit.py
==============
Checks whether the raw satellite and soil variables are in the units the
carbon formulas assume.

This matters more than any model score. A unit scaling error changes the
district carbon total by a factor of ten; a model score only changes how
confidently you describe the estimate.

For each variable the script prints the observed range and compares it to
the physically expected range for agricultural Punjab, then flags likely
scaling problems and shows what the corrected carbon totals would be.

Nothing is modified. This only reads and reports.

Usage (from the project root, with .venv active):
    python units_audit.py
"""

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

ROOT = Path(os.getenv("PROJECT_ROOT", SCRIPT_DIR))
DATA = ROOT / "IIRS" / "Carbon_Stocks"
OUT_FILE = DATA / "units_audit_report.txt"

NPP_COL = "Agricultur"
SOC_COL = "SOC_mean"
CELL_AREA_HA = 6.25

if not DATA.is_dir():
    sys.exit(f"Data folder not found: {DATA}\nCheck PROJECT_ROOT in .env")

lines = []


def say(text=""):
    print(text)
    lines.append(text)


def header(text):
    say()
    say("=" * 74)
    say(f"  {text}")
    say("=" * 74)


def describe(series, name, expected_lo, expected_hi, expected_unit, notes=""):
    """Print observed range against the expected physical range."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0:
        say(f"{name:<14} NOT FOUND")
        return None
    lo, hi, mean, med = s.min(), s.max(), s.mean(), s.median()
    say(f"{name}")
    say(f"   observed   min {lo:>12.4f}   max {hi:>12.4f}   "
        f"mean {mean:>12.4f}   median {med:>12.4f}")
    say(f"   expected   {expected_lo} to {expected_hi} {expected_unit}")

    ratio = mean / ((expected_lo + expected_hi) / 2)
    if 0.4 <= ratio <= 2.5:
        say("   VERDICT    consistent with the expected range")
    elif 5 <= ratio <= 20:
        say(f"   VERDICT    about {ratio:.0f}x too large -- likely a 10x unit "
            f"scaling issue")
    elif 50 <= ratio <= 200:
        say(f"   VERDICT    about {ratio:.0f}x too large -- likely a 100x unit "
            f"scaling issue")
    elif ratio > 2.5:
        say(f"   VERDICT    about {ratio:.1f}x larger than expected -- CHECK")
    else:
        say(f"   VERDICT    about {1/ratio:.1f}x smaller than expected -- CHECK")
    if notes:
        say(f"   note       {notes}")
    say()
    return mean


# ══════════════════════════════════════════════════════════════
header("LOADING")

bg = pd.read_csv(DATA / "Below_Ground_Data_geom.csv")
ag = pd.read_csv(DATA / "Above_ground_data_geom.csv")
bgd_all = pd.read_csv(DATA / "BGD_for_all_grids(GEOM).csv")
final = pd.read_csv(DATA / "carbon_all_66790_final.csv")

say(f"Training sample: {len(bg):,} cells")
say(f"Full district:   {len(final):,} cells")


# ══════════════════════════════════════════════════════════════
header("1. SOIL ORGANIC CARBON")

say("SoilGrids reports soil organic carbon in dg/kg, which is TEN TIMES the")
say("value in g/kg. The carbon formula assumes g/kg. Punjab cropland typically")
say("holds 0.2-0.6% organic carbon, which is 2 to 6 g/kg.")
say()

soc_mean = describe(
    bg[SOC_COL], SOC_COL, 2, 8, "g/kg",
    "if values sit around 20-60, they are dg/kg and must be divided by 10")


# ══════════════════════════════════════════════════════════════
header("2. BULK DENSITY")

say("SoilGrids reports bulk density in cg/cm3, which is 100x the value in")
say("g/cm3. Real agricultural topsoil is 1.2 to 1.7 g/cm3.")
say()

bd_col = "bd_gcm3" if "bd_gcm3" in bg.columns else "BD_g_cm3"
bd_mean = describe(
    bg[bd_col], bd_col, 1.2, 1.7, "g/cm3",
    "if values sit around 120-170, they are cg/cm3 and must be divided by 100")


# ══════════════════════════════════════════════════════════════
header("3. SOIL TEXTURE")

say("SoilGrids reports sand, silt and clay in g/kg, not percent. Punjab")
say("alluvial soils are typically 40-70% sand and 10-30% clay.")
say()

sand_mean = describe(bg["sand_pct"], "sand_pct", 40, 70, "%",
                     "if values sit around 400-700, they are g/kg")
clay_mean = describe(bg["clay_pct"], "clay_pct", 10, 30, "%",
                     "if values sit around 100-300, they are g/kg")

if sand_mean and clay_mean:
    total = sand_mean + clay_mean
    say(f"sand + clay = {total:.2f}")
    if 60 <= total <= 95:
        say("   Consistent with percentages; the remainder would be silt.")
    elif 600 <= total <= 950:
        say("   Consistent with g/kg; the remainder would be silt.")
    else:
        say("   Does not sum to a sensible texture total. The two layers may")
        say("   not be true texture fractions, which would also explain their")
        say("   positive correlation with each other.")


# ══════════════════════════════════════════════════════════════
header("4. NET PRIMARY PRODUCTIVITY")

say("MODIS NPP (MOD17A3) is reported in kgC/m2/yr, and is often rescaled to")
say("gC/m2/yr. Irrigated double-cropped Punjab reaches roughly 600-1200")
say("gC/m2/yr. Note that NPP is ALREADY carbon, so multiplying by the 0.47")
say("biomass-to-carbon fraction counts the conversion twice.")
say()

npp = ag[ag[NPP_COL] > 0][NPP_COL]
npp_mean = describe(npp, NPP_COL, 600, 1200, "gC/m2/yr",
                    "values near 1.0 would indicate kgC/m2/yr")


# ══════════════════════════════════════════════════════════════
header("5. GRID AREA VERSUS OFFICIAL DISTRICT AREA")

say("Ludhiana district covers 3,767 km2, which is 376,700 ha. If the grid")
say("extends past the district boundary, every total is inflated in proportion.")
say()

grid_ha = len(final) * CELL_AREA_HA
say(f"   grid cells        {len(final):,}")
say(f"   cell area         {CELL_AREA_HA} ha")
say(f"   grid area         {grid_ha:,.0f} ha  ({grid_ha / 100:,.0f} km2)")
say(f"   official area     376,700 ha  (3,767 km2)")
excess = 100 * (grid_ha - 376700) / 376700
say(f"   difference        {excess:+.1f}%")
say()
if abs(excess) > 5:
    say(f"   VERDICT    the grid covers {excess:+.1f}% more ground than the")
    say("              district. All district totals are inflated by roughly")
    say("              this amount unless cells outside the boundary are")
    say("              removed or the totals are area-corrected.")
else:
    say("   VERDICT    grid area is close to the official district area")


# ══════════════════════════════════════════════════════════════
header("6. WHAT THE CARBON TOTALS BECOME UNDER EACH CORRECTION")

t_ag = float(final["AGC_tC_ha"].sum()) * CELL_AREA_HA / 1e6
t_bg = float(final["BGC_tC_ha"].sum()) * CELL_AREA_HA / 1e6
t_all = t_ag + t_bg

say("Current reported figures")
say(f"   above-ground   {t_ag:>10.4f} MtC")
say(f"   below-ground   {t_bg:>10.4f} MtC")
say(f"   TOTAL          {t_all:>10.4f} MtC")
say()

bgc_density = float(final["BGC_tC_ha"].mean())
say(f"Below-ground density: {bgc_density:.2f} tC/ha over 0-30 cm")
say("Published values for Punjab cropland fall around 15-35 tC/ha.")
say()

say(f"{'scenario':<44}{'below-ground':>14}{'TOTAL':>12}")
say("-" * 72)
say(f"{'as currently calculated':<44}{t_bg:>13.4f}{t_all:>12.4f}")
say(f"{'if SOC is dg/kg (divide by 10)':<44}{t_bg/10:>13.4f}"
    f"{t_ag + t_bg/10:>12.4f}")
say(f"{'if SOC dg/kg AND bulk density cg/cm3':<44}{t_bg/1000:>13.4f}"
    f"{t_ag + t_bg/1000:>12.4f}")
if abs(excess) > 5:
    corrected = t_bg / 10 * (376700 / grid_ha)
    say(f"{'if SOC dg/kg AND area-corrected':<44}{corrected:>13.4f}"
        f"{t_ag * 376700/grid_ha + corrected:>12.4f}")

say()
say("Above-ground scenarios")
say(f"{'as currently calculated (NPP x 0.47)':<44}{t_ag:>13.4f}")
say(f"{'without the 0.47 factor (NPP is already C)':<44}{t_ag/0.47:>13.4f}")


# ══════════════════════════════════════════════════════════════
header("7. SANITY CHECK AGAINST PUBLISHED VALUES")

say("Reference points for Punjab agricultural land:")
say()
say("   Soil organic carbon, 0-30 cm    15 - 35 tC/ha")
say("   Soil organic carbon content     0.2 - 0.6 %  (2 - 6 g/kg)")
say("   Bulk density, topsoil           1.3 - 1.7 g/cm3")
say("   Annual NPP, irrigated cropland  600 - 1200 gC/m2/yr")
say("   Above-ground crop biomass C     2 - 6 tC/ha at peak, near zero")
say("                                   after harvest")
say()
say(f"Your below-ground density   {bgc_density:>8.2f} tC/ha")
ratio = bgc_density / 25
if ratio > 3:
    say(f"   That is about {ratio:.0f}x the middle of the published range.")
    say("   A unit scaling error is the most likely explanation.")
elif ratio > 1.5:
    say("   Higher than typical but within argument if the soil product")
    say("   disagrees with field surveys. Worth stating in the report.")
else:
    say("   Within the published range.")


# ══════════════════════════════════════════════════════════════
header("WHAT TO DO")

say("1. Open the Google Earth Engine script that produced these exports and")
say("   check the units documented for each band. SoilGrids in particular")
say("   uses dg/kg for organic carbon and cg/cm3 for bulk density.")
say()
say("2. If a scaling factor was missed, the fix is a single division applied")
say("   in the cleaning step. The models, the database and the website all")
say("   stay exactly as they are.")
say()
say("3. Decide how to treat the above-ground pool. NPP is an annual flux, not")
say("   a stock. Either rename it as annual carbon accumulation, or drop the")
say("   0.47 factor if the source band is already in carbon units, or exclude")
say("   above-ground entirely and report a soil carbon inventory.")
say()
say("4. If the grid extends beyond the district boundary, clip to the official")
say("   boundary or state the area difference alongside the total.")
say()
say("5. Whatever you find, report the reasoning. A corrected figure with a")
say("   documented unit audit is a stronger result than an uncorrected one.")

OUT_FILE.write_text("\n".join(lines), encoding="utf-8")
say()
say(f"Report saved to {OUT_FILE}")
