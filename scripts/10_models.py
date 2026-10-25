"""Regression models: does depopulation / farm abandonment predict wildfire, and does it differ by region?

Sample: study municipalities with population data; primary models on RURAL municipalities
        (density < 50/km² and population < 5,000 in 2000), sensitivity models on all.
Outcomes (2001–2025, ESFire30):
  M1  number of fires            negative binomial GLM, offset = log(area_km2)  -> rate ratios
  M2  any fire (yes/no)          logistic GLM                                    -> odds ratios
  M3  % of area burned           OLS on log(1 + % burned)                         -> % change per SD
Predictors (standardized to 1 SD so effects are comparable):
  population change 2000–2020, farm-holding change 1999–2020, log density 2000,
  % wildland (forest+scrub) 2018, % WUI (if available), slope, elevation, precipitation, temperature,
  region (Northwest vs Andalucía) and region × population change.
Mechanism test: M1 with and without farm-holding change; if the population effect shrinks, abandonment carries it.
Outputs: 02_analysis/model_results.csv, 02_analysis/model_summaries.txt, 02_analysis/model_residuals.csv
"""
import os

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "02_analysis")

df = pd.read_csv(os.path.join(A, "analysis_table_municipalities.csv"), dtype={"ine_code": str})
df = df[df["pop_2000"] > 0].copy()
df["northwest"] = (df["region"] == "Northwest").astype(int)
df["log_density_2000"] = np.log(df["density_2000"])
df["log_area"] = np.log(df["area_km2"])
df["any_fire"] = (df["n_fires_2001_2025"] > 0).astype(int)
df["log_pct_burned"] = np.log1p(df["pct_burned_2001_2025"])
has_wui = "pct_wui_any" in df.columns

raw_predictors = ["pop_change_pct_2000_2020", "holdings_change_pct_1999_2020", "log_density_2000",
                  "pct_wildland_2018", "slope_mean_deg", "elev_mean_m", "precip_mm", "temp_mean_c"]
if has_wui:
    raw_predictors.append("pct_wui_any")
# Cap extreme % changes (tiny municipalities) at the 1st/99th percentile before standardizing
for c in raw_predictors:
    lo, hi = df[c].quantile([0.01, 0.99])
    df[f"z_{c}"] = (df[c].clip(lo, hi) - df[c].clip(lo, hi).mean()) / df[c].clip(lo, hi).std()
Z = {c: f"z_{c}" for c in raw_predictors}
fh = np.log1p(df["pct_burned_1985_2000"])
df["z_fire_history"] = (fh - fh.mean()) / fh.std()

controls = " + ".join(Z[c] for c in raw_predictors if c not in ("pop_change_pct_2000_2020", "holdings_change_pct_1999_2020"))
pop, farm = Z["pop_change_pct_2000_2020"], Z["holdings_change_pct_1999_2020"]

results, text = [], []


def record(name, sample, spec, model, exp=True):
    params, ci, p = model.params, model.conf_int(), model.pvalues
    for term in params.index:
        if term in ("Intercept", "alpha") or term.startswith("C(PROV_CODE)"):
            continue
        est, lo, hi = params[term], ci.loc[term, 0], ci.loc[term, 1]
        if exp:
            est, lo, hi = np.exp(est), np.exp(lo), np.exp(hi)
        results.append(dict(model=name, sample=sample, spec=spec, term=term.replace("z_", ""), estimate=est, ci_low=lo,
                            ci_high=hi, p_value=p[term], n=int(model.nobs), scale="ratio" if exp else "coef"))
    text.append(f"\n===== {name} | {sample} | {spec} =====\n{model.summary()}")


# Spatial dependence: neighbouring municipalities share weather, fuels and fire events (Moran's I of basic-model
# residuals 0.22–0.53). Main spec = province fixed effects + standard errors clustered by comarca agraria
# (province where the comarca is unknown). 'basic' = no fixed effects, heteroskedasticity-robust SEs (sensitivity).
df["cluster"] = df["comarca"].astype("string").fillna("P" + df["PROV_CODE"].astype(str))

