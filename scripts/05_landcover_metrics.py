"""Municipal land-cover composition (CLC 2018) and land-cover transitions (CORINE change layers).

CLC grid codes: 1-11 artificial · 12-22 agriculture · 23-25 forest · 26-29 scrub/herbaceous · 30-34 open/bare (33 = burnt)
              · 35-39 wetlands · 40-44 water.

Abandonment = agriculture (12-22) -> forest or scrub/herbaceous (23-29).
Only transitions FROM agriculture are counted, so fire-driven changes (forest/scrub -> burnt 33, or regrowth
after fire) are not mistaken for abandonment.

Outputs: 02_analysis/landcover_by_muni.csv
  pct_artificial_2018, pct_agri_2018, pct_forest_2018, pct_scrub_2018, pct_wildland_2018 (forest+scrub)
  abandon_ha_1990_2000, abandon_ha_2000_2006, abandon_ha_2006_2012, abandon_ha_2012_2018, abandon_ha_2000_2018
  urbanize_ha_2000_2018 (agriculture or wildland -> artificial), pct_abandon_2000_2018, pct_agri_2000 (approx.)
"""
import os

import arcpy
import pandas as pd
from arcpy.sa import Con, Raster, ZonalStatisticsAsTable, TabulateArea

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLC = os.path.join(ROOT, "00_raw", "landcover_corine")
GDB = os.path.join(ROOT, "01_processed", "espana.gdb")
ANALYSIS = os.path.join(ROOT, "02_analysis")

arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True
study = os.path.join(GDB, "study_munis")
arcpy.env.extent = arcpy.Describe(os.path.join(GDB, "study_regions")).extent
arcpy.env.snapRaster = os.path.join(CLC, "U2018_CLC2018_V2020_20u1.tif")
arcpy.env.cellSize = 100

munis = pd.DataFrame(arcpy.da.TableToNumPyArray(study, ["ine_code", "area_km2"]))

# --- Composition 2018 (zonal histogram via TabulateArea, value = CLC code) ----
clc18 = Raster(os.path.join(CLC, "U2018_CLC2018_V2020_20u1.tif"))
groups = Con((clc18 >= 1) & (clc18 <= 11), 1,
         Con((clc18 >= 12) & (clc18 <= 22), 2,
         Con((clc18 >= 23) & (clc18 <= 25), 3,
         Con((clc18 >= 26) & (clc18 <= 29), 4, 5))))
tab = os.path.join("memory", "clc18_tab")
TabulateArea(study, "ine_code", groups, "Value", tab, 100)
comp = pd.DataFrame(arcpy.da.TableToNumPyArray(tab, "*"))
comp = comp.rename(columns={"INE_CODE": "ine_code"})
area_cols = {f"VALUE_{k}": v for k, v in {1: "artificial", 2: "agri", 3: "forest", 4: "scrub", 5: "other"}.items()}
for c in area_cols:
    if c not in comp:
        comp[c] = 0.0
total = comp[list(area_cols)].sum(axis=1)
for c, name in area_cols.items():
    comp[f"pct_{name}_2018"] = 100 * comp[c] / total
comp["pct_wildland_2018"] = comp["pct_forest_2018"] + comp["pct_scrub_2018"]
comp = comp[["ine_code"] + [f"pct_{n}_2018" for n in area_cols.values()] + ["pct_wildland_2018"]]


# --- Transitions per change period ---------------------------------------------
def is_agri(r):
    return (r >= 12) & (r <= 22)


def is_wild(r):
    return (r >= 23) & (r <= 29)


def is_artificial(r):
    return (r >= 1) & (r <= 11)


periods = {"1990_2000": ("U2000_CHA9000_90", "U2000_CHA9000_00"),
           "2000_2006": ("U2006_CHA0006_00", "U2006_CHA0006_06"),
           "2006_2012": ("U2012_CHA0612_06", "U2012_CHA0612_12"),
           "2012_2018": ("U2018_CHA1218_12", "U2018_CHA1218_18")}

out = munis.copy()
for label, (src_name, dst_name) in periods.items():
    before = Raster(os.path.join(CLC, f"{src_name}_V2020_20u1.tif"))
    after = Raster(os.path.join(CLC, f"{dst_name}_V2020_20u1.tif"))
    for kind, cond in {"abandon": is_agri(before) & is_wild(after),
                       "urbanize": (is_agri(before) | is_wild(before)) & is_artificial(after)}.items():
        flag = Con(cond, 1, 0)
        zt = os.path.join("memory", f"{kind}_{label}")
        ZonalStatisticsAsTable(study, "ine_code", flag, zt, "DATA", "SUM")
        z = pd.DataFrame(arcpy.da.TableToNumPyArray(zt, ["ine_code", "SUM"]))
        z[f"{kind}_ha_{label}"] = z["SUM"]  # 1 pixel = 100 m x 100 m = 1 ha
        out = out.merge(z[["ine_code", f"{kind}_ha_{label}"]], on="ine_code", how="left")
    print("done", label)

out = out.fillna(0)
out["abandon_ha_2000_2018"] = out[["abandon_ha_2000_2006", "abandon_ha_2006_2012", "abandon_ha_2012_2018"]].sum(axis=1)
out["urbanize_ha_2000_2018"] = out[["urbanize_ha_2000_2006", "urbanize_ha_2006_2012", "urbanize_ha_2012_2018"]].sum(axis=1)
out["pct_abandon_2000_2018"] = 100 * out["abandon_ha_2000_2018"] / (out["area_km2"] * 100)
out = out.merge(comp, on="ine_code", how="left")
# Approximate 2000 farmland share: 2018 farmland plus farmland lost to abandonment/urbanization since 2000
out["pct_agri_2000_approx"] = out["pct_agri_2018"] + out["pct_abandon_2000_2018"]

out.drop(columns=["area_km2"]).to_csv(os.path.join(ANALYSIS, "landcover_by_muni.csv"), index=False)
print(out[["pct_agri_2018", "pct_wildland_2018", "pct_abandon_2000_2018"]].describe().round(2))
print("municipalities with any abandonment 2000-2018:", int((out["abandon_ha_2000_2018"] > 0).sum()), "of", len(out))
arcpy.management.Delete("memory")
