# Rural Depopulation, Farm Abandonment and Wildfire in Spain — replication package

Code and data for *Rural Depopulation, Farm Abandonment and Wildfire in Spain: a municipal comparison of
Andalucía and the Northwest, 2001–2025* (Holden Hobbs, Texas Tech University, independent research).

The study asks whether rural municipalities that lost more people (2000–2020) and farms (1999–2020) had more
wildfire (2001–2025), comparing rural Andalucía (381 municipalities) with the rural Northwest — Galicia, Asturias,
León and Zamora (608).

## Quick check (no ArcGIS needed, about one minute)

```
pip install -r requirements.txt
python reproduce_paper_numbers.py
```

The script reads `data/analysis_table_municipalities.csv`, refits the models and compares 181 numbers in the
paper (corrected version, October 2026) with the recomputed values. Each is marked:

| Status | Meaning |
|---|---|
| `MATCH` | recomputed value rounds to the printed number |
| `ROUNDING` | off by one in the last printed digit |
| `DIFFERS` | a real discrepancy (listed under Known issues) |
| `NOTE` | a result not printed in the paper, shown for context |

Results are saved to `results/reproduction_check.csv`. Current result: **178 MATCH, 3 NOTE, 0 ROUNDING, 0 DIFFERS**.
Tables 1–3, the pooled interaction model and the robustness models (including the timing test) reproduce from
the CSV alone. Table 4,
Moran's I and the WUI resolution check come from GIS steps; their saved outputs are in `data/` and are checked
against the paper as stored values.

## Contents

| Path | What it is |
|---|---|
| `data/analysis_table_municipalities.csv` | One row per municipality (1,635 × 75). Every model variable. See `data_dictionary.csv` |
| `data/wui_fire_selectivity.csv` | Landscape and burned-area share by WUI class and region (Table 4; script 09c) |
| `data/morans_i_residuals.csv` | Moran's I of model residuals, queen contiguity (script 11) |
| `data/wui_resolution_check.csv` | WUI shares tabulated at 30 m vs native 10 m, 100 test municipalities (script 09b) |
| `data_dictionary.csv` | Every CSV column with units and source |
| `results/model_results.csv`, `model_summaries.txt` | All coefficients from `10_models.py`, full regression output (every covariate, NB dispersion α, n) |
| `results/quintile_test.csv` | Table 3 models (`15_quintile_test.py`) |
| `results/burned_area_by_landcover.csv` | Burned area by CORINE class (`14_reviewer_checks.py`) |
| `results/model_residuals_basic.csv`, `model_residuals_fe_cluster.csv` | Residuals of the rural models, input to the Moran's I check (`10_models.py` → `11_spatial_check.py`) |
| `results/reproduction_check.csv` | Paper value vs recomputed value for every checked number |
| `data/intermediate/` | Municipal tables from steps 04–09 that `08_build_analysis_table.py` joins: fire by municipality and year, reburned area, land cover, farm census, terrain and climate, WUI shares |
| `figures/` | Figures 1, 4, 5 and 7 of the paper (`12_figures.py`); `figures/maps/` and `figures/maps_tight/` hold the choropleth maps (Figures 2, 3 and 6) |
| `reproduce_paper_numbers.py` | Standalone check of the paper's numbers |
| `scripts/` | Full pipeline, numbered in run order |

## Full pipeline (ArcGIS Pro)

Scripts 03–09c and 11–12b use `arcpy` with the Spatial Analyst extension (ArcGIS Pro 3.7). They expect the original
project layout next to `scripts/`: `00_raw/` (downloads), `01_processed/` (file geodatabase), `02_analysis/`
(tables), `03_outputs/` (figures). Run with ArcGIS Pro's Python:
`"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" scripts\<script>`

| Step | Script | Output |
|---|---|---|
| 1 | `01_build_ine_population.py` | INE province tables → municipal population 1996–2025 |
| 2 | `02_download_dem_climate.ps1` | Downloads DEM tiles and WorldClim |
| 3 | `03_prepare_base.py` | Municipal polygons + region + area + population + buildings; FIRMS type-0 points (EPSG:3035) |
| 4 | `04_fire_metrics.py` | ESFire30 1985–2025 → burned area and patch counts per municipality and year |
| 5 | `05_landcover_metrics.py` | CORINE 2018 composition and 1990–2018 change transitions |
| 6 | `06_agri_census.py` | Censo Agrario 1999 vs 2020 (holdings, SAU, comarca) |
| 7 | `07_terrain_climate.py` | Elevation, slope, temperature, precipitation |
| 8 | `08_build_analysis_table.py` | Joins everything → `analysis_table_municipalities.csv` |
| 9 | `09_wui_metrics.py`, `09b_wui_resolution_check.py`, `09c_wui_fire_selectivity.py` | WUI shares, 30 m vs 10 m check, Table 4 |
| 10 | `10_models.py` | All regression models (no arcpy) |
| 11 | `11_spatial_check.py` | Moran's I of residuals |
| 12 | `12_figures.py`, `12b_maps_tight.py` | Figures and maps |
| 14 | `14_reviewer_checks.py` | Agricultural-land check, timing test, density check |
| 15 | `15_quintile_test.py` | Quintile and sensitivity models (Table 3; no arcpy) |

