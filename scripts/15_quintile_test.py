"""Is the depopulation–fire relationship linear, or driven by the most-depopulated municipalities? (review point 2)

Rural municipalities, main specification (province fixed effects, SEs clustered by comarca), same controls as
10_models.py. Population change is expressed as POPULATION LOSS so that effects > 1 mean more fire with more loss.
  A  baseline: linear population loss (reproduces the main model)
  B  quintile dummies of population loss within region (reference = least loss, Q1)
  C  linear model dropping the most-depopulated quintile (Q5)
  D  linear model dropping Ourense province (32), the fire epicentre
Outcomes: burned patches 2001–2025 (negative binomial, area offset) and log(1 + % burned) (OLS).
Output: 02_analysis/quintile_test.csv
"""
import os

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
A = os.path.join(ROOT, "02_analysis")

full = pd.read_csv(os.path.join(A, "analysis_table_municipalities.csv"), dtype={"ine_code": str, "PROV_CODE": str})
full = full[full["pop_2000"] > 0].copy()
full["pop_loss_pct_2000_2020"] = -full["pop_change_pct_2000_2020"]
full["holdings_loss_pct_1999_2020"] = -full["holdings_change_pct_1999_2020"]
full["log_density_2000"] = np.log(full["density_2000"])
full["log_area"] = np.log(full["area_km2"])
full["log_pct_burned"] = np.log1p(full["pct_burned_2001_2025"])

# Standardize on the full sample, exactly as in 10_models.py
preds = ["pop_loss_pct_2000_2020", "holdings_loss_pct_1999_2020", "log_density_2000", "pct_wildland_2018",
         "slope_mean_deg", "elev_mean_m", "precip_mm", "temp_mean_c", "pct_wui_any"]
for c in preds:
    lo, hi = full[c].quantile([0.01, 0.99])
    x = full[c].clip(lo, hi)
    full[f"z_{c}"] = (x - x.mean()) / x.std()
full["cluster"] = full["comarca"].astype("string").fillna("P" + full["PROV_CODE"])

ctrl = ("z_holdings_loss_pct_1999_2020 + z_log_density_2000 + z_pct_wildland_2018 + z_slope_mean_deg + "
        "z_elev_mean_m + z_precip_mm + z_temp_mean_c + z_pct_wui_any + C(PROV_CODE)")
rural = full[full["rural_2000"]].dropna(subset=[f"z_{c}" for c in preds])

rows = []


def fit(d, rhs, label, region, terms):
    kw = dict(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["cluster"])[0]})
    nb = smf.negativebinomial(f"n_fires_2001_2025 ~ {rhs} + {ctrl}", d, offset=d["log_area"]).fit(disp=0, maxiter=1000, **kw)
    ols = smf.ols(f"log_pct_burned ~ {rhs} + {ctrl}", d).fit(**kw)
    for outcome, m, exp in (("burned_patches_RR", nb, True), ("log1p_pct_burned_coef", ols, False)):
        ci = m.conf_int()
        for t in terms:
            if t not in m.params:
                continue
            est, lo, hi = m.params[t], ci.loc[t, 0], ci.loc[t, 1]
            if exp:
                est, lo, hi = np.exp([est, lo, hi])
            rows.append(dict(region=region, spec=label, outcome=outcome, term=t.replace("z_", ""), estimate=est,
                             ci_low=lo, ci_high=hi, p_value=m.pvalues[t], n=int(m.nobs)))


for rg in ("Northwest", "Andalucia"):
    d = rural[rural["region"] == rg].copy()
    d["loss_q"] = pd.qcut(d["pop_loss_pct_2000_2020"], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"])
    qr = d.groupby("loss_q", observed=True)["pop_loss_pct_2000_2020"].agg(["min", "max", "size"])
    print(f"\n{rg}: population-loss quintiles (% lost 2000–2020)\n{qr.round(1)}")

    fit(d, "z_pop_loss_pct_2000_2020", "A_linear_all", rg, ["z_pop_loss_pct_2000_2020"])
    fit(d, "C(loss_q, Treatment('Q1'))", "B_quintile_dummies", rg,
        [f"C(loss_q, Treatment('Q1'))[T.{q}]" for q in ("Q2", "Q3", "Q4", "Q5")])
    fit(d[d["loss_q"] != "Q5"], "z_pop_loss_pct_2000_2020", "C_linear_drop_Q5", rg, ["z_pop_loss_pct_2000_2020"])
    if rg == "Northwest":
        fit(d[d["PROV_CODE"] != "32"], "z_pop_loss_pct_2000_2020", "D_linear_drop_Ourense", rg,
            ["z_pop_loss_pct_2000_2020"])

res = pd.DataFrame(rows)
res["term"] = res["term"].str.replace(r"C\(loss_q, Treatment\('Q1'\)\)\[T\.(Q\d)\]", r"\1 vs Q1", regex=True)
res.to_csv(os.path.join(A, "quintile_test.csv"), index=False)
pd.set_option("display.width", 220)
print("\n" + res.round(3).to_string(index=False))
