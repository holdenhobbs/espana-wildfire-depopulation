"""Assemble the municipality-level analysis table (one row per study municipality).

Joins: study_munis (region, area, INE population, HISDAC buildings) + ESFire30 fire metrics + FIRMS intensity
       + CORINE land cover/abandonment + Censo Agrario farmland change + terrain/climate.
Output: 02_analysis/analysis_table_municipalities.csv (+ a copy as a table in espana.gdb for mapping)
"""
import os

import arcpy
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDB = os.path.join(ROOT, "01_processed", "espana.gdb")
A = os.path.join(ROOT, "02_analysis")
arcpy.env.overwriteOutput = True

study = os.path.join(GDB, "study_munis")
base = pd.DataFrame(arcpy.da.TableToNumPyArray(
    study, ["ine_code", "muni_name", "region", "CA_CODE", "PROV_CODE", "area_km2", "pop_2000", "pop_2010", "pop_2020",
            "pop_2025", "numbldgs_2000", "numbldgs_2020"], null_value=np.nan)).set_index("ine_code")

# --- Population and settlement ---------------------------------------------------
base["density_2000"] = base["pop_2000"] / base["area_km2"]
base["pop_change_pct_2000_2020"] = 100 * (base["pop_2020"] - base["pop_2000"]) / base["pop_2000"]
base["pop_change_pct_2000_2010"] = 100 * (base["pop_2010"] - base["pop_2000"]) / base["pop_2000"]
base["bldg_change_pct_2000_2020"] = 100 * (base["numbldgs_2020"] - base["numbldgs_2000"]) / base["numbldgs_2000"].replace(0, np.nan)
base["rural_2000"] = (base["density_2000"] < 50) & (base["pop_2000"] < 5000)

# --- ESFire30 fire outcomes ---------------------------------------------------------
fy = pd.read_csv(os.path.join(A, "fire_by_muni_year.csv"), dtype={"ine_code": str})
def window(y0, y1, tag):
    w = fy[(fy["year"] >= y0) & (fy["year"] <= y1)].groupby("ine_code").agg(
        **{f"burned_ha_{tag}": ("burned_ha", "sum"), f"n_fires_{tag}": ("n_fires", "sum"),
           f"fire_years_{tag}": ("year", "nunique")})
    return w
fire = window(2001, 2025, "2001_2025").join(window(2011, 2025, "2011_2025"), how="outer").join(
    window(1985, 2000, "1985_2000"), how="outer")
rec = pd.read_csv(os.path.join(A, "fire_recurrence_2001_2025.csv"), dtype={"ine_code": str}).set_index("ine_code")
df = base.join(fire).join(rec)
for c in [c for c in df.columns if c.startswith(("burned_ha_", "n_fires_", "fire_years_", "reburned_ha_"))]:
    df[c] = df[c].fillna(0)
df["pct_burned_2001_2025"] = 100 * df["burned_ha_2001_2025"] / (df["area_km2"] * 100)
df["pct_reburned_2001_2025"] = 100 * df["reburned_ha_2001_2025"] / (df["area_km2"] * 100)
df["pct_burned_1985_2000"] = 100 * df["burned_ha_1985_2000"] / (df["area_km2"] * 100)

# --- FIRMS intensity (type-0 detections, 2008-2023) ---------------------------------
sj = os.path.join("memory", "firms_join")
arcpy.analysis.SpatialJoin(os.path.join(GDB, "firms_veg"), study, sj, "JOIN_ONE_TO_ONE", "KEEP_COMMON")
fr = pd.DataFrame(arcpy.da.TableToNumPyArray(sj, ["ine_code", "frp", "confidence"]))
fr = fr.groupby("ine_code").agg(firms_n_2008_2023=("frp", "size"), firms_frp_mean=("frp", "mean"),
                                firms_frp_max=("frp", "max"))
df = df.join(fr)
df["firms_n_2008_2023"] = df["firms_n_2008_2023"].fillna(0)

# --- Land cover, farmland census, terrain/climate -------------------------------------
for f in ("landcover_by_muni.csv", "agri_census_by_muni.csv", "terrain_climate_by_muni.csv", "wui_by_muni.csv"):
    path = os.path.join(A, f)
    if os.path.exists(path):
        df = df.join(pd.read_csv(path, dtype={"ine_code": str}).set_index("ine_code"))
    else:
        print("not yet available:", f)

df.index.name = "ine_code"
df = df.reset_index()
out_csv = os.path.join(A, "analysis_table_municipalities.csv")
df.to_csv(out_csv, index=False, encoding="utf-8")
arcpy.conversion.ExportTable(out_csv, os.path.join(GDB, "analysis_table"))

print(f"rows: {len(df)}  columns: {df.shape[1]}")
print(df.groupby("region").agg(
    municipalities=("ine_code", "size"), rural=("rural_2000", "sum"),
    median_pop_change=("pop_change_pct_2000_2020", "median"),
    median_sau_change=("sau_change_pct_1999_2020", "median"),
    median_holdings_change=("holdings_change_pct_1999_2020", "median"),
    mean_pct_burned=("pct_burned_2001_2025", "mean"),
    share_burned_any=("burned_ha_2001_2025", lambda s: (s > 0).mean())).round(2).T)
print("\nmissing values per key column:")
print(df[["pop_change_pct_2000_2020", "sau_change_pct_1999_2020", "holdings_change_pct_1999_2020",
          "pct_agri_2018", "precip_mm"]].isna().sum())
arcpy.management.Delete("memory")