Software: Python 3.13, pandas 3.0, numpy 2.3, statsmodels 0.14.6, scipy 1.16 (ArcGIS Pro 3.7 environment).
Step 13 (the script that drafted the report document) is not included; the final paper was edited by hand.

## Raw data (public; not included because of size)

| Theme | Dataset | Where |
|---|---|---|
| Fire (primary) | ESFire30 burned-area perimeters, Landsat 30 m, ≥ 5 ha, 1985–2025. Ochoa, Khairoun, Rodado Coello & Chuvieco (2026), *IJWF* 35(9) WF26035 | doi:10.5281/zenodo.20257001 |
| Fire (secondary) | NASA FIRMS MODIS C6.1 active fire archive, Spain 2008–2023, type 0 only | firms.modaps.eosdis.nasa.gov/download |
| Population | INE *Cifras oficiales de población de los municipios españoles: Revisión del Padrón municipal*, 1996–2025 | ine.es (tables 2854–2909, one per province) |
| Farms | INE Censo Agrario 1999 (municipal results) and Censo Agrario 2020 (table 52071) | ine.es |
| Boundaries, buildings | HISDAC-ES municipal aggregates (Uhl et al. 2023, *ESSD*), CNIG boundaries | see Uhl et al. 2023 |
| Land cover | CORINE Land Cover 2018 and change layers 1990–2018 (v2020_20u1, 100 m) | land.copernicus.eu |
| WUI | Schug et al. (2023), *Nature* 621:94–99, global WUI ~2020, 10 m (EU.zip) | Zenodo record 7941460 |
| Terrain | Copernicus DEM GLO-90 | AWS open data (copernicus-dem-90m) |
| Climate | WorldClim 2.1 bioclimatic variables, 2.5 arc-min, 1970–2000 (Fick & Hijmans 2017) | worldclim.org |

All datasets were accessed between June and October 2026 (final copies saved 24 October 2026), in the versions
cited above.

## Definitions

- **Rural municipality:** density < 50 people/km² and population < 5,000 in 2000.
- **Population loss / farm-holding loss:** the negative of percent change 2000–2020 / 1999–2020, so effects > 1
  (or > 0) mean more fire with more loss. All predictors are capped at the 1st/99th percentiles and standardized
  over the 1,617 municipalities with population data (1 SD = 30.8 points of population change).
- **Burned patches:** ESFire30 patches intersecting a municipality. A fire crossing four municipalities counts in
  each, so these are not individual fires. Burned area (log(1 + % burned)) is the primary outcome.
- **Main specification:** province fixed effects; standard errors clustered by comarca agraria (88 clusters in
  the rural models: 49 Andalucía, 39 Northwest).

## Corrections made to the paper

An earlier draft was checked against this package. These were corrected in the current version; none changes a
conclusion.

- Clusters: 324 → 88 (the rural models; 324 was not the rural count).
- CORINE abandonment: "271 of 1,635" → 273 of 1,635.
- Rounding: Andalucía patch p 0.22 → 0.21; Q4 rate ratio 1.13 → 1.12; without-Q5 patch p 0.17 → 0.16;
  "27% higher" → 28% (exp(0.243) = 1.275); Table 4 Northwest intermix (forest/shrub) landscape 14.4 → 14.3;
  Andalucía non-WUI other landscape 18.3 → 18.2; Andalucía non-WUI wildland burned 54.5 → 54.4.
- Wording: the middle quintiles are "mostly" not significant (Q2 differs for burned area, p = 0.027); Andalucía
  shows no *positive* relationship; the timing test moved from Next Steps to Robustness.
- Added: Table 4 caption notes the omitted non-WUI urban class; Study Area notes the 18 post-2000 municipalities;
  Limitations notes municipal splits. The unused FIRMS dataset was removed from Data Sources.

## Notes

1. **Andalucía in the pooled model.** In the combined interaction model, Andalucía's population-loss rate ratio
   is 0.83 (0.69–1.00), p = 0.049: borderline, in the opposite direction to the Northwest.
2. **Municipal splits.** Municipalities that ceded territory to new municipalities after 2000 show inflated
   population loss (e.g., Arenas del Rey −67%, Calañas −41%; both rural Andalucía). Dropping them leaves the
   Northwest unchanged and Andalucía non-significant (patch p 0.21 → 0.14).
3. **Excluded units.** Five jointly owned territories (CNIG 53xxx; 18 km², no burned area) have no population or
   census data. Eighteen municipalities created after 2000 have no 2000 population, so they cannot be classed as
   rural or given a 2000–2020 change. Four rural Northwest municipalities lack 2020 census farm figures, so the
   Northwest models use n = 604.
4. **Table 4** omits non-WUI urban (Andalucía 0.84% of landscape, Northwest 0.06%), so its landscape columns sum
   to just under 100%.
5. **WUI resolution check.** Mean |30 m − 10 m| difference is 0.03 points for intermix and 0.01 for interface;
   the maximum is 0.16.
6. **FIRMS** columns (`firms_*`) remain in the table from an earlier draft but are not used in the paper.

## License

Code is under the MIT License (`LICENSE`); data, results, figures and text are under CC BY 4.0 (`LICENSE-CC-BY-4.0.md`).

## Citation

Hobbs, H. (2026). *Rural Depopulation, Farm Abandonment and Wildfire in Spain* — replication package.
[Add Zenodo DOI after archiving.]
