"""Farmland change per municipality from the INE Censo Agrario 1999 and 2020 (the abandonment signal).

1999 (provincial pc-axis tables, 'Resultados municipales'):
  10001  land distribution of holdings: Tierras labradas, Tierras para pastos permanentes, forest, other
  10002  number of holdings, parcels, livestock units (UG), annual work units (UTA)
  SAU (utilized agricultural area) 1999 = Tierras labradas + Tierras para pastos permanentes
2020 (table 52071): SAU (ha) and number of holdings with SAU, per municipality

Caveats: the census assigns each holding to one municipality; 2020 survey thresholds differ slightly from 1999.
Output: 02_analysis/agri_census_by_muni.csv
"""
import glob
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "00_raw", "agri_census")
ANALYSIS = os.path.join(ROOT, "02_analysis")


def es_number(s):
    """'1.220.973' or '100,00' (Spanish formatting) -> float."""
    s = str(s).strip()
    if s in ("", "..", ".", "-"):
        return float("nan")
    return float(s.replace(".", "").replace(",", "."))


def read_1999(table):
    frames = []
    for path in glob.glob(os.path.join(RAW, "ca1999", f"ca1999_prov*_{table}.csv")):
        df = pd.read_csv(path, sep=";", dtype=str, encoding="utf-8")
        df.columns = ["muni", "var", "value"]
        frames.append(df)
    df = pd.concat(frames)
    df["ine_code"] = df["muni"].str.split(":").str[0]
    df = df[df["ine_code"].str.fullmatch(r"\d{5}") & ~df["ine_code"].str.endswith("000")]
    df["value"] = df["value"].map(es_number)
    return df.pivot_table(index="ine_code", columns="var", values="value", aggfunc="first")


land = read_1999("10001")
hold = read_1999("10002")
ca99 = pd.DataFrame(index=land.index.union(hold.index))
ca99["sau_ha_1999"] = land["Tierras labradas"].fillna(0) + land["Tierras para pastos permanentes"].fillna(0)
ca99["cropland_ha_1999"] = land["Tierras labradas"]
ca99["holdings_1999"] = hold.get("Número de explotaciones: Total")
ca99["uta_1999"] = hold.get("Unidades de trabajo-año (UTA)")

# 2020: tab-separated, '906,916' style thousands separators
cols = ["nat", "ca", "prov", "comarca", "muni", "level", "sub1", "sub2", "measure", "value"]
df = pd.read_csv(os.path.join(RAW, "ca2020_municipal_SAU_explotaciones_52071.csv"), sep="\t", header=0, names=cols,
                 dtype=str, encoding="utf-8")
df = df[df["muni"].notna() & df["sub1"].isna() & (df["level"] == "SAU")]
df["ine_code"] = df["muni"].str.extract(r"^(\d{5})")[0]
df["value"] = pd.to_numeric(df["value"].str.replace(",", "", regex=False), errors="coerce")
ca20 = df.pivot_table(index="ine_code", columns="measure", values="value", aggfunc="first")
ca20 = ca20.rename(columns={"Superficie (ha.)": "sau_ha_2020", "Explotaciones": "holdings_2020"})
# Comarca agraria (agricultural county) for clustered standard errors
ca20["comarca"] = df.drop_duplicates("ine_code").set_index("ine_code")["comarca"].str.extract(r"^(\d+)")[0]

out = ca99.join(ca20[["sau_ha_2020", "holdings_2020", "comarca"]], how="outer")
out["sau_change_pct_1999_2020"] = 100 * (out["sau_ha_2020"] - out["sau_ha_1999"]) / out["sau_ha_1999"]
out["holdings_change_pct_1999_2020"] = 100 * (out["holdings_2020"] - out["holdings_1999"]) / out["holdings_1999"]
out.index.name = "ine_code"
out.to_csv(os.path.join(ANALYSIS, "agri_census_by_muni.csv"))

print("municipalities: 1999 =", ca99["sau_ha_1999"].notna().sum(), "| 2020 =", ca20["sau_ha_2020"].notna().sum(),
      "| both =", out[["sau_ha_1999", "sau_ha_2020"]].dropna().shape[0])
print("national SAU 1999 vs 2020 (ha):", round(out["sau_ha_1999"].sum()), round(out["sau_ha_2020"].sum()))
print("national holdings 1999 vs 2020:", round(out["holdings_1999"].sum()), round(out["holdings_2020"].sum()))
print(out.loc[["14001", "32054", "24089"]].round(1) if {"14001", "32054", "24089"} <= set(out.index) else out.head())
