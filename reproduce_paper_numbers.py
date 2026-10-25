"""Re-derive every checkable number in the report from data/analysis_table_municipalities.csv.

No ArcGIS needed: Python 3 with pandas, numpy and statsmodels. Run from this folder:
    python reproduce_paper_numbers.py
For each number it prints PAPER vs COMPUTED and a status:
    MATCH     the computed value rounds to the number printed in the paper
    ROUNDING  off by one unit in the last printed digit (a rounding slip, not an error)
    DIFFERS   a real discrepancy (explained in README.md, "Known issues")
Models follow scripts/10_models.py and scripts/15_quintile_test.py exactly. Table 4, Moran's I and the WUI
resolution check come from GIS steps (scripts 09b, 09c, 11); their saved outputs in data/ are checked here.
Writes results/reproduction_check.csv.
"""
import os

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "results")
os.makedirs(OUT, exist_ok=True)

raw = pd.read_csv(os.path.join(D, "analysis_table_municipalities.csv"), dtype={"ine_code": str, "PROV_CODE": str})
full = raw[raw["pop_2000"] > 0].copy()
full["pop_loss_pct_2000_2020"] = -full["pop_change_pct_2000_2020"]
full["holdings_loss_pct_1999_2020"] = -full["holdings_change_pct_1999_2020"]
full["log_density_2000"] = np.log(full["density_2000"])
full["log_area"] = np.log(full["area_km2"])
full["log_pct_burned"] = np.log1p(full["pct_burned_2001_2025"])
full["northwest"] = (full["region"] == "Northwest").astype(int)

# Standardize on all municipalities with population (1st/99th percentile capped), as in 10_models.py
preds = ["pop_loss_pct_2000_2020", "holdings_loss_pct_1999_2020", "log_density_2000", "pct_wildland_2018",
         "slope_mean_deg", "elev_mean_m", "precip_mm", "temp_mean_c", "pct_wui_any"]
SD = {}
for c in preds:
    lo, hi = full[c].quantile([0.01, 0.99])
    x = full[c].clip(lo, hi)
    SD[c] = x.std()
    full[f"z_{c}"] = (x - x.mean()) / x.std()
fh = np.log1p(full["pct_burned_1985_2000"])
full["z_fire_history"] = (fh - fh.mean()) / fh.std()
full["cluster"] = full["comarca"].astype("string").fillna("P" + full["PROV_CODE"])

ctrl = ("z_log_density_2000 + z_pct_wildland_2018 + z_slope_mean_deg + z_elev_mean_m + z_precip_mm + "
        "z_temp_mean_c + z_pct_wui_any")
rural = full[full["rural_2000"]].dropna(subset=[f"z_{c}" for c in preds])
POP, FARM = "z_pop_loss_pct_2000_2020", "z_holdings_loss_pct_1999_2020"


def cl(d):
    return dict(cov_type="cluster", cov_kwds={"groups": pd.factorize(d["cluster"])[0]})


def nb(formula, d, **kw):
    return smf.negativebinomial(formula, d, offset=d["log_area"]).fit(disp=0, maxiter=1000, **kw)


def ols(formula, d, **kw):
    return smf.ols(formula, d).fit(**kw)


def get(m, term, exp):
    est, (lo, hi), p = m.params[term], m.conf_int().loc[term], m.pvalues[term]
    return (np.exp(est), np.exp(lo), np.exp(hi), p) if exp else (est, lo, hi, p)


rows = []


def check(where, item, paper, computed, decimals=None, kind="value"):
    """paper: number as printed (or a string like '<0.001' / '>0.09'); decimals: digits printed in the paper."""
    if kind == "lt":
        status = "MATCH" if computed < paper else "DIFFERS"
        shown = f"< {paper}"
    elif kind == "gt":
        status = "MATCH" if computed > paper else "DIFFERS"
        shown = f"> {paper}"
    elif kind == "count":
        status = "MATCH" if int(computed) == int(paper) else "DIFFERS"
        shown = str(paper)
    else:
        unit = 10 ** -decimals
        if round(computed + 1e-12, decimals) == round(paper, decimals):
            status = "MATCH"
        elif abs(computed - paper) <= unit + 1e-9:
            status = "ROUNDING"
        else:
            status = "DIFFERS"
        shown = f"{paper:.{decimals}f}"
    rows.append(dict(where=where, item=item, paper=shown, computed=round(float(computed), 4), status=status))


