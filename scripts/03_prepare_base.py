"""Build the project geodatabase: municipalities (with study regions, population, buildings) and cleaned FIRMS points.

Inputs
  00_raw/settlement_hisdac/hisdac_..._wideformat_v1.gpkg   CNIG municipal polygons (LAEA) + HISDAC building stats
  01_processed/ine_population_wide.csv                      from 01_build_ine_population.py
  00_raw/fire_firms/firms_modis_spain_2008_2023.csv         NASA FIRMS MODIS C6.1 detections
Outputs (01_processed/espana.gdb)
  municipalities   one polygon per municipality, EPSG:3035
  firms_veg        FIRMS detections with type = 0 (presumed vegetation fire), EPSG:3035
"""
import os

import arcpy
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "00_raw")
PROC = os.path.join(ROOT, "01_processed")
GDB = os.path.join(PROC, "espana.gdb")
LAEA = arcpy.SpatialReference(3035)

arcpy.env.overwriteOutput = True
if not arcpy.Exists(GDB):
    arcpy.management.CreateFileGDB(PROC, "espana.gdb")

# Study regions by autonomous community (CA_CODE) and province (PROV_CODE), INE codes
NORTHWEST_CA = {"12", "03"}          # Galicia, Asturias
NORTHWEST_PROV = {"24", "49"}        # León, Zamora (Castilla y León)
ANDALUCIA_CA = {"01"}


def region(ca, prov):
    if ca in ANDALUCIA_CA:
        return "Andalucia"
    if ca in NORTHWEST_CA or prov in NORTHWEST_PROV:
        return "Northwest"
    return "Other"


# --- Municipalities ---------------------------------------------------------
src = os.path.join(RAW, "settlement_hisdac", "hisdac_es_municipality_stats_multitemporal_wideformat_v1.gpkg",
                   "main.ES_building_muni_stats_wideform")
keep = ["NATCODE", "CA_CODE", "PROV_CODE", "LAU_CODE", "numbldgs_2000", "numbldgs_2010", "numbldgs_2020"]
muni = os.path.join(GDB, "municipalities")

fm = arcpy.FieldMappings()
for f in keep:
    m = arcpy.FieldMap()
    m.addInputField(src, f)
    fm.addFieldMap(m)
arcpy.conversion.ExportFeatures(src, muni, field_mapping=fm)
arcpy.management.DefineProjection(muni, LAEA) if arcpy.Describe(muni).spatialReference.factoryCode != 3035 else None

arcpy.management.AddFields(muni, [["ine_code", "TEXT", "", 5], ["region", "TEXT", "", 12], ["area_km2", "DOUBLE"],
                                  ["pop_2000", "DOUBLE"], ["pop_2010", "DOUBLE"], ["pop_2020", "DOUBLE"],
                                  ["pop_2025", "DOUBLE"], ["muni_name", "TEXT", "", 120]])

pop = pd.read_csv(os.path.join(PROC, "ine_population_wide.csv"), dtype={"ine_code": str}).set_index("ine_code")
missing = 0
with arcpy.da.UpdateCursor(muni, ["CA_CODE", "PROV_CODE", "LAU_CODE", "ine_code", "region", "area_km2", "SHAPE@AREA",
                                  "pop_2000", "pop_2010", "pop_2020", "pop_2025", "muni_name"]) as cur:
    for r in cur:
        code = str(r[2]).zfill(5)
        r[3] = code
        r[4] = region(r[0], r[1])
        r[5] = r[6] / 1e6
        if code in pop.index:
            p = pop.loc[code]
            r[7:11] = [None if pd.isna(p.get(c)) else float(p[c]) for c in ("pop_2000", "pop_2010", "pop_2020", "pop_2025")]
            r[11] = p["municipality"]
        else:
            missing += 1
        cur.updateRow(r)

counts = {}
with arcpy.da.SearchCursor(muni, ["region"]) as cur:
    for (rg,) in cur:
        counts[rg] = counts.get(rg, 0) + 1
print("municipalities:", sum(counts.values()), counts, "| no INE population match:", missing)

# --- FIRMS: vegetation-fire detections only (type 0), all years -------------
csv = os.path.join(RAW, "fire_firms", "firms_modis_spain_2008_2023.csv")
df = pd.read_csv(csv)
total = len(df)
df = df[df["type"] == 0].copy()
df["year"] = pd.to_datetime(df["acq_date"]).dt.year
clean_csv = os.path.join(PROC, "firms_veg_2008_2023.csv")
df.to_csv(clean_csv, index=False)

tmp = os.path.join(GDB, "firms_veg_wgs84")
arcpy.management.XYTableToPoint(clean_csv, tmp, "longitude", "latitude", coordinate_system=arcpy.SpatialReference(4326))
arcpy.management.Project(tmp, os.path.join(GDB, "firms_veg"), LAEA)
arcpy.management.Delete(tmp)
print(f"FIRMS: {total} detections -> {len(df)} vegetation-fire (type 0), years {df['year'].min()}-{df['year'].max()}")
print("feature count:", arcpy.management.GetCount(os.path.join(GDB, "firms_veg"))[0])
