"""Validate the 30 m WUI tabulation against the native 10 m map on a test set of municipalities.

Test set: the 40 smallest study municipalities (worst case for sampling error) + 60 random others.
Output: 02_analysis/wui_resolution_check.csv and printed agreement statistics.
"""
import os

import arcpy
import numpy as np
import pandas as pd
from arcpy.sa import TabulateArea

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDB = os.path.join(ROOT, "01_processed", "espana.gdb")
A = os.path.join(ROOT, "02_analysis")
WUI = os.path.join(ROOT, "01_processed", "wui_study_3035.tif")
arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True

m = pd.DataFrame(arcpy.da.TableToNumPyArray(os.path.join(GDB, "study_munis"), ["ine_code", "area_km2"]))
smallest = m.nsmallest(40, "area_km2")["ine_code"].tolist()
rand = m[~m["ine_code"].isin(smallest)].sample(60, random_state=42)["ine_code"].tolist()
codes = smallest + rand

sub = os.path.join("memory", "test_munis")
arcpy.analysis.Select(os.path.join(GDB, "study_munis"), sub, "ine_code IN ({})".format(",".join(f"'{c}'" for c in codes)))


def shares(cell):
    arcpy.env.cellSize = cell
    tab = os.path.join("memory", f"tab_{cell}")
    TabulateArea(sub, "ine_code", WUI, "Value", tab, cell)
    df = pd.DataFrame(arcpy.da.TableToNumPyArray(tab, "*")).rename(columns={"INE_CODE": "ine_code"}).set_index("ine_code")
    land = [c for c in df.columns if c.startswith("VALUE_") and c != "VALUE_0"]
    for k in range(1, 9):
        if f"VALUE_{k}" not in df:
            df[f"VALUE_{k}"] = 0.0
    tot = df[land].sum(axis=1)
    return pd.DataFrame({"intermix": 100 * (df["VALUE_1"] + df["VALUE_3"]) / tot,
                         "interface": 100 * (df["VALUE_2"] + df["VALUE_4"]) / tot})


s10, s30 = shares(10), shares(30)
cmp = s10.join(s30, lsuffix="_10m", rsuffix="_30m").join(m.set_index("ine_code"))
cmp["group"] = np.where(cmp.index.isin(smallest), "smallest_40", "random_60")
cmp.to_csv(os.path.join(A, "wui_resolution_check.csv"))

for g, d in [("all 100", cmp), ("smallest 40", cmp[cmp["group"] == "smallest_40"])]:
    for v in ("intermix", "interface"):
        diff = (d[f"{v}_30m"] - d[f"{v}_10m"]).abs()
        r = np.corrcoef(d[f"{v}_10m"], d[f"{v}_30m"])[0, 1]
        print(f"{g:12s} {v:9s}: mean |diff| = {diff.mean():.2f} pts, max = {diff.max():.2f} pts, r = {r:.4f}")
print("smallest municipality in test set: %.2f km²" % cmp["area_km2"].min())
arcpy.management.Delete("memory")