# ---------------------------------------------------------------- Study area / Table 1
check("Study area", "Andalucia municipalities", 785, (raw["region"] == "Andalucia").sum(), kind="count")
check("Study area", "Northwest municipalities", 850, (raw["region"] == "Northwest").sum(), kind="count")
T1 = {"Andalucia": dict(n=381, pop=1187, popc=-12.4, hold=-36.9, sau=-12.3, rate=4.8, mean=3.6, med=0.5, pr=515),
      "Northwest": dict(n=608, pop=675, popc=-31.7, hold=-56.3, sau=-6.0, rate=42.5, mean=15.5, med=4.1, pr=834)}
r_all = full[full["rural_2000"]]
for rg, v in T1.items():
    d = r_all[r_all["region"] == rg]
    w = f"Table 1 ({rg})"
    check(w, "rural municipalities", v["n"], len(d), kind="count")
    check(w, "median population 2000", v["pop"], d["pop_2000"].median(), 0)
    check(w, "median population change 2000-2020 %", v["popc"], d["pop_change_pct_2000_2020"].median(), 1)
    check(w, "median change in farm holdings %", v["hold"], d["holdings_change_pct_1999_2020"].median(), 1)
    check(w, "median change in SAU %", v["sau"], d["sau_change_pct_1999_2020"].median(), 1)
    check(w, "burned patches per 100 km2 (total patches / total area)", v["rate"],
          100 * d["n_fires_2001_2025"].sum() / d["area_km2"].sum(), 1)
    check(w, "mean % area burned", v["mean"], d["pct_burned_2001_2025"].mean(), 1)
    check(w, "median % area burned", v["med"], d["pct_burned_2001_2025"].median(), 1)
    check(w, "median annual precipitation mm", v["pr"], d["precip_mm"].median(), 0)
nw, an = r_all[r_all["region"] == "Northwest"], r_all[r_all["region"] == "Andalucia"]
check("Key finding 1", "NW median population loss %", 32, -nw["pop_change_pct_2000_2020"].median(), 0)
check("Key finding 1", "NW median farm loss %", 56, -nw["holdings_change_pct_1999_2020"].median(), 0)

# ---------------------------------------------------------------- Methods
check("Table 2 note", "1 SD of population change (points)", 30.8, SD["pop_loss_pct_2000_2020"], 1)
check("Table 2 note", "1 SD of farm-holding change (points)", 25.9, SD["holdings_loss_pct_1999_2020"], 1)
check("Table 2 note", "1 SD of % WUI (points)", 23.1, SD["pct_wui_any"], 1)
check("Methods", "comarca clusters in rural models", 88, rural["cluster"].nunique(), kind="count")
check("Methods (05_landcover)", "municipalities with CORINE abandonment, of 1,635", 273,
      (raw["abandon_ha_2000_2018"] > 0).sum(), kind="count")
check("Table 2 note", "rural NW municipalities in models", 604, (rural["region"] == "Northwest").sum(), kind="count")

# ---------------------------------------------------------------- Table 2 (by-region models, main spec)
T2 = {  # (estimate, ci_low, ci_high, p) as printed
    "Andalucia": dict(ba_pop=(-0.10, -0.34, 0.15, 0.44), ba_farm=(-0.02, -0.20, 0.17, 0.84),
                      bp_pop=(0.90, 0.76, 1.06, 0.21), bp_hist=(0.92, 0.79, 1.07, 0.29),
                      bp_farm=(1.05, 0.85, 1.30, 0.64), bp_wui=(1.09, 0.73, 1.62, 0.67)),
    "Northwest": dict(ba_pop=(0.24, 0.08, 0.41, 0.004), ba_farm=(0.19, 0.06, 0.32, 0.004),
                      bp_pop=(1.28, 1.05, 1.56, 0.016), bp_hist=(1.27, 1.07, 1.51, 0.006),
                      bp_farm=(1.08, 0.90, 1.30, 0.42), bp_wui=(0.68, 0.50, 0.93, 0.016)),
}
LABEL = dict(ba_pop="burned area, population loss (coef)", ba_farm="burned area, farm loss (coef)",
             bp_pop="patches, population loss (RR)", bp_hist="patches, pop. loss + fire history (RR)",
             bp_farm="patches, farm loss (RR)", bp_wui="patches, % WUI (RR)")