SPECS = {
    "fe_cluster": dict(fe=" + C(PROV_CODE)", fit=lambda d: dict(cov_type="cluster",
                                                                cov_kwds={"groups": pd.factorize(d["cluster"])[0]})),
    "basic": dict(fe="", fit=lambda d: dict(cov_type="HC1")),
}

samples = {"rural": df[df["rural_2000"]], "all": df}
for sname, d0 in samples.items():
    d = d0.dropna(subset=list(Z.values()) + ["n_fires_2001_2025", "log_area"]).copy()
    for spec, S in SPECS.items():
        fe, kw = S["fe"], S["fit"](d)
        # With province fixed effects the region main effect is absorbed (each province is in one region)
        region_terms = f"{pop} + {pop}:northwest" if fe else f"{pop} * northwest"
        nb = lambda formula, data, k: smf.negativebinomial(formula, data, offset=data["log_area"]).fit(
            disp=0, maxiter=1000, **k)
        # M1: fire counts, NB2 with area offset (dispersion estimated)
        m1 = nb(f"n_fires_2001_2025 ~ {region_terms} + {farm} + {controls}{fe}", d, kw)
        record("M1_fire_count_NB", sname, spec, m1)
        # Mechanism: without farm-holding change
        m1b = nb(f"n_fires_2001_2025 ~ {region_terms} + {controls}{fe}", d, kw)
        record("M1b_no_farm_change", sname, spec, m1b)
        # M2: any fire (logit)
        m2 = smf.glm(f"any_fire ~ {region_terms} + {farm} + {controls}{fe}", d, family=sm.families.Binomial()).fit(**kw)
        record("M2_any_fire_logit", sname, spec, m2)
        # M3: log(1 + % area burned), OLS
        m3 = smf.ols(f"log_pct_burned ~ {region_terms} + {farm} + {controls}{fe}", d).fit(**kw)
        record("M3_log_pct_burned_OLS", sname, spec, m3, exp=False)
        # Separate models by region
        for rg in ("Andalucia", "Northwest"):
            dr = d[d["region"] == rg].copy()
            kr = S["fit"](dr)
            mr = nb(f"n_fires_2001_2025 ~ {pop} + {farm} + {controls}{fe}", dr, kr)
            record(f"M1_by_region_{rg}", sname, spec, mr)
            mr3 = smf.ols(f"log_pct_burned ~ {pop} + {farm} + {controls}{fe}", dr).fit(**kr)
            record(f"M3_by_region_{rg}", sname, spec, mr3, exp=False)
            # Robustness: control for the municipality's earlier fire history (1985-2000), which absorbs persistent
            # spatial fire-proneness that contiguity-based autocorrelation reflects
            mr4 = nb(f"n_fires_2001_2025 ~ {pop} + {farm} + {controls} + z_fire_history{fe}", dr, kr)
            record(f"M4_by_region_firehistory_{rg}", sname, spec, mr4)
        if sname == "rural":
            mu = m1.predict(d, offset=d["log_area"])
            alpha = m1.params["alpha"]
            resid_m1 = (d["n_fires_2001_2025"] - mu) / np.sqrt(mu + alpha * mu ** 2)  # Pearson residuals, NB2
            pd.DataFrame({"ine_code": d["ine_code"], "resid_M1": resid_m1, "resid_M3": m3.resid}).to_csv(
                os.path.join(A, f"model_residuals_{spec}.csv"), index=False)

res = pd.DataFrame(results)
res.to_csv(os.path.join(A, "model_results.csv"), index=False)
with open(os.path.join(A, "model_summaries.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(text))

key = res[res["term"].str.contains("pop_change|holdings_change|northwest") & (res["sample"] == "rural")]
pd.set_option("display.width", 220)
print(key[["model", "spec", "term", "estimate", "ci_low", "ci_high", "p_value", "n"]].round(3).to_string(index=False))
