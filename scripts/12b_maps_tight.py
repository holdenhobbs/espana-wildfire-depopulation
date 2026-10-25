"""Compact versions of the three choropleth maps for the report layout (03_outputs/maps_tight).

Same data and colour scales as 12_figures.py, but no figure title (the report caption carries it), tighter panels
and minimal whitespace, so two maps fit on a page alongside text.
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
OUT = os.path.join(ROOT, "03_outputs", "maps_tight")
os.makedirs(OUT, exist_ok=True)
plt.rcParams.update({"font.family": "Calibri", "font.size": 11})

vals = pd.read_csv(os.path.join(ROOT, "02_analysis", "analysis_table_municipalities.csv"),
                   dtype={"ine_code": str}).set_index("ine_code")
polys = []
with arcpy.da.SearchCursor(os.path.join(GDB, "study_munis"), ["ine_code", "SHAPE@", "region"]) as cur:
    for code, shp, region in cur:
        for part in shp:
            ring = []
            for p in part:
                if p is None:
                    break
                ring.append((p.X, p.Y))
            if len(ring) > 2:
                polys.append((code, region, ring))


def choropleth(col, fname, cmap, vmin, vmax, unit):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.9), gridspec_kw={"wspace": 0.02})
    for ax, (r, label) in zip(axes, (("Andalucia", "Andalucía"), ("Northwest", "Northwest"))):
        sel = [(c, p) for c, rg, p in polys if rg == r]
        v = np.array([vals[col].get(c, np.nan) for c, _ in sel], dtype=float)
        pc = PolyCollection([p for _, p in sel], array=np.clip(v, vmin, vmax), cmap=cmap, edgecolor="white",
                            linewidth=0.1)
        pc.set_clim(vmin, vmax)
        ax.add_collection(pc); ax.autoscale_view(); ax.set_aspect("equal"); ax.axis("off")
        ax.set_title(label, fontsize=12, pad=2)
    fig.colorbar(pc, ax=axes, shrink=0.8, pad=0.01, label=unit)
    fig.savefig(os.path.join(OUT, fname), dpi=220, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)


choropleth("pop_change_pct_2000_2020", "map_pop_change.png", "RdBu", -50, 50, "Population change (%)")
choropleth("pct_burned_2001_2025", "map_pct_burned.png", "YlOrRd", 0, 60, "% of municipality burned")
choropleth("holdings_change_pct_1999_2020", "map_farm_change.png", "RdBu", -100, 100, "Change in farm holdings (%)")
print(sorted(os.listdir(OUT)))