fitted = {}
for rg in ("Andalucia", "Northwest"):
    d = rural[rural["region"] == rg].copy()
    m_ols = ols(f"log_pct_burned ~ {POP} + {FARM} + {ctrl} + C(PROV_CODE)", d, **cl(d))
    m_nb = nb(f"n_fires_2001_2025 ~ {POP} + {FARM} + {ctrl} + C(PROV_CODE)", d, **cl(d))
    m_h = nb(f"n_fires_2001_2025 ~ {POP} + {FARM} + {ctrl} + z_fire_history + C(PROV_CODE)", d, **cl(d))
    fitted[rg] = (m_ols, m_nb)
    got = dict(ba_pop=get(m_ols, POP, False), ba_farm=get(m_ols, FARM, False), bp_pop=get(m_nb, POP, True),
               bp_hist=get(m_h, POP, True), bp_farm=get(m_nb, FARM, True), bp_wui=get(m_nb, "z_pct_wui_any", True))
    for k, paper in T2[rg].items():
        for part, pv, cv in zip(("estimate", "CI low", "CI high", "p"), paper, got[k]):
            dec = 3 if (part == "p" and pv < 0.01) else 2
            check(f"Table 2 ({rg})", f"{LABEL[k]}: {part}", pv, cv, dec)
    check(f"Table 2 ({rg})", "n", 381 if rg == "Andalucia" else 604, int(m_nb.nobs), kind="count")

b = fitted["Northwest"][0].params[POP]
check("Text / Methods", "(1 + % burned) higher per SD, NW (%)", 28, 100 * (np.exp(b) - 1), 0)
med = nw["pct_burned_2001_2025"].median()
check("Text / Methods", "NW median % burned", 4.1, med, 1)
new = (1 + med) * np.exp(b) - 1
check("Text / Methods", "NW median rises to (% burned)", 5.5, new, 1)
check("Text / Methods", "increase in burned share at median (%)", 34, 100 * (new / med - 1), 0)
check("Key finding 4", "farm loss: (1 + % burned) higher per SD, NW (%)", 21,
      100 * (np.exp(fitted["Northwest"][0].params[FARM]) - 1), 0)

# ---------------------------------------------------------------- Pooled interaction model (10_models.py M1)
m_int = nb(f"n_fires_2001_2025 ~ {POP} + {POP}:northwest + {FARM} + {ctrl} + C(PROV_CODE)", rural, **cl(rural))
e, lo, hi, p = get(m_int, f"{POP}:northwest", True)
check("Findings 2", "interaction RR (NW vs Andalucia)", 1.63, e, 2)
check("Findings 2", "interaction CI low", 1.26, lo, 2)
check("Findings 2", "interaction CI high", 2.12, hi, 2)
check("Findings 2", "interaction p", 0.001, p, kind="lt")
e, lo, hi, p = get(m_int, POP, True)
rows.append(dict(where="Findings 2 (context)", item="Andalucia population-loss RR in pooled model",
                 paper="'no positive relationship'", computed=f"{e:.2f} ({lo:.2f}-{hi:.2f}), p = {p:.3f}",
                 status="NOTE"))

# ---------------------------------------------------------------- Robustness: basic model (no FE, HC1)
for rg, (pe, pp) in {"Northwest": (1.33, 0.002), "Andalucia": (0.92, 0.27)}.items():
    d = rural[rural["region"] == rg]
    m = nb(f"n_fires_2001_2025 ~ {POP} + {FARM} + {ctrl}", d, cov_type="HC1")
    e, _, _, p = get(m, POP, True)
    check(f"Robustness ({rg})", "basic model patches RR", pe, e, 2)
    check(f"Robustness ({rg})", "basic model p", pp, p, 3 if pp < 0.01 else 2)

# ---------------------------------------------------------------- Table 3 (quintiles, NW) + Andalucia note
T3 = {"Q2": (0.23, 0.03, 1.10, 0.40), "Q3": (0.09, 0.38, 1.13, 0.32), "Q4": (0.20, 0.23, 1.12, 0.36),
      "Q5": (0.38, 0.020, 1.39, 0.019)}
