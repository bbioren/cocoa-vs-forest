"""Build the 2020-12-31 test set (what was each point at the EUDR cutoff?) from records, not eyeballs.

Hand-labelling shaded cocoa vs forest from sub-metre imagery turned out to be unreliable, so the
test labels come from field surveys and satellite loss records instead:

  cocoa_2020      CERSGIS farm whose last major replanting (field-verified `Replant_Fr`) was <= 2019,
                  with no Hansen loss 2020-2024 at the point. Cocoa trees stood there on the cutoff.
  forest_reserve  reserve-interior forest point (make_forest_labels.py): Hansen >= 60% in 2000, no loss
                  2001-2024, JRC GFC2020 forest. The easy forest case.
  forest_degraded CERSGIS "Open/Degraded Forest" point (2024-25 survey) with no Hansen loss 2001-2024,
                  so it was the same forest in 2020. The harder forest case.
  other_2020      CERSGIS oil palm / rubber point with no Hansen loss 2020-2024 (plantation already there).
  converted       Candidate forest -> cocoa after the cutoff: CERSGIS farm replanted 2021-2024, the point
                  has Hansen loss in 2021-2024 (tree cover >= 30% in 2000). Label: forest in 2020.
                  NOISY (replanting old cocoa also shows as loss); report separately and spot-check
                  2020 vs 2024 imagery with fetch_label_chips.py.

Except `converted` (too rare; see below), only points in the held-out 10 km blocks (labels/test_blocks.csv) are used, so no test location
was seen in training. Every point also gets the JRC GFC2020 value, for the baseline comparison.

Writes data/test2020/test2020.gpkg (layer points) and test2020.csv (lat/lon, for chips/predictions).

Run:  uv run python scripts/make_test2020.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from export_studio import BLOCKS, block_id  # noqa: E402
from make_forest_labels import GFC2020, sample_hansen, sample_raster  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GPKG = ROOT / "data/processed/cersgis_clean.gpkg"
FOREST = ROOT / "data/processed/forest_reserve_points.gpkg"
OUT = ROOT / "data/test2020"
UTM = "EPSG:32630"
SEED = 0
CAP = {"cocoa_2020": 800, "forest_reserve": 400, "forest_degraded": 400, "other_2020": 400, "converted": 400}
MIN_FARM_PX = 5
INSET_M = 15          # keep points >= 1.5 pixels inside the farm edge
CONVERT_TRIES = 25    # random points per recently replanted farm when looking for post-2020 loss


def random_point_in(geom, rng, tries=50):
    x0, y0, x1, y1 = geom.bounds
    for _ in range(tries):
        p = gpd.points_from_xy([rng.uniform(x0, x1)], [rng.uniform(y0, y1)])[0]
        if geom.contains(p):
            return p
    return geom.representative_point()


def main():
    rng = np.random.default_rng(SEED)
    test_blocks = set(pd.read_csv(BLOCKS)["block"])
    farms = gpd.read_file(GPKG, layer="cocoa_farms").to_crs(UTM)
    farms = farms[farms.area_px >= MIN_FARM_PX].copy()
    farms["held_out"] = block_id(farms).isin(test_blocks).values
    farms["inner"] = farms.geometry.buffer(-INSET_M)
    farms = farms[~farms.inner.is_empty]
    yr = pd.to_numeric(farms.replant_year, errors="coerce")
    parts = []

    # cocoa standing at the cutoff
    old = farms[(yr <= 2019) & farms.held_out].sample(frac=1, random_state=SEED)
    pts = gpd.GeoDataFrame({"object_id": old.object_id.values, "replant_year": yr[old.index].values,
                            "shade_class": old.shade_class.values},
                           geometry=[random_point_in(g, rng) for g in old.inner], crs=UTM)
    pts["lossyear"] = sample_hansen("lossyear", pts)
    pts = pts[~pts.lossyear.between(20, 24)].head(CAP["cocoa_2020"])
    parts.append(pts.assign(slice="cocoa_2020", label="cocoa"))

    # candidate forest -> cocoa conversions after the cutoff. Too rare in held-out blocks, so taken from
    # all blocks: these farms were trained on as cocoa (2024-25 imagery), which can only push the
    # model towards "cocoa" on 2020 imagery, i.e. makes this slice harder, not easier.
    new = farms[yr.between(2021, 2024)]
    cand = []
    for oid, ry, sc, g in zip(new.object_id, yr[new.index], new.shade_class, new.inner):
        cand += [(oid, ry, sc, random_point_in(g, rng)) for _ in range(CONVERT_TRIES)]
    cand = gpd.GeoDataFrame(pd.DataFrame(cand, columns=["object_id", "replant_year", "shade_class", "geometry"]),
                            crs=UTM)
    cand["lossyear"] = sample_hansen("lossyear", cand)
    cand["treecover2000"] = sample_hansen("treecover2000", cand)
    cand = cand[cand.lossyear.between(21, 24) & (cand.treecover2000 >= 30)]
    cand = cand.sample(frac=1, random_state=SEED).drop_duplicates("object_id")
    print(f"converted: {new.shape[0]} farms replanted 2021-24, {len(cand)} with post-2020 loss")
    parts.append(cand.assign(slice="converted", label="forest"))

    # forest
    fr = gpd.read_file(FOREST, layer="forest_points").to_crs(UTM)
    fr = fr[block_id(fr).isin(test_blocks)].sample(frac=1, random_state=SEED).head(CAP["forest_reserve"])
    parts.append(fr[["reserve", "geometry"]].assign(slice="forest_reserve", label="forest", lossyear=0))

    oth = gpd.read_file(GPKG, layer="other_points").to_crs(UTM)
    oth = oth[block_id(oth).isin(test_blocks)].copy()
    oth["lossyear"] = sample_hansen("lossyear", oth)
    deg = oth[(oth.cersgis_class == "Open/Degraded Forest") & (oth.lossyear == 0)]
    parts.append(deg.sample(frac=1, random_state=SEED).head(CAP["forest_degraded"])
                 [["object_id", "cersgis_class", "lossyear", "geometry"]].assign(slice="forest_degraded", label="forest"))
    pl = oth[oth.cersgis_class.isin(["Oil Palm", "Rubber"]) & ~oth.lossyear.between(20, 24)]
    parts.append(pl.sample(frac=1, random_state=SEED).head(CAP["other_2020"])
                 [["object_id", "cersgis_class", "lossyear", "geometry"]].assign(slice="other_2020", label="other"))

    t = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=UTM)
    t["block"] = block_id(t)
    print(f"sampling JRC GFC2020 remotely for {len(t)} points ...")
    t["gfc2020"] = sample_raster(GFC2020, t)
    # (We do NOT require GFC2020 forest for conversions: GFC2020 masks cocoa using a model trained on
    # CERSGIS, so it calls ~every CERSGIS farm pixel non-forest, conversions included.)
    t = t[~((t.slice == "converted") & (t.groupby("slice").cumcount() >= CAP["converted"]))].copy()
    t.insert(0, "pid", [f"t{i:04d}" for i in range(len(t))])
    ll = t.to_crs(4326)
    t["lat"], t["lon"] = ll.geometry.y.round(6), ll.geometry.x.round(6)

    OUT.mkdir(parents=True, exist_ok=True)
    t.to_file(OUT / "test2020.gpkg", layer="points", driver="GPKG")
    t.drop(columns="geometry").rename(columns={"pid": "cand_id"}).to_csv(OUT / "test2020.csv", index=False)
    print(t.groupby(["slice", "label"]).size().to_string())
    print("GFC2020 forest share by slice:\n" + t.groupby("slice").gfc2020.apply(lambda s: (s == 1).mean()).round(2).to_string())


if __name__ == "__main__":
    main()
