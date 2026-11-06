"""Candidate points for hand labelling the cocoa–forest border.

The auto forest labels come from reserve interiors, which risks the model learning "reserve-looking
= forest". These candidates sit just outside CERSGIS cocoa farms (30–500 m away), which is where shaded
cocoa and real forest get confused. About two thirds have high Hansen tree cover (>=60% in 2000, no loss
through 2024), i.e. either forest or shaded cocoa (the confusion we care about); the rest are random.

We tried stratifying by GFC2020 V4 instead, but it maps almost nothing near CERSGIS farms as forest
(1/400 farm centroids, 5/400 points 300 m away), consistent with V3+ masking cocoa using the FDaP
cocoa model, which was itself trained partly on CERSGIS points. GFC2020 is kept as a column for reference.

Writes, in labels/ (tracked in git):
  border_candidates.gpkg   layer "candidates" with an empty `label` column to fill in (QGIS)
  border_candidates.kml    same points for Google Earth Pro
  border_candidates.csv    same points with lat/lon, for a spreadsheet workflow

Labelling instructions are in labels/README.md.

Run:  uv run python scripts/make_border_candidates.py
"""

from __future__ import annotations

import os
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from make_forest_labels import sample_hansen

ROOT = Path(__file__).resolve().parents[1]
GPKG = ROOT / "data/processed/cersgis_clean.gpkg"
OUT = ROOT / "labels"
GFC2020 = "/vsicurl/https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/FOREST/GFC2020/LATEST/single-cog/JRC_GFC2020_V4_COG.tif"
UTM = "EPSG:32630"
N_TOTAL = 600
FRAC_TREED = 2 / 3
RING = (30, 2000)  # metres outside the farm edge
SEED = 1

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")


def main():
    rng = np.random.default_rng(SEED)
    farms = gpd.read_file(GPKG, layer="cocoa_farms")
    other = gpd.read_file(GPKG, layer="other_points")

    # one random point per sampled farm, at a random bearing and distance outside its edge
    picks = farms.sample(min(len(farms), N_TOTAL * 15), random_state=SEED)
    c = picks.geometry.centroid
    ang = rng.uniform(0, 2 * np.pi, len(picks))
    # radius ≈ distance from centroid to edge + ring distance
    r_edge = np.sqrt(picks.area.to_numpy() / np.pi)
    dist = r_edge + rng.uniform(*RING, len(picks))
    pts = gpd.GeoDataFrame(
        {"near_farm_id": picks["object_id"].to_numpy(), "region": picks["region"].to_numpy(),
         "district": picks["district"].to_numpy()},
        geometry=gpd.points_from_xy(c.x + dist * np.cos(ang), c.y + dist * np.sin(ang)), crs=UTM)

    # drop points that land inside any labelled farm or right on a CERSGIS point
    inside = gpd.sjoin(pts, farms[["geometry"]], predicate="within", how="inner").index
    pts = pts[~pts.index.isin(inside)]
    close = gpd.sjoin_nearest(pts[["geometry"]], other[["geometry"]], max_distance=30, how="inner").index
    pts = pts[~pts.index.isin(close)]

    with rasterio.open(GFC2020) as r:
        p = pts.to_crs(r.crs)
        pts["gfc2020_forest"] = [int(v[0] == 1) for v in r.sample(zip(p.geometry.x, p.geometry.y))]

    pts["treecover2000"] = sample_hansen("treecover2000", pts)
    pts["lossyear"] = sample_hansen("lossyear", pts)
    pts["treed"] = ((pts.treecover2000 >= 60) & (pts.lossyear == 0)).astype(int)

    n_f = int(N_TOTAL * FRAC_TREED)
    f = pts[pts.treed == 1]; nf = pts[pts.treed == 0]
    sel = pd.concat([f.sample(min(n_f, len(f)), random_state=SEED),
                     nf.sample(min(N_TOTAL - n_f, len(nf)), random_state=SEED)])
    sel = sel.sample(frac=1, random_state=SEED).reset_index(drop=True)  # shuffle so labellers are blind to strata
    sel.insert(0, "cand_id", [f"B{i:04d}" for i in range(len(sel))])
    sel["labeler"] = np.where(sel.index % 2 == 0, "ben", "kyvalya")
    for col in ["label", "confidence", "imagery_date", "notes"]:
        sel[col] = ""

    ll = sel.to_crs(4326)
    sel["lon"] = ll.geometry.x.round(6); sel["lat"] = ll.geometry.y.round(6)
    sel["google_maps"] = "https://www.google.com/maps/@" + sel.lat.astype(str) + "," + sel.lon.astype(str) + ",300m/data=!3m1!1e3"

    OUT.mkdir(exist_ok=True)
    out = OUT / "border_candidates.gpkg"
    out.unlink(missing_ok=True)
    sel.to_file(out, layer="candidates", driver="GPKG")
    # empty polygon layer for optional hand-drawn forest/cocoa polygons
    gpd.GeoDataFrame({"label": pd.Series(dtype=str), "labeler": pd.Series(dtype=str),
                      "imagery_date": pd.Series(dtype=str), "notes": pd.Series(dtype=str)},
                     geometry=gpd.GeoSeries([], crs=UTM)).to_file(out, layer="hand_polygons", driver="GPKG")
    kml = OUT / "border_candidates.kml"; kml.unlink(missing_ok=True)
    ll.assign(Name=sel.cand_id, Description="labeler: " + sel.labeler)[["Name", "Description", "geometry"]].to_file(kml, driver="KML")
    sel.drop(columns="geometry").to_csv(OUT / "border_candidates.csv", index=False)
    print('treed', sel.treed.value_counts().to_dict(), 'gfc', sel.gfc2020_forest.value_counts().to_dict(), sel.labeler.value_counts().to_dict())
    print("wrote", out, kml, OUT / "border_candidates.csv")


if __name__ == "__main__":
    main()
