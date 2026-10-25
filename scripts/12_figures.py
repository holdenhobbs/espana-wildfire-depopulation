"""Figures for the check-in and poster (PNG, 200 dpi) -> 03_outputs/figures and 03_outputs/maps.

fig1_region_contrast.png   population change, farm-holding change and % burned by region (rural municipalities)
fig2_depop_vs_fire.png     fires per 100 km² across population-change quintiles, by region
fig3_model_effects.png     rate ratios (95% CI) for population and farm change, by region (model M1)
map_*.png                  choropleths of % burned 2001–2025, population change, farm-holding change
"""
import os

import arcpy
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import PolyCollection

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDB = os.path.join(ROOT, "01_processed", "espana.gdb")
A = os.path.join(ROOT, "02_analysis")
FIG = os.path.join(ROOT, "03_outputs", "figures")
MAP = os.path.join(ROOT, "03_outputs", "maps")
COL = {"Andalucia": "#D08C2E", "Northwest": "#2E6F8E"}
LABEL = {"Andalucia": "Andalucía", "Northwest": "Northwest (Galicia, Asturias, León, Zamora)"}
plt.rcParams.update({"font.family": "Calibri", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False})

df = pd.read_csv(os.path.join(A, "analysis_table_municipalities.csv"), dtype={"ine_code": str})
df = df[df["pop_2000"] > 0]
rural = df[df["rural_2000"]].copy()
rural["fires_per_100km2"] = 100 * rural["n_fires_2001_2025"] / rural["area_km2"]

# --- Figure 1: regional contrast ---------------------------------------------------
metrics = [("pop_change_pct_2000_2020", "Population change\n2000–2020 (%)"),
           ("holdings_change_pct_1999_2020", "Change in farm holdings\n1999–2020 (%)"),
           ("pct_burned_2001_2025", "Area burned\n2001–2025 (% of municipality)")]
fig, axes = plt.subplots(1, 3, figsize=(11, 3.6))
for ax, (col, title) in zip(axes, metrics):
    data = [rural.loc[rural["region"] == r, col].dropna().clip(*rural[col].quantile([0.02, 0.98])) for r in COL]
    bp = ax.boxplot(data, patch_artist=True, widths=0.55, showfliers=False, medianprops=dict(color="black"))
    for patch, r in zip(bp["boxes"], COL):
        patch.set_facecolor(COL[r]); patch.set_alpha(0.8)
    ax.set_xticks([1, 2], ["Andalucía", "Northwest"]); ax.set_title(title, fontsize=11)
    ax.axhline(0, color="grey", lw=0.6, ls=":")
fig.suptitle(f"Rural municipalities (n = {len(rural)}): Andalucía vs. the Northwest", fontsize=12)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig1_region_contrast.png"), dpi=200); plt.close(fig)

# --- Figure 2: fire rate across depopulation quintiles -------------------------------
fig, ax = plt.subplots(figsize=(7, 4))
for r in COL:
    d = rural[rural["region"] == r].dropna(subset=["pop_change_pct_2000_2020"]).copy()
    d["pop_loss"] = -d["pop_change_pct_2000_2020"]
    d["q"] = pd.qcut(d["pop_loss"], 5, labels=False)
    g = d.groupby("q").agg(x=("pop_loss", "median"), y=("fires_per_100km2", "mean"),
                           se=("fires_per_100km2", lambda s: s.std() / np.sqrt(len(s))))
    ax.errorbar(g["x"], g["y"], yerr=1.96 * g["se"], marker="o", color=COL[r], label=LABEL[r], capsize=3)
