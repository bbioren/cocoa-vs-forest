# Label pipeline

Run from the repo root with [uv](https://docs.astral.sh/uv/). `uv sync` once, then:

```bash
# 1. raw downloads (go to data/raw/, git-ignored)
mkdir -p data/raw/cersgis_v2 data/raw/osm data/raw/hansen
curl -L -o data/raw/cersgis_v2/cersgis_v2.zip \
  "https://zenodo.org/api/records/16579443/files/Reference_Dataset_Ghana_Cocoa_2024_2025.zip/content"
unzip -o data/raw/cersgis_v2/cersgis_v2.zip -d data/raw/cersgis_v2
curl -L -o data/raw/osm/ghana-latest.osm.pbf https://download.geofabrik.de/africa/ghana-latest.osm.pbf
for l in treecover2000 lossyear; do for t in 10N_010W 10N_000E; do
  curl -L -o data/raw/hansen/Hansen_GFC-2024-v1.12_${l}_${t}.tif \
    "https://storage.googleapis.com/earthenginepartners-hansen/GFC-2024-v1.12/Hansen_GFC-2024-v1.12_${l}_${t}.tif"
done; done   # ~850 MB

# 2. build labels
uv run python scripts/clean_cersgis.py          # -> data/processed/cersgis_clean.gpkg
uv run python scripts/plot_cersgis.py           # -> figures/01-05
uv run python scripts/make_forest_labels.py     # -> data/processed/forest_reserve_points.gpkg, figures/06
uv run python scripts/make_border_candidates.py # -> labels/border_candidates.* (only re-run to regenerate; it overwrites!)
```

The GFC2020 V4 map is read remotely from the JRC's 38 GB COG, so it isn't downloaded. Ghana's boundary (geoBoundaries) downloads automatically.

## What each step does

**`clean_cersgis.py`**
- Drops 4 null farm geometries, 274 duplicate points, 32 points whose location appears twice with conflicting classes, and 1 non-cocoa point inside a cocoa farm.
- Reprojects to UTM 30N.
- Adds farm area in 10 m pixels and flags 311 farms under 2 px.
- Simplifies canopy, weeds and shade into short codes.
- Maps CERSGIS classes to project classes: *Open/Degraded Forest* → `forest`; oil palm, rubber and galamsey → `other`.
- Writes a log to `data/processed/cleaning_log.json`.

**`make_forest_labels.py`** keeps a forest point only if all of these hold:
- inside an OSM forest reserve or park in the cocoa landscape, at least 500 m from its edge
- at least 1 km from any CERSGIS non-forest label
- Hansen tree cover ≥60% in 2000 and no loss through 2024
- GFC2020 V4 = forest

At most 300 points per reserve. Result: 6,255 points in 60 reserves. Only about 43% of reserve interiors pass the Hansen check, because the reserves are heavily degraded.

**`make_border_candidates.py`**: see `labels/README.md`.

## Label counts so far

| class | source | n | geometry |
|---|---|---|---|
| cocoa | CERSGIS farms | 21,027 | polygons (median ≈ 24 px) |
| forest | reserve interiors (auto) | 6,255 | points |
| forest | CERSGIS open/degraded forest | 1,606 | points |
| other | CERSGIS oil palm 7,259 / galamsey 7,904 / rubber 2,959 | 18,122 | points |
| forest/cocoa/other | hand labels (border) | 600 to do | points |

## Known issues / caveats

- **Circularity with GFC2020.** V3+ masks cocoa using the Forest Data Partnership cocoa model, which was trained partly on CERSGIS points. Near CERSGIS farms it maps almost nothing as forest. Don't use GFC2020 or FDaP as an independent evaluation on these labels.
- **Reserve bias.** Forest labels come only from reserve interiors. The border hand labels exist to counter this.
- **Partial farms.** CERSGIS farm polygons cover only parts of farms. Unlabelled pixels next to farms are *not* negatives; treat them as ignore/no-data when rasterising.
- **Collection dates.** Labels date from 2024–25, so pair them with 2024–25 imagery. Apply the model to 2020 only at inference time.

## Data sources and licences

| data | licence | in git? |
|---|---|---|
| CERSGIS Ghana cocoa reference dataset v2.0, doi:10.5281/zenodo.16579443 | CC BY 4.0 | no (download script); derived hand labels yes |
| JRC GFC2020 V4, doi:10.2905/JRC.3KATEH8 | CC BY 4.0 | no |
| Hansen et al. Global Forest Change 2000–2024 v1.12 | CC BY 4.0 | no |
| OpenStreetMap via Geofabrik | ODbL | no |
| geoBoundaries GHA ADM1 | CC BY 4.0 | no |
