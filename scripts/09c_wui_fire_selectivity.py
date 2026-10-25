"""Where does fire burn relative to the wildland–urban interface? (RQ3)

For each region: share of the landscape in each WUI class vs share of 2001–2025 burned area in that class.
Selectivity ratio = burned share / landscape share  (>1 = burns more than its area would predict).
Burned area = union of ESFire30 perimeters 2001–2025 rasterized at 30 m (matches ESFire30 resolution).
Output: 02_analysis/wui_fire_selectivity.csv
"""
import os

import arcpy
import pandas as pd
from arcpy.sa import Con, IsNull, Raster, TabulateArea

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDB = os.path.join(ROOT, "01_processed", "espana.gdb")
A = os.path.join(ROOT, "02_analysis")
WUI = os.path.join(ROOT, "01_processed", "wui_study_3035.tif")
arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True
arcpy.env.cellSize = 30
arcpy.env.snapRaster = WUI

regions = os.path.join(GDB, "study_regions")
arcpy.env.extent = arcpy.Describe(regions).extent

# Burned mask 2001-2025 (any burn) at 30 m
fires = os.path.join("memory", "fires_0125")
arcpy.analysis.Select(os.path.join(GDB, "esfire30_study"), fires, "fire_year >= 2001")
arcpy.management.CalculateField(fires, "burn", "1", field_type="SHORT")
burn_r = os.path.join(GDB, "burned_2001_2025_30m")
arcpy.conversion.PolygonToRaster(fires, "burn", burn_r, "CELL_CENTER", cellsize=30)

wui = Raster(WUI)
names = {1: "Intermix (forest/shrub)", 2: "Interface (forest/shrub)", 3: "Intermix (grass)", 4: "Interface (grass)",
         5: "Non-WUI wildland (forest/shrub)", 6: "Non-WUI grassland", 7: "Non-WUI urban", 8: "Non-WUI other"}

rows = []
for label, raster in (("landscape", Con(wui > 0, wui)), ("burned", Con(~IsNull(Raster(burn_r)) & (wui > 0), wui))):
    tab = os.path.join("memory", f"sel_{label}")
    TabulateArea(regions, "region", raster, "Value", tab, 30)
    df = pd.DataFrame(arcpy.da.TableToNumPyArray(tab, "*"))
    for _, r in df.iterrows():
        for k in names:
            rows.append(dict(region=r["REGION"], kind=label, wui_class=k, ha=r.get(f"VALUE_{k}", 0) / 1e4))

d = pd.DataFrame(rows).pivot_table(index=["region", "wui_class"], columns="kind", values="ha").reset_index()
d["class_name"] = d["wui_class"].map(names)
for c in ("landscape", "burned"):
    d[f"{c}_share_pct"] = 100 * d[c] / d.groupby("region")[c].transform("sum")
d["selectivity"] = d["burned_share_pct"] / d["landscape_share_pct"]
d.to_csv(os.path.join(A, "wui_fire_selectivity.csv"), index=False)
pd.set_option("display.width", 200)
print(d[["region", "class_name", "landscape_share_pct", "burned_share_pct", "selectivity"]].round(2).to_string(index=False))
arcpy.management.Delete("memory")