for rg in ("Northwest", "Andalucia"):
    d = rural[rural["region"] == rg].copy()
    d["loss_q"] = pd.qcut(d["pop_loss_pct_2000_2020"], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"])
    q = "C(loss_q, Treatment('Q1'))"
    mo = ols(f"log_pct_burned ~ {q} + {FARM} + {ctrl} + C(PROV_CODE)", d, **cl(d))
    mn = nb(f"n_fires_2001_2025 ~ {q} + {FARM} + {ctrl} + C(PROV_CODE)", d, **cl(d))
    if rg == "Andalucia":
        ps = [m.pvalues[f"{q}[T.{k}]"] for m in (mo, mn) for k in ("Q2", "Q3", "Q4", "Q5")]
        check("Table 3 note", "Andalucia: smallest quintile p", 0.09, min(ps), kind="gt")
        continue
    edges = d.groupby("loss_q", observed=True)["pop_loss_pct_2000_2020"].agg(["min", "max"])
    for k, edge in (("Q1", 22), ("Q2", 29), ("Q3", 35), ("Q4", 40)):
        check("Table 3", f"{k} upper bound of population loss (%)", edge, edges.loc[k, "max"], 0)
    check("Table 3", "Q5 upper bound of population loss (%)", 62, edges.loc["Q5", "max"], 0)
    for k, (bc, bp, rr, rp) in T3.items():
        t = f"{q}[T.{k}]"
        check("Table 3", f"{k} burned area coef", bc, mo.params[t], 2)
        check("Table 3", f"{k} burned area p", bp, mo.pvalues[t], 3 if bp < 0.025 else 2)
        check("Table 3", f"{k} patches RR", rr, np.exp(mn.params[t]), 2)
        check("Table 3", f"{k} patches p", rp, mn.pvalues[t], 3 if rp < 0.025 else 2)
    sens = {"without Q5": (d[d["loss_q"] != "Q5"], 483, 0.17, 0.058, 1.18, 0.16),
            "without Ourense": (d[d["PROV_CODE"] != "32"], 538, 0.29, None, 1.30, 0.016)}
    for name, (ds, n, bc, bp, rr, rp) in sens.items():
        mo2 = ols(f"log_pct_burned ~ {POP} + {FARM} + {ctrl} + C(PROV_CODE)", ds, **cl(ds))
        mn2 = nb(f"n_fires_2001_2025 ~ {POP} + {FARM} + {ctrl} + C(PROV_CODE)", ds, **cl(ds))
        check("Table 3", f"linear {name}: n", n, int(mo2.nobs), kind="count")
        check("Table 3", f"linear {name}: burned area coef", bc, mo2.params[POP], 2)
        if bp is None:
            check("Table 3", f"linear {name}: burned area p", 0.001, mo2.pvalues[POP], kind="lt")
        else:
            check("Table 3", f"linear {name}: burned area p", bp, mo2.pvalues[POP], 3)
        check("Table 3", f"linear {name}: patches RR", rr, np.exp(mn2.params[POP]), 2)
        check("Table 3", f"linear {name}: patches p", rp, mn2.pvalues[POP], 3 if rp < 0.025 else 2)

# ---------------------------------------------------------------- Robustness: timing test (14_reviewer_checks.py)
# Script 14 standardizes on all rural municipalities (both regions), so it is reproduced that way here.
rt = full[full["rural_2000"]].copy()
rt["fire_history"] = np.log1p(rt["pct_burned_1985_2000"])
TV = ["pop_change_pct_2000_2020", "pop_change_pct_2000_2010", "holdings_change_pct_1999_2020", "log_density_2000",
      "pct_wildland_2018", "slope_mean_deg", "elev_mean_m", "precip_mm", "temp_mean_c", "pct_wui_any", "fire_history"]
for c in TV:
    lo, hi = rt[c].quantile([0.01, 0.99])
    x = rt[c].clip(lo, hi)
    rt[f"t_{c}"] = (x - x.mean()) / x.std()
for rg in ("Northwest", "Andalucia"):
    d = rt[rt["region"] == rg].dropna(subset=[f"t_{c}" for c in TV] + ["n_fires_2011_2025"]).copy()
    tc = ctrl.replace("z_", "t_")
    m = nb(f"n_fires_2011_2025 ~ t_pop_change_pct_2000_2010 + t_fire_history + {tc} + C(PROV_CODE)", d, **cl(d))
    e, lo, hi, p = get(m, "t_pop_change_pct_2000_2010", True)
    pe, pp = {"Northwest": (1.13, 0.066), "Andalucia": (0.89, 0.18)}[rg]
    check(f"Robustness, timing ({rg})", "loss 2000-2010 -> patches 2011-2025, RR per SD of loss", pe, 1 / e, 2)
    check(f"Robustness, timing ({rg})", "p", pp, p, 3 if rg == "Northwest" else 2)

# ---------------------------------------------------------------- GIS outputs (saved results, not refitted)
sel = pd.read_csv(os.path.join(D, "wui_fire_selectivity.csv"))
T4 = {"Interface (forest/shrub)": ((1.0, 0.2, 0.17), (0.4, 0.0, 0.07)),
      "Interface (grass)": ((3.0, 0.5, 0.16), (0.9, 0.1, 0.09)),
      "Intermix (forest/shrub)": ((5.4, 3.4, 0.63), (14.3, 5.1, 0.35)),
      "Intermix (grass)": ((4.7, 2.7, 0.57), (9.6, 2.9, 0.30)),
      "Non-WUI wildland (forest/shrub)": ((40.8, 54.4, 1.34), (38.2, 38.2, 1.00)),
      "Non-WUI grassland": ((26.1, 33.2, 1.27), (24.4, 52.5, 2.16)),
      "Non-WUI other": ((18.2, 5.6, 0.31), (12.2, 1.2, 0.10))}
for cls, vals in T4.items():
    for rg, (ls, bs, ratio) in zip(("Andalucia", "Northwest"), vals):
        s = sel[(sel["region"] == rg) & (sel["class_name"] == cls)].iloc[0]
        check(f"Table 4 ({rg})", f"{cls}: landscape %", ls, s["landscape_share_pct"], 1)
        check(f"Table 4 ({rg})", f"{cls}: burned %", bs, s["burned_share_pct"], 1)
        check(f"Table 4 ({rg})", f"{cls}: ratio", ratio, s["selectivity"], 2)
for rg in ("Andalucia", "Northwest"):
    s = sel[(sel["region"] == rg) & (sel["class_name"] == "Non-WUI urban")].iloc[0]
    rows.append(dict(where=f"Table 4 ({rg})", item="Non-WUI urban (row omitted from Table 4)", paper="not shown (noted in caption)",
                     computed=f"{s['landscape_share_pct']:.2f}% / {s['burned_share_pct']:.2f}%", status="NOTE"))

mi = pd.read_csv(os.path.join(D, "morans_i_residuals.csv"))
mi = mi[mi["region"] != "Both"]
check("Methods", "Moran's I basic model, min", 0.22, mi[mi["spec"] == "basic"]["morans_i"].min(), 2)
check("Methods", "Moran's I basic model, max", 0.53, mi[mi["spec"] == "basic"]["morans_i"].max(), 2)
check("Robustness", "Moran's I with fixed effects, min", 0.19, mi[mi["spec"] == "fe_cluster"]["morans_i"].min(), 2)
check("Robustness", "Moran's I with fixed effects, max", 0.49, mi[mi["spec"] == "fe_cluster"]["morans_i"].max(), 2)

wr = pd.read_csv(os.path.join(D, "wui_resolution_check.csv"))
diff = pd.concat([(wr["intermix_30m"] - wr["intermix_10m"]).abs(), (wr["interface_30m"] - wr["interface_10m"]).abs()])
check("Methods", "WUI 30 m vs 10 m: test municipalities", 100, len(wr), kind="count")
# 09b prints a mean per class (intermix 0.03, interface 0.01); the paper quotes the larger one
check("Methods", "WUI 30 m vs 10 m: mean |difference|, intermix (points)", 0.03,
      (wr["intermix_30m"] - wr["intermix_10m"]).abs().mean(), 2)
check("Methods", "WUI 30 m vs 10 m: max |difference| (points)", 0.16, diff.max(), 2)
r = np.corrcoef(pd.concat([wr["intermix_10m"], wr["interface_10m"]]), pd.concat([wr["intermix_30m"], wr["interface_30m"]]))[0, 1]
check("Methods", "WUI 30 m vs 10 m: r", 1.000, r, 3)
check("Methods", "smallest test municipality (km2)", 1.65, wr["area_km2"].min(), 2)

# ---------------------------------------------------------------- report
res = pd.DataFrame(rows)
res.to_csv(os.path.join(OUT, "reproduction_check.csv"), index=False)
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 70)
pd.set_option("display.max_rows", 500)
print(res.to_string(index=False))
counts = res["status"].value_counts()
print("\nSUMMARY:", ", ".join(f"{k} {v}" for k, v in counts.items()), f"(of {len(res)} rows)")
for s in ("DIFFERS", "ROUNDING"):
    sub = res[res["status"] == s]
    if len(sub):
        print(f"\n{s}:")
        print(sub[["where", "item", "paper", "computed"]].to_string(index=False))
