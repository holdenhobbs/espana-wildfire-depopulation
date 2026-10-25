"""Combine INE 'Cifras oficiales de población' province tables into one municipal table.

Input : 00_raw/population_ine/province_tables/ine_*.csv  (one INE table per province)
Output: 01_processed/ine_population_long.csv   (ine_code, municipality, year, population)
        01_processed/ine_population_wide.csv   (one row per municipality, pop_1996..pop_2025)
"""
import glob
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "00_raw", "population_ine", "province_tables")
OUT = os.path.join(ROOT, "01_processed")

frames = []
for path in sorted(glob.glob(os.path.join(RAW, "ine_*.csv"))):
    df = pd.read_csv(path, sep=";", dtype=str, encoding="utf-8")
    df = df[df["Sexo"] == "Total"]
    frames.append(df)

df = pd.concat(frames, ignore_index=True)
df["ine_code"] = df["Municipios"].str[:5]
df["municipality"] = df["Municipios"].str[6:]
df["year"] = df["Periodo"].astype(int)
# INE uses '.' as thousands separator; empty or '..' means no data
df["population"] = pd.to_numeric(df["Total"].str.replace(".", "", regex=False), errors="coerce")
df = df[df["ine_code"].str.fullmatch(r"\d{5}")]
df = df.drop_duplicates(["ine_code", "year"])[["ine_code", "municipality", "year", "population"]]
df = df.sort_values(["ine_code", "year"])
df.to_csv(os.path.join(OUT, "ine_population_long.csv"), index=False, encoding="utf-8")

wide = df.pivot(index="ine_code", columns="year", values="population")
wide.columns = [f"pop_{c}" for c in wide.columns]
names = df.drop_duplicates("ine_code").set_index("ine_code")["municipality"]
wide.insert(0, "municipality", names)
wide.insert(1, "prov_code", wide.index.str[:2])
wide.to_csv(os.path.join(OUT, "ine_population_wide.csv"), encoding="utf-8")

print(f"municipalities: {len(wide)}  years: {df['year'].min()}-{df['year'].max()}  provinces: {wide['prov_code'].nunique()}")
print("missing pop_2000:", int(wide["pop_2000"].isna().sum()), " missing pop_2020:", int(wide["pop_2020"].isna().sum()))
print(wide[["municipality", "pop_2000", "pop_2020"]].head())
