"""Export training labels as GeoJSON for upload to OlmoEarth Studio.

Studio takes WGS84 GeoJSON (points/polygons). Each feature has a label and a time; the field
names are mapped in the upload dialog. We use:

  label        "cocoa" | "forest" | "other"
  start_time   first day of the observation month (YYYY-MM-DD)
  end_time     last day of the observation month
  source       where the label came from (for our bookkeeping; Studio ignores it)

What goes in:
  cocoa   CERSGIS farm polygons, shrunk 10 m (one pixel) to avoid mixed edge pixels; farms < 2 px dropped
  forest  auto reserve-interior points + CERSGIS open/degraded forest points, as 30x30 m squares
  other   CERSGIS oil palm / rubber / galamsey points, as 30x30 m squares
  border  hand labels from labels/border_candidates.csv (only rows already labelled), 30x30 m squares

Points without a real date (auto forest) get a month drawn from the cocoa collection months,
so the date can't give away the class.

Spatial hold-out: we split Ghana into 10 km blocks and keep TEST_FRAC of blocks OUT of the upload.
Those labels go to data/studio/test_holdout.geojson, and we score Studio's predictions on them
ourselves. Studio's own validation split is random, so on clustered data it reads optimistic.

Writes data/studio/train_upload.geojson, data/studio/test_holdout.geojson, and
labels/test_blocks.csv (tracked, so the split is fixed).

Run:  uv run python scripts/export_studio.py
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
GPKG = ROOT / "data/processed/cersgis_clean.gpkg"
FOREST = ROOT / "data/processed/forest_reserve_points.gpkg"
BORDER = ROOT / "labels/border_candidates.csv"
OUT = ROOT / "data/studio"
BLOCKS = ROOT / "labels/test_blocks.csv"
UTM = "EPSG:32630"
BLOCK_M = 10_000
TEST_FRAC = 0.15
SQUARE_M = 30          # point labels become 3x3-pixel squares
SHRINK_M = 10          # farm polygons shrink by one pixel
MIN_FARM_PX = 2
SEED = 0


def month_range(ts: pd.Series) -> tuple[pd.Series, pd.Series]:
    start = ts.dt.to_period("M").dt.start_time
    end = ts.dt.to_period("M").dt.end_time
    return start.dt.strftime("%Y-%m-%d"), end.dt.strftime("%Y-%m-%d")


def squares(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    g = g.copy()
    g["geometry"] = g.geometry.buffer(SQUARE_M / 2, cap_style="square")
    return g


def block_id(g: gpd.GeoDataFrame) -> pd.Series:
    c = g.geometry.centroid
    return (c.x // BLOCK_M).astype(int).astype(str) + "_" + (c.y // BLOCK_M).astype(int).astype(str)


def main():
    rng = np.random.default_rng(SEED)
    farms = gpd.read_file(GPKG, layer="cocoa_farms")
    other = gpd.read_file(GPKG, layer="other_points")
    forest_auto = gpd.read_file(FOREST, layer="forest_points")

    # cocoa
    farms = farms[farms["area_px"] >= MIN_FARM_PX].copy()
    farms["geometry"] = farms.geometry.buffer(-SHRINK_M)
    farms = farms[~farms.geometry.is_empty & farms.geometry.notna()]
    farms["geometry"] = farms.geometry.simplify(2)
    cocoa = farms.assign(label="cocoa", source="cersgis_farm")[["label", "source", "collected", "geometry"]]

    # other + CERSGIS degraded forest
    oth = squares(other).assign(source="cersgis_" + other["cersgis_class"].str.lower().str.replace("[^a-z]+", "_", regex=True))
    oth = oth[["label", "source", "collected", "geometry"]]

    # auto forest: borrow months from the cocoa distribution
    months = cocoa["collected"].dropna().to_numpy()
    fa = squares(forest_auto).assign(source="reserve_interior_auto",
                                     collected=pd.to_datetime(rng.choice(months, len(forest_auto))))
    fa = fa[["label", "source", "collected", "geometry"]]

    parts = [cocoa, oth, fa]

    # border hand labels, if any are done
    if BORDER.exists():
        b = pd.read_csv(BORDER)
        b = b[b["label"].isin(["cocoa", "forest", "other"]) & b["confidence"].isin(["high", "med"])]
        if len(b):
            bg = gpd.GeoDataFrame(b, geometry=gpd.points_from_xy(b.lon, b.lat), crs=4326).to_crs(UTM)
            bg = squares(bg).assign(source="border_hand",
                                    collected=pd.to_datetime(bg["imagery_date"], errors="coerce"))
            bg["collected"] = bg["collected"].fillna(pd.Timestamp("2025-01-15"))
            parts.append(bg[["label", "source", "collected", "geometry"]])

    allg = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=UTM)
    allg["collected"] = pd.to_datetime(allg["collected"])
    allg["start_time"], allg["end_time"] = month_range(allg["collected"])
    allg["block"] = block_id(allg)

    # fixed spatial hold-out
    if BLOCKS.exists():
        test_blocks = set(pd.read_csv(BLOCKS)["block"])
    else:
        # Labels are very clustered (e.g. galamsey sits in a few blocks), so a plain random draw
        # can hold out most of one class. Try many draws; keep the one whose held-out fraction
        # per source is closest to TEST_FRAC.
        counts = allg.groupby(["block", "source"]).size().unstack(fill_value=0)
        totals = counts.sum()
        blocks = counts.index.to_numpy()
        best, best_err = None, np.inf
        for _ in range(5000):
            pick = rng.random(len(blocks)) < TEST_FRAC
            frac = counts[pick].sum() / totals
            err = float(((frac - TEST_FRAC) ** 2).max())
            if err < best_err:
                best, best_err = pick, err
        test_blocks = set(blocks[best])
        pd.DataFrame({"block": sorted(test_blocks)}).to_csv(BLOCKS, index=False)
    is_test = allg["block"].isin(test_blocks)

    OUT.mkdir(parents=True, exist_ok=True)
    cols = ["label", "start_time", "end_time", "source", "block", "geometry"]
    train = allg.loc[~is_test, cols].to_crs(4326)
    test = allg.loc[is_test, cols].to_crs(4326)
    for name, g in [("train_upload", train), ("test_holdout", test)]:
        p = OUT / f"{name}.geojson"
        p.unlink(missing_ok=True)
        g.to_file(p, driver="GeoJSON", COORDINATE_PRECISION=6)

    summary = {
        "train": train.groupby(["label", "source"]).size().to_dict(),
        "test": test.groupby(["label", "source"]).size().to_dict(),
        "n_train": len(train), "n_test": len(test),
        "test_blocks": len(test_blocks), "all_blocks": int(allg["block"].nunique()),
        "train_mb": round((OUT / "train_upload.geojson").stat().st_size / 1e6, 1),
    }
    summary = {k: ({f"{a}/{b}": v for (a, b), v in d.items()} if isinstance(d, dict) else d) for k, d in summary.items()}
    (OUT / "export_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
