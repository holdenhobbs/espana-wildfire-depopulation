"""Terrain and climate controls per municipality.

DEM: Copernicus GLO-90 tiles -> mosaic -> EPSG:3035 at 100 m (study regions only) -> slope (degrees).
Climate: WorldClim 2.1 (2.5 arc-min, 1970-2000 normals): BIO1 annual mean temperature (°C), BIO12 annual precipitation (mm).
Output: 02_analysis/terrain_climate_by_muni.csv  (elev_mean_m, slope_mean_deg, temp_mean_c, precip_mm)
"""
import glob
import os
import zipfile

import arcpy
import pandas as pd
from arcpy.sa import Slope, ZonalStatisticsAsTable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "00_raw")
PROC = os.path.join(ROOT, "01_processed")
GDB = os.path.join(PROC, "espana.gdb")
ANALYSIS = os.path.join(ROOT, "02_analysis")
LAEA = arcpy.SpatialReference(3035)

arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True
study = os.path.join(GDB, "study_munis")
regions = os.path.join(GDB, "study_regions")

# --- DEM mosaic, projected and clipped to the study regions -------------------
tiles = glob.glob(os.path.join(RAW, "dem", "glo90", "*.tif"))
mosaic = os.path.join(PROC, "dem_glo90_iberia_wgs84.tif")
if not arcpy.Exists(mosaic):
    arcpy.management.MosaicToNewRaster(tiles, PROC, "dem_glo90_iberia_wgs84.tif", number_of_bands=1,
                                       pixel_type="32_BIT_FLOAT")
dem = os.path.join(GDB, "dem_100m")
arcpy.env.extent = arcpy.Describe(regions).extent
arcpy.management.ProjectRaster(mosaic, dem, LAEA, "BILINEAR", 100)
slope = Slope(dem, "DEGREE")
slope.save(os.path.join(GDB, "slope_100m"))

# --- WorldClim BIO1 and BIO12 --------------------------------------------------
clim_dir = os.path.join(RAW, "climate")
climate = {}
with zipfile.ZipFile(os.path.join(clim_dir, "wc2.1_2.5m_bio.zip")) as z:
    for bio, name in (("bio1", "wc2.1_2.5m_bio_1.tif"), ("bio12", "wc2.1_2.5m_bio_12.tif")):
        if not os.path.exists(os.path.join(clim_dir, name)):
            z.extract(name, clim_dir)
        # WorldClim is in geographic degrees: project to EPSG:3035 (500 m, bilinear) before zonal stats
        climate[bio] = os.path.join(GDB, f"wc_{bio}_500m")
        arcpy.management.ProjectRaster(os.path.join(clim_dir, name), climate[bio], LAEA, "BILINEAR", 500)

# --- Zonal means per municipality ---------------------------------------------
def zonal_mean(raster, field):
    tab = os.path.join("memory", field)
    ZonalStatisticsAsTable(study, "ine_code", raster, tab, "DATA", "MEAN")
    df = pd.DataFrame(arcpy.da.TableToNumPyArray(tab, ["ine_code", "MEAN"]))
    return df.rename(columns={"MEAN": field}).set_index("ine_code")

arcpy.env.extent = "MAXOF"
# Climate rasters are coarse (~4 km): sample at 100 m so small municipalities still get a value
arcpy.env.cellSize = 100
out = pd.concat([
    zonal_mean(dem, "elev_mean_m"),
    zonal_mean(os.path.join(GDB, "slope_100m"), "slope_mean_deg"),
    zonal_mean(climate["bio1"], "temp_mean_c"),
    zonal_mean(climate["bio12"], "precip_mm"),
], axis=1)
out.index.name = "ine_code"
out.to_csv(os.path.join(ANALYSIS, "terrain_climate_by_muni.csv"))
print("municipalities with values:", out.dropna().shape[0], "of", int(arcpy.management.GetCount(study)[0]))
print(out.describe().round(1))
arcpy.management.Delete("memory")
