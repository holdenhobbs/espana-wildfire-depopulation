"""Checks prompted by external review of the first version.

(a) Agricultural burning: how much of the 2001–2025 ESFire30 burned area falls on agricultural land (CLC 2018
    codes 12–22)? Stubble/pruning burns would sit there; abandonment-driven fire should sit on wildland.
    Then re-run the main Northwest/Andalucía models counting only burned area on non-agricultural land.
(b) Timing: does EARLIER depopulation (2000–2010) predict LATER fire (2011–2025), controlling for 1985–2000 fire?
    This separates cause and effect better than overlapping windows.
(c) Density confound: report the baseline-density coefficient and test the depopulation effect within density
    terciles in the Northwest.
Outputs: 02_analysis/reviewer_checks.csv, 02_analysis/burned_area_by_landcover.csv
"""
import os

import arcpy
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from arcpy.sa import Con, IsNull, Raster, TabulateArea, ZonalStatisticsAsTable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDB = os.path.join(ROOT, "01_processed", "espana.gdb")
A = os.path.join(ROOT, "02_analysis")
CLC = os.path.join(ROOT, "00_raw", "landcover_corine", "U2018_CLC2018_V2020_20u1.tif")
arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True

burn = Raster(os.path.join(GDB, "burned_2001_2025_30m"))
arcpy.env.snapRaster = os.path.join(GDB, "burned_2001_2025_30m")
arcpy.env.cellSize = 30
arcpy.env.extent = arcpy.Describe(os.path.join(GDB, "study_regions")).extent
clc = Raster(CLC)
group = Con((clc >= 1) & (clc <= 11), 1, Con((clc >= 12) & (clc <= 22), 2, Con((clc >= 23) & (clc <= 25), 3,
        Con((clc >= 26) & (clc <= 29), 4, 5))))
names = {1: "artificial", 2: "agriculture", 3: "forest", 4: "scrub/herbaceous", 5: "other"}

# (a1) burned area by CLC group and region
tab = os.path.join("memory", "burn_lc")
TabulateArea(os.path.join(GDB, "study_regions"), "region", Con(~IsNull(burn), group), "Value", tab, 30)
t = pd.DataFrame(arcpy.da.TableToNumPyArray(tab, "*"))
rows = []
for _, r in t.iterrows():
    tot = sum(r.get(f"VALUE_{k}", 0) for k in names)
    for k, n in names.items():
        rows.append(dict(region=r["REGION"], landcover=n, burned_ha=r.get(f"VALUE_{k}", 0) / 1e4,
                         share_pct=100 * r.get(f"VALUE_{k}", 0) / tot))
lc = pd.DataFrame(rows)
lc.to_csv(os.path.join(A, "burned_area_by_landcover.csv"), index=False)
print(lc.round(1).to_string(index=False))

# (a2) non-agricultural burned area per municipality
nonag = Con(~IsNull(burn) & (group != 2), 1, 0)
zt = os.path.join("memory", "nonag")
ZonalStatisticsAsTable(os.path.join(GDB, "study_munis"), "ine_code", nonag, zt, "DATA", "SUM")
na = pd.DataFrame(arcpy.da.TableToNumPyArray(zt, ["ine_code", "SUM"])).rename(columns={"SUM": "nonag_cells"})

# ---- models --------------------------------------------------------------------------
df = pd.read_csv(os.path.join(A, "analysis_table_municipalities.csv"), dtype={"ine_code": str})
df = df[(df["pop_2000"] > 0) & df["rural_2000"]].merge(na, on="ine_code", how="left")
df["nonag_cells"] = df["nonag_cells"].fillna(0)
df["pct_burned_nonag"] = 100 * df["nonag_cells"] * 900 / (df["area_km2"] * 1e6)  # 30 m cells; union of burns
df["log_pct_burned_nonag"] = np.log1p(df["pct_burned_nonag"])
df["log_area"] = np.log(df["area_km2"])
df["log_density_2000"] = np.log(df["density_2000"])
df["fire_history"] = np.log1p(df["pct_burned_1985_2000"])
df["cluster"] = df["comarca"].astype("string").fillna("P" + df["PROV_CODE"].astype(str))
pred = ["pop_change_pct_2000_2020", "pop_change_pct_2000_2010", "holdings_change_pct_1999_2020", "log_density_2000",
        "pct_wildland_2018", "slope_mean_deg", "elev_mean_m", "precip_mm", "temp_mean_c", "pct_wui_any", "fire_history"]