ax.set_xlabel("Population loss 2000–2020 (%, quintile medians; negative = growth)")
ax.set_ylabel("Burned patches 2001–2025 per 100 km²")
ax.set_title("Burned patches by population-loss quintile (rural municipalities, unadjusted)", fontsize=11)
ax.legend(frameon=False, fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig2_depop_vs_fire.png"), dpi=200); plt.close(fig)

# --- Figure 3: model effects --------------------------------------------------------
res = pd.read_csv(os.path.join(A, "model_results.csv"))
# Burned-area model (M3, the headline outcome); signs flipped so effects are per SD of LOSS
res = res[(res["sample"] == "rural") & (res["spec"] == "fe_cluster") & res["model"].str.startswith("M3_by_region") &
          res["term"].isin(["pop_change_pct_2000_2020", "holdings_change_pct_1999_2020"])]
fig, ax = plt.subplots(figsize=(7, 3.2))
terms = {"pop_change_pct_2000_2020": "Population loss (+1 SD)", "holdings_change_pct_1999_2020": "Farm-holding loss (+1 SD)"}
for i, (term, lab) in enumerate(terms.items()):
    for j, r in enumerate(COL):
        row = res[(res["term"] == term) & (res["model"].str.endswith(r))]
        if row.empty:
            continue
        y = i + (0.15 if j == 0 else -0.15)
        e = row.iloc[0]
        est, lo, hi = -e["estimate"], -e["ci_high"], -e["ci_low"]
        ax.errorbar(est, y, xerr=[[est - lo], [hi - est]], fmt="o", color=COL[r], capsize=3,
                    label=LABEL[r] if i == 0 else None)
ax.axvline(0, color="grey", ls=":")
ax.set_yticks(range(len(terms)), list(terms.values()))
ax.set_xlabel("Effect on log(1 + % area burned) 2001–2025 (95% CI), rural municipalities\n> 0 = more loss, more area burned")
ax.legend(frameon=False, fontsize=9, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2)
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig3_model_effects.png"), dpi=200); plt.close(fig)

# --- Figure 4: fire selectivity by WUI class ------------------------------------------
sel = pd.read_csv(os.path.join(A, "wui_fire_selectivity.csv"))
order = ["Interface (forest/shrub)", "Interface (grass)", "Intermix (forest/shrub)", "Intermix (grass)",
         "Non-WUI wildland (forest/shrub)", "Non-WUI grassland", "Non-WUI other"]
fig, ax = plt.subplots(figsize=(8, 3.8))
y = np.arange(len(order))
for j, r in enumerate(COL):
    s = sel[sel["region"] == r].set_index("class_name").reindex(order)
    ax.barh(y + (0.2 if j == 0 else -0.2), s["selectivity"], height=0.4, color=COL[r], label=LABEL[r])
ax.axvline(1, color="grey", ls=":")
ax.set_yticks(y, order)
ax.invert_yaxis()
ax.set_xlabel("Burned share ÷ landscape share (2001–2025)\n> 1 = burns more than its area predicts")
ax.legend(frameon=False, fontsize=9, loc="lower right")
fig.tight_layout(); fig.savefig(os.path.join(FIG, "fig4_wui_selectivity.png"), dpi=200); plt.close(fig)

# --- Maps ---------------------------------------------------------------------------
polys, codes = [], []
with arcpy.da.SearchCursor(os.path.join(GDB, "study_munis"), ["ine_code", "SHAPE@", "region"]) as cur:
    for code, shp, region in cur:
        for part in shp:
            # A part holds its outer ring, then interior rings separated by None; draw the outer ring only
            ring = []
            for p in part:
                if p is None:
                    break
                ring.append((p.X, p.Y))
            if len(ring) > 2:
                polys.append((code, region, ring))
vals = df.set_index("ine_code")

def choropleth(col, title, fname, cmap, vmin, vmax, unit):
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
    for ax, r in zip(axes, COL):
        sel = [(c, p) for c, rg, p in polys if rg == r]
        v = np.array([vals[col].get(c, np.nan) for c, _ in sel], dtype=float)
        pc = PolyCollection([p for _, p in sel], array=np.clip(v, vmin, vmax), cmap=cmap, edgecolor="white", linewidth=0.1)
        pc.set_clim(vmin, vmax)
        ax.add_collection(pc); ax.autoscale_view(); ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(LABEL[r].split(" (")[0], fontsize=11)
    cb = fig.colorbar(pc, ax=axes, shrink=0.7, label=unit)
    fig.suptitle(title, fontsize=12)
    fig.savefig(os.path.join(MAP, fname), dpi=200, bbox_inches="tight"); plt.close(fig)

choropleth("pct_burned_2001_2025", "Area burned 2001–2025 (ESFire30)", "map_pct_burned.png", "YlOrRd", 0, 60, "% of municipality")
choropleth("pop_change_pct_2000_2020", "Population change 2000–2020 (INE)", "map_pop_change.png", "RdBu", -50, 50, "%")
choropleth("holdings_change_pct_1999_2020", "Change in farm holdings 1999–2020 (Censo Agrario)", "map_farm_change.png",
           "RdBu", -100, 100, "%")
print("figures:", sorted(os.listdir(FIG)), "\nmaps:", sorted(os.listdir(MAP)))
