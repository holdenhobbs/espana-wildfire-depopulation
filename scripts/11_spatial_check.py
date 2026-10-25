"""Spatial autocorrelation of model residuals (global Moran's I, queen contiguity), by region.

Neighbouring municipalities share weather, fuels and fire events, so residuals may cluster.
If Moran's I is significant, p-values in 10_models.py are too optimistic -> report and add spatial terms.
Output: 02_analysis/morans_i_residuals.csv
"""
import os

import arcpy
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDB = os.path.join(ROOT, "01_processed", "espana.gdb")
A = os.path.join(ROOT, "02_analysis")
arcpy.env.overwriteOutput = True

rows = []
for spec in ("basic", "fe_cluster"):
    res = pd.read_csv(os.path.join(A, f"model_residuals_{spec}.csv"), dtype={"ine_code": str}).set_index("ine_code")
    fc = os.path.join(GDB, f"rural_residuals_{spec}")
    arcpy.analysis.Select(os.path.join(GDB, "study_munis"), fc,
                          "ine_code IN ({})".format(",".join(f"'{c}'" for c in res.index)))
    arcpy.management.AddFields(fc, [["resid_M1", "DOUBLE"], ["resid_M3", "DOUBLE"]])
    with arcpy.da.UpdateCursor(fc, ["ine_code", "resid_M1", "resid_M3"]) as cur:
        for r in cur:
            r[1], r[2] = res.loc[r[0], "resid_M1"], res.loc[r[0], "resid_M3"]
            cur.updateRow(r)
    for region in ("Andalucia", "Northwest", None):
        lyr = arcpy.management.MakeFeatureLayer(fc, "lyr", f"region = '{region}'" if region else None)[0]
        for field in ("resid_M1", "resid_M3"):
            out = arcpy.stats.SpatialAutocorrelation(lyr, field, "NO_REPORT", "CONTIGUITY_EDGES_CORNERS",
                                                     "EUCLIDEAN_DISTANCE", "ROW")
            rows.append(dict(spec=spec, region=region or "Both", residual=field, morans_i=float(out[0]),
                             z=float(out[1]), p=float(out[2])))
        arcpy.management.Delete("lyr")

df = pd.DataFrame(rows)
df.to_csv(os.path.join(A, "morans_i_residuals.csv"), index=False)
print(df.round(4).to_string(index=False))
