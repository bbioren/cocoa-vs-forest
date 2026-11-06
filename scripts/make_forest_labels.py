"""Automatic "forest" training points from the interiors of Ghana's forest reserves.

CERSGIS has no intact-forest class, so we sample points inside forest reserves and keep only
those that every check agrees are forest:

  1. inside an OpenStreetMap protected area / forest reserve in Ghana, >= BUFFER_IN m from its edge
     (reserve edges are where encroaching cocoa is)
  2. in the cocoa belt (within NEAR_LABELS_KM of a CERSGIS label), so savanna parks are excluded
  3. >= MIN_DIST_LABEL_M from any CERSGIS cocoa farm or non-forest point
  4. JRC GFC2020 V4 = forest at the EUDR cutoff (CC BY 4.0, read remotely from the JRC COG)
  5. Hansen GFC v1.12 tree cover in 2000 >= 60% and no loss 2001-2024 (so still forest when the
     2024-25 training imagery was taken)

Writes data/processed/forest_reserve_points.gpkg and figures/06_forest_points.png.

Caveat for the paper: GFC2020 V3+ used the Forest Data Partnership cocoa layer as a mask, so
these labels are not independent of that product. Use them for training only, not for evaluation.

Inputs (see scripts/README.md):
  data/raw/osm/ghana-latest.osm.pbf   Geofabrik Ghana extract (ODbL)
  data/raw/hansen/*.tif               Hansen GFC-2024-v1.12 treecover2000 + lossyear, tiles 10N_010W, 10N_000E
  data/processed/cersgis_clean.gpkg   from clean_cersgis.py

Run:  uv run python scripts/make_forest_labels.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyogrio
import rasterio
from shapely.geometry import Point

ROOT = Path(__file__).resolve().parents[1]
OSM = ROOT / "data/raw/osm/ghana-latest.osm.pbf"
HANSEN = ROOT / "data/raw/hansen"
GPKG = ROOT / "data/processed/cersgis_clean.gpkg"
OUT = ROOT / "data/processed/forest_reserve_points.gpkg"
FIG = ROOT / "figures/06_forest_points.png"
BOUNDS = ROOT / "data/raw/boundaries/gha_adm1.geojson"
GFC2020 = "/vsicurl/https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/FOREST/GFC2020/LATEST/single-cog/JRC_GFC2020_V4_COG.tif"
UTM = "EPSG:32630"

BUFFER_IN = 500          # m inward from reserve edge
NEAR_LABELS_KM = 40      # keep reserves near the CERSGIS cocoa landscape
MIN_DIST_LABEL_M = 1000  # stay away from known non-forest labels
N_CANDIDATES = 30000
MAX_PER_RESERVE = 300    # stop big reserves dominating
MIN_TREECOVER = 60
SEED = 0

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MULTIRANGE", "YES")
os.environ.setdefault("VSI_CACHE", "TRUE")


def reserves(labels_hull) -> gpd.GeoDataFrame:
    g = pyogrio.read_dataframe(
        OSM, layer="multipolygons", columns=["osm_id", "osm_way_id", "name", "boundary", "leisure", "landuse"],
        where="boundary IN ('protected_area','national_park','forest') OR leisure='nature_reserve' "
              "OR (landuse='forest' AND name LIKE '%eserve%')",
    ).to_crs(UTM)
    ghana = gpd.read_file(BOUNDS).to_crs(UTM).union_all()
    g = g[g.geometry.representative_point().within(ghana)]
    g = g[g.intersects(labels_hull.buffer(NEAR_LABELS_KM * 1000))]
    g["name"] = g["name"].fillna("unnamed")
    # overlapping duplicates (e.g. the same reserve as way and relation): dissolve by name
    g = g.dissolve(by="name", as_index=False)[["name", "geometry"]]
    g["interior"] = g.buffer(-BUFFER_IN)
    g = g[~g["interior"].is_empty]
    g["interior_km2"] = g["interior"].area / 1e6
    return g


def sample_in(polys: gpd.GeoSeries, n: int, rng) -> gpd.GeoDataFrame:
    """Uniform random points over the union of polygons, tagged with the polygon index."""
    areas = polys.area.to_numpy()
    counts = rng.multinomial(n, areas / areas.sum())
    rows = []
    for (idx, geom), k in zip(polys.items(), counts):
        if k == 0:
            continue
        x0, y0, x1, y1 = geom.bounds
        got = []
        while len(got) < k:
            xs = rng.uniform(x0, x1, k * 3); ys = rng.uniform(y0, y1, k * 3)
            pts = gpd.GeoSeries(gpd.points_from_xy(xs, ys), crs=UTM)
            got.extend(pts[pts.within(geom)].tolist())
        rows += [(idx, p) for p in got[:k]]
    return gpd.GeoDataFrame({"reserve_idx": [r[0] for r in rows]}, geometry=[r[1] for r in rows], crs=UTM)


def sample_raster(path: str, pts: gpd.GeoDataFrame) -> np.ndarray:
    with rasterio.open(path) as r:
        p = pts.to_crs(r.crs)
        return np.array([v[0] for v in r.sample(zip(p.geometry.x, p.geometry.y))])


def sample_hansen(layer: str, pts: gpd.GeoDataFrame) -> np.ndarray:
    out = np.full(len(pts), -1, dtype=int)
    lon = pts.to_crs(4326).geometry.x.to_numpy()
    for tile, mask in [("10N_010W", lon < 0), ("10N_000E", lon >= 0)]:
        if mask.any():
            out[mask] = sample_raster(str(HANSEN / f"Hansen_GFC-2024-v1.12_{layer}_{tile}.tif"), pts[mask])
    return out


def main():
    rng = np.random.default_rng(SEED)
    farms = gpd.read_file(GPKG, layer="cocoa_farms")
    other = gpd.read_file(GPKG, layer="other_points")
    labels_hull = pd.concat([farms.geometry.centroid, other.geometry]).union_all().convex_hull

    res = reserves(labels_hull)
    print(f"{len(res)} reserves in the cocoa landscape, interior area {res.interior_km2.sum():,.0f} km²")

    cand = sample_in(res["interior"], N_CANDIDATES, rng)
    cand["reserve"] = res["name"].reindex(cand["reserve_idx"]).to_numpy()
    log = {"candidates": len(cand)}

    nonforest = pd.concat([farms.geometry, other[other.label != "forest"].geometry])
    near = gpd.sjoin_nearest(cand[["geometry"]], gpd.GeoDataFrame(geometry=nonforest, crs=UTM),
                             max_distance=MIN_DIST_LABEL_M, how="inner")
    cand = cand[~cand.index.isin(near.index)]
    log["after_label_distance"] = len(cand)

    print("sampling Hansen ...")
    cand["treecover2000"] = sample_hansen("treecover2000", cand)
    cand["lossyear"] = sample_hansen("lossyear", cand)
    cand = cand[(cand.treecover2000 >= MIN_TREECOVER) & (cand.lossyear == 0)]
    log["after_hansen"] = len(cand)

    print(f"sampling GFC2020 V4 remotely for {len(cand)} points ...")
    cand["gfc2020"] = sample_raster(GFC2020, cand)
    cand = cand[cand.gfc2020 == 1]
    log["after_gfc2020"] = len(cand)

    cand = cand.sample(frac=1, random_state=SEED)
    cand = cand[cand.groupby("reserve").cumcount() < MAX_PER_RESERVE]
    cand["label"] = "forest"
    cand["source"] = "reserve_interior_auto"
    log["final"] = len(cand)
    log["reserves_used"] = int(cand["reserve"].nunique())
    log["per_reserve"] = cand["reserve"].value_counts().to_dict()

    cand = cand.drop(columns="reserve_idx")
    OUT.unlink(missing_ok=True)
    cand.to_file(OUT, layer="forest_points", driver="GPKG")
    res.drop(columns="interior").to_file(OUT, layer="reserves", driver="GPKG")
    (OUT.parent / "forest_labels_log.json").write_text(json.dumps(log, indent=2))
    print(json.dumps({k: v for k, v in log.items() if k != "per_reserve"}, indent=2))

    fig, ax = plt.subplots(figsize=(8, 8))
    gpd.read_file(BOUNDS).to_crs(UTM).boundary.plot(ax=ax, color="0.6", lw=0.5)
    res.plot(ax=ax, color="#d9f0d3", edgecolor="#5aae61", lw=0.4)
    farms.centroid.plot(ax=ax, markersize=0.5, color="#8c510a", label="CERSGIS cocoa")
    cand.plot(ax=ax, markersize=1.5, color="#1b7837", label=f"auto forest points ({len(cand):,})")
    x0, y0, x1, y1 = labels_hull.buffer(30000).bounds
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_axis_off()
    ax.legend(markerscale=6, loc="upper right"); ax.set_title("Forest reserves (OSM) and auto forest labels")
    fig.tight_layout(); fig.savefig(FIG, dpi=150)
    print("wrote", OUT, FIG)


if __name__ == "__main__":
    main()
