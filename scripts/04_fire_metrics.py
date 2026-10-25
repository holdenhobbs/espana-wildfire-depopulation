"""Municipal fire metrics from ESFire30 (Landsat 30 m annual burned-area perimeters).

For every municipality in the study regions and every year 1985–2025:
  burned_ha  burned area inside the municipality
  n_fires    number of burned patches intersecting it
Plus recurrence for 2001–2025: area burned two or more times.

Outputs
  01_processed/espana.gdb/study_munis          study-region municipalities (shared 53xxx territories excluded)
  01_processed/espana.gdb/esfire30_study       all fire polygons 1985–2025 clipped to study regions (EPSG:3035)
  02_analysis/fire_by_muni_year.csv             long table: ine_code, year, burned_ha, n_fires
  02_analysis/fire_recurrence_2001_2025.csv     ine_code, reburned_ha (burned >= 2 times)
"""
import os

import arcpy
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "00_raw", "fire_esfire30", "ESFire30_1985_2025")
GDB = os.path.join(ROOT, "01_processed", "espana.gdb")
ANALYSIS = os.path.join(ROOT, "02_analysis")
LAEA = arcpy.SpatialReference(3035)

arcpy.env.overwriteOutput = True
arcpy.env.workspace = GDB

# Study municipalities and region outlines
study = os.path.join(GDB, "study_munis")
arcpy.analysis.Select("municipalities", study, "region <> 'Other' AND ine_code NOT LIKE '53%'")
regions = os.path.join(GDB, "study_regions")
arcpy.analysis.PairwiseDissolve(study, regions, "region")
print("study municipalities:", arcpy.management.GetCount(study)[0])

# Reproject each year, clip to the study regions, tag with year, then merge
yearly = []
for year in range(1985, 2026):
    shp = os.path.join(RAW, f"BA_{year}.shp")
    if not arcpy.Exists(shp):
        print("missing", shp)
        continue
    proj = os.path.join("memory", f"ba_{year}")
    arcpy.management.Project(shp, proj, LAEA)
    clip = os.path.join("memory", f"bac_{year}")
    arcpy.analysis.PairwiseClip(proj, regions, clip)
    arcpy.management.CalculateField(clip, "fire_year", str(year), field_type="SHORT")
    arcpy.management.CalculateField(clip, "fire_uid", f"'{year}_' + str(!OBJECTID!)", field_type="TEXT")
    yearly.append(clip)

fires = os.path.join(GDB, "esfire30_study")
arcpy.management.Merge(yearly, fires)
print("fire polygons in study regions 1985-2025:", arcpy.management.GetCount(fires)[0])

# Burned area and fire count per municipality-year
inter = os.path.join("memory", "fire_x_muni")
arcpy.analysis.PairwiseIntersect([fires, study], inter, "ALL")
rows = []
with arcpy.da.SearchCursor(inter, ["ine_code", "fire_year", "fire_uid", "SHAPE@AREA"]) as cur:
    for code, yr, uid, area in cur:
        rows.append((code, yr, uid, area / 1e4))
df = pd.DataFrame(rows, columns=["ine_code", "year", "fire_uid", "ha"])
by_year = df.groupby(["ine_code", "year"]).agg(burned_ha=("ha", "sum"), n_fires=("fire_uid", "nunique")).reset_index()
by_year.to_csv(os.path.join(ANALYSIS, "fire_by_muni_year.csv"), index=False)
print("municipality-years with fire:", len(by_year), "| municipalities that ever burned:", by_year["ine_code"].nunique())

# Recurrence 2001-2025: area burned two or more times
recent = os.path.join("memory", "fires_2001")
arcpy.analysis.Select(fires, recent, "fire_year >= 2001")
overlap = os.path.join("memory", "overlap")
arcpy.analysis.CountOverlappingFeatures(recent, overlap, 2)
reb = os.path.join("memory", "reburn_x_muni")
arcpy.analysis.PairwiseIntersect([overlap, study], reb, "ALL")
rec = {}
with arcpy.da.SearchCursor(reb, ["ine_code", "SHAPE@AREA"]) as cur:
    for code, area in cur:
        rec[code] = rec.get(code, 0) + area / 1e4
pd.DataFrame(sorted(rec.items()), columns=["ine_code", "reburned_ha_2001_2025"]).to_csv(
    os.path.join(ANALYSIS, "fire_recurrence_2001_2025.csv"), index=False)
print("municipalities with reburned area (2001-2025):", len(rec))

arcpy.management.Delete("memory")
