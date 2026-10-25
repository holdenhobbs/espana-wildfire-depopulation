"""Wildland-urban interface (Schug et al. 2023, Nature) per municipality.

The EU archive holds 100 km x 100 km tiles (10 m, Azimuthal Equidistant 'Equi7'-style grid).
Tile X{i}_Y{j}: xmin = i*100 km, ymax = 9,900 km - j*100 km (from datacube-definition.prj).
Only tiles overlapping the study regions are extracted, mosaicked and projected to EPSG:3035 (10 m, nearest).

Classes: 1 forest/shrub/wetland-dominated WUI intermix · 2 forest/shrub/wetland-dominated WUI interface
         3 grassland-dominated WUI intermix · 4 grassland-dominated WUI interface
         5 non-WUI forest/shrub/wetland · 6 non-WUI grassland · 7 non-WUI urban · 8 non-WUI other · 0 water
         (codes from the authors' map_wui.py in tabular_script_meta_data.zip; water is excluded from percentages)
Output: 02_analysis/wui_by_muni.csv  (pct of municipal area in each class + pct_wui_interface, pct_wui_intermix)
"""
import os
import zipfile

import arcpy
import pandas as pd
from arcpy.sa import TabulateArea

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "00_raw", "wui_schug")
PROC = os.path.join(ROOT, "01_processed")
GDB = os.path.join(PROC, "espana.gdb")
ANALYSIS = os.path.join(ROOT, "02_analysis")
TILE = 100_000
Y_TOP = 9_900_000

arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True
study = os.path.join(GDB, "study_munis")
regions = os.path.join(GDB, "study_regions")
# datacube-definition.prj isn't readable by arcpy, so take the spatial reference from a sample tile
tile_dir = os.path.join(RAW, "tiles_study")
os.makedirs(tile_dir, exist_ok=True)
sample = os.path.join(tile_dir, "_sample_WUI.tif")
if not os.path.exists(sample):
    with zipfile.ZipFile(os.path.join(RAW, "EU.zip")) as z, z.open("EU/X0074_Y0074/WUI.tif") as src, open(sample, "wb") as dst:
        dst.write(src.read())
wui_sr = arcpy.Describe(sample).spatialReference
print("WUI grid:", wui_sr.name)

# Which tiles intersect the study regions (test each candidate footprint against the real outlines)
regions_aeqd = os.path.join("memory", "regions_aeqd")
arcpy.management.Project(regions, regions_aeqd, wui_sr)
geoms = [g for (g,) in arcpy.da.SearchCursor(regions_aeqd, ["SHAPE@"])]
ext = arcpy.Describe(regions_aeqd).extent
tiles = []
for i in range(int(ext.XMin // TILE), int(ext.XMax // TILE) + 1):
    for j in range(int((Y_TOP - ext.YMax) // TILE), int((Y_TOP - ext.YMin) // TILE) + 1):
        x0, y1 = i * TILE, Y_TOP - j * TILE
        box = arcpy.Polygon(arcpy.Array([arcpy.Point(x0, y1 - TILE), arcpy.Point(x0, y1), arcpy.Point(x0 + TILE, y1),
                                         arcpy.Point(x0 + TILE, y1 - TILE)]), wui_sr)
        if any(not g.disjoint(box) for g in geoms):
            tiles.append(f"X{i:04d}_Y{j:04d}")
print("tiles needed:", len(tiles))

# Extract only those tiles
paths = []
with zipfile.ZipFile(os.path.join(RAW, "EU.zip")) as z:
    names = set(z.namelist())
    for t in tiles:
        member = f"EU/{t}/WUI.tif"
        if member not in names:
            continue  # ocean tile, not in the archive
        out = os.path.join(tile_dir, f"{t}_WUI.tif")
        if not os.path.exists(out):
            with z.open(member) as src, open(out, "wb") as dst:
                dst.write(src.read())
        paths.append(out)
print("tiles extracted:", len(paths))

# Mosaic, then project to EPSG:3035 at 10 m (nearest neighbour keeps class codes)
mosaic = os.path.join(PROC, "wui_study_aeqd.tif")
if not arcpy.Exists(mosaic):
    arcpy.management.MosaicToNewRaster(paths, PROC, "wui_study_aeqd.tif", wui_sr, "8_BIT_UNSIGNED", 10, 1)
wui = os.path.join(PROC, "wui_study_3035.tif")
if not arcpy.Exists(wui):
    arcpy.management.ProjectRaster(mosaic, wui, arcpy.SpatialReference(3035), "NEAREST", 10)

# Area of each class per municipality. Tabulated at 30 m: the 10 m mosaic is ~8 billion cells and takes 1h+;
# 30 m (nearest) gives the same municipal percentages within rounding, since even the smallest municipality has
# thousands of 30 m cells.
arcpy.env.cellSize = 30
tab = os.path.join(GDB, "wui_tabulate_30m")
if not arcpy.Exists(tab):
    TabulateArea(study, "ine_code", wui, "Value", tab, 30)
df = pd.DataFrame(arcpy.da.TableToNumPyArray(tab, "*")).rename(columns={"INE_CODE": "ine_code"}).set_index("ine_code")
vals = [c for c in df.columns if c.startswith("VALUE_") and c != "VALUE_0"]  # land only (0 = water)
total = df[vals].sum(axis=1)
out = pd.DataFrame(index=df.index)
for c in vals:
    out[f"pct_wui_class{c.split('_')[1]}"] = 100 * df[c] / total
for k in range(1, 9):
    if f"pct_wui_class{k}" not in out.columns:
        out[f"pct_wui_class{k}"] = 0.0
out["pct_wui_intermix"] = out["pct_wui_class1"] + out["pct_wui_class3"]
out["pct_wui_interface"] = out["pct_wui_class2"] + out["pct_wui_class4"]
out["pct_wui_any"] = out["pct_wui_intermix"] + out["pct_wui_interface"]
out.to_csv(os.path.join(ANALYSIS, "wui_by_muni.csv"))
print("municipalities:", len(out))
print(out[["pct_wui_intermix", "pct_wui_interface", "pct_wui_any"]].describe().round(2))
arcpy.management.Delete("memory")