full = pd.read_csv(os.path.join(A, "analysis_table_municipalities.csv"))
for c in pred:
    src = df[c]
    lo, hi = src.quantile([0.01, 0.99])
    df[f"z_{c}"] = (src.clip(lo, hi) - src.clip(lo, hi).mean()) / src.clip(lo, hi).std()
ctrl = "z_log_density_2000 + z_pct_wildland_2018 + z_slope_mean_deg + z_elev_mean_m + z_precip_mm + z_temp_mean_c + z_pct_wui_any"

out = []


def keep(check, region, m, terms, exp):
    ci = m.conf_int()
    for term in terms:
        est, lo, hi = m.params[term], ci.loc[term, 0], ci.loc[term, 1]
        if exp:
            est, lo, hi = np.exp([est, lo, hi])
        out.append(dict(check=check, region=region, term=term.replace("z_", ""), estimate=est, ci_low=lo, ci_high=hi,
                        p_value=m.pvalues[term], n=int(m.nobs)))


for rg in ("Andalucia", "Northwest"):
    d = df[df["region"] == rg].dropna(subset=[f"z_{c}" for c in pred] + ["n_fires_2011_2025"]).copy()
    kw = dict(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["cluster"])[0]})
    # (a) burned area excluding agricultural land
    m = smf.ols(f"log_pct_burned_nonag ~ z_pop_change_pct_2000_2020 + z_holdings_change_pct_1999_2020 + {ctrl}"
                " + C(PROV_CODE)", d).fit(**kw)
    keep("burned_area_excluding_agricultural_land", rg, m,
         ["z_pop_change_pct_2000_2020", "z_holdings_change_pct_1999_2020"], exp=False)
    # (b) timing: 2000-2010 depopulation -> 2011-2025 fires, with 1985-2000 fire history
    m = smf.negativebinomial(f"n_fires_2011_2025 ~ z_pop_change_pct_2000_2010 + z_fire_history + {ctrl}"
                             " + C(PROV_CODE)", d, offset=d["log_area"]).fit(disp=0, maxiter=1000, **kw)
    keep("timing_popchange_2000_2010_to_fires_2011_2025", rg, m, ["z_pop_change_pct_2000_2010", "z_fire_history"], exp=True)
    # (c) density coefficient in the main model
    m = smf.negativebinomial(f"n_fires_2001_2025 ~ z_pop_change_pct_2000_2020 + z_holdings_change_pct_1999_2020 + {ctrl}"
                             " + C(PROV_CODE)", d, offset=d["log_area"]).fit(disp=0, maxiter=1000, **kw)
    keep("main_model_density_term", rg, m, ["z_log_density_2000", "z_pop_change_pct_2000_2020"], exp=True)
    # (c2) within density terciles (Northwest only has enough municipalities per tercile)
    if rg == "Northwest":
        d["dens_t"] = pd.qcut(d["density_2000"], 3, labels=["low", "mid", "high"])
        for t_, dt in d.groupby("dens_t", observed=True):
            mt = smf.negativebinomial(f"n_fires_2001_2025 ~ z_pop_change_pct_2000_2020 + {ctrl}", dt,
                                      offset=dt["log_area"]).fit(disp=0, maxiter=1000, cov_type="cluster",
                                                                cov_kwds={"groups": pd.factorize(dt["cluster"])[0]})
            keep(f"within_density_tercile_{t_}", rg, mt, ["z_pop_change_pct_2000_2020"], exp=True)

res = pd.DataFrame(out)
res.to_csv(os.path.join(A, "reviewer_checks.csv"), index=False)
pd.set_option("display.width", 200)
print(res.round(3).to_string(index=False))
arcpy.management.Delete("memory")
