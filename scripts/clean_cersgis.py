"""Clean the CERSGIS Ghana cocoa reference dataset (Zenodo 10.5281/zenodo.16579443, v2.0, CC BY 4.0).

Reads the raw shapefiles from data/raw/cersgis_v2/ and writes cleaned layers to
data/processed/cersgis_clean.gpkg:

  cocoa_farms        cocoa farm polygons (UTM 30N), with derived fields
  cocoa_shadeless    "homogeneous" shadeless sub-polygons drawn inside farms
  other_points       non-cocoa points with our project class (forest / other)

Also writes data/processed/cleaning_log.json with counts of what was dropped.

Run:  uv run python scripts/clean_cersgis.py
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import make_valid

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw/cersgis_v2/Reference_Dataset_Ghana_Cocoa_2024_2025/data"
OUT = ROOT / "data/processed"
UTM = "EPSG:32630"  # WGS84 / UTM zone 30N covers all of Ghana's cocoa belt
PIXEL_M2 = 100.0  # one 10 m Sentinel-2 pixel

# Ghana bounding box with a small margin, to catch mis-geocoded features
GHANA_BBOX = (-3.4, 4.6, 1.3, 11.3)

# CERSGIS "other land use" class -> our project class
OTHER_CLASS_MAP = {
    "Open/Degraded Forest": "forest",  # EUDR (FAO) definition: degraded forest is still forest
    "Oil Palm": "other",
    "Rubber": "other",
    "Galamsey": "other",  # informal gold mining
}

CANOPY_MAP = {
    "The canopy of the cocoa trees is completely closed, and sunlight does not reach the ground": "closed",
    "There are gaps in an otherwise closed canopy, and sunlight can reach the ground in some places": "gaps",
    "Sunlight penetrates the canopy of the cocoa trees because it is not closed": "open",
}
WEED_MAP = {
    "There are no weeds between cocoa trees": "none",
    "There are short weeds between cocoa trees": "short",
    "There are tall weeds between cocoa trees": "tall",
}


def in_bbox(gdf: gpd.GeoDataFrame) -> pd.Series:
    c = gdf.geometry.representative_point()
    x0, y0, x1, y1 = GHANA_BBOX
    return c.x.between(x0, x1) & c.y.between(y0, y1)


def fix_geoms(gdf: gpd.GeoDataFrame, log: dict, name: str) -> gpd.GeoDataFrame:
    n0 = len(gdf)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    log[f"{name}_null_or_empty"] = n0 - len(gdf)

    bad = ~gdf.is_valid
    log[f"{name}_invalid_repaired"] = int(bad.sum())
    if bad.any():
        gdf.loc[bad, "geometry"] = gdf.loc[bad, "geometry"].apply(make_valid)
        # make_valid can return GeometryCollections; keep only the polygonal part
        gdf["geometry"] = gdf.geometry.apply(
            lambda g: g if g.geom_type in ("Polygon", "MultiPolygon", "Point")
            else gpd.GeoSeries([g]).explode(index_parts=False)
            .loc[lambda s: s.geom_type.isin(["Polygon", "MultiPolygon"])].union_all()
        )
        gdf = gdf[~gdf.geometry.is_empty]

    keep = in_bbox(gdf)
    log[f"{name}_outside_ghana_bbox"] = int((~keep).sum())
    return gdf[keep]


def clean_cocoa(path: Path, log: dict, name: str) -> gpd.GeoDataFrame:
    g = gpd.read_file(path)
    log[f"{name}_raw"] = len(g)
    g = fix_geoms(g, log, name)

    dup = g.geometry.to_wkb().duplicated()
    log[f"{name}_duplicate_geoms"] = int(dup.sum())
    g = g[~dup]

    g = g.to_crs(UTM)
    g["area_m2"] = g.area
    g["area_px"] = g["area_m2"] / PIXEL_M2
    # Farms smaller than ~2 pixels can't be resolved at 10 m; keep but flag
    g["too_small"] = g["area_px"] < 2

    g["canopy"] = g["Canopy_Sta"].map(CANOPY_MAP).fillna("unknown")
    g["weeds"] = g["Weed_Statu"].map(WEED_MAP).fillna("unknown")
    g["has_shade_trees"] = g["Shd_Trees"].eq("Yes")
    g["n_shade_trees"] = g["No_Shd_Tre"]
    # Simple shade class for stratified reporting later
    g["shade_class"] = pd.cut(
        g["n_shade_trees"], bins=[-1, 0, 5, 1000], labels=["none", "low(1-5)", "high(6+)"]
    ).astype(str)
    g["replant_year"] = g["Replant_Fr"].where(g["Replant_Fr"] != 9999)
    g["collected"] = pd.to_datetime(g["Date"], format="%Y-%m", errors="coerce")
    g["label"] = "cocoa"

    keep = [
        "OBJECT_ID", "label", "Region", "District", "collected", "canopy", "weeds",
        "has_shade_trees", "n_shade_trees", "shade_class", "Cocoa_Vari", "Tree_Speci",
        "replant_year", "area_m2", "area_px", "too_small", "geometry",
    ]
    return g[keep].rename(columns={"OBJECT_ID": "object_id", "Region": "region",
                                   "District": "district", "Cocoa_Vari": "cocoa_variety",
                                   "Tree_Speci": "shade_tree_species"})


def clean_other(path: Path, log: dict) -> gpd.GeoDataFrame:
    g = gpd.read_file(path)
    log["other_raw"] = len(g)
    g = fix_geoms(g, log, "other")

    # Same location labelled twice: keep one if labels agree, drop both if they conflict
    key = g.geometry.to_wkb()
    n_classes = g.groupby(key)["CLASS"].transform("nunique")
    log["other_conflicting_dup_points"] = int((n_classes > 1).sum())
    g = g[n_classes == 1]
    dup = g.geometry.to_wkb().duplicated()
    log["other_duplicate_points"] = int(dup.sum())
    g = g[~dup]

    g = g.to_crs(UTM)
    g["label"] = g["CLASS"].map(OTHER_CLASS_MAP)
    unmapped = g["label"].isna()
    log["other_unmapped_class"] = int(unmapped.sum())
    g = g[~unmapped]
    g["collected"] = pd.to_datetime(
        g["YEAR"].astype(str) + "-" + g["MONTH"].astype(str), format="%Y-%B", errors="coerce"
    )
    return g[["OBJECTID", "label", "CLASS", "PLANTATION", "REGION", "collected", "geometry"]].rename(
        columns={"OBJECTID": "object_id", "CLASS": "cersgis_class",
                 "PLANTATION": "plantation", "REGION": "region"})


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    log: dict = {}

    farms = clean_cocoa(RAW / "cocoa_farm_polygons/cocoa_farms.shp", log, "cocoa")
    shadeless = clean_cocoa(RAW / "cocoa_farm_polygons/homogeneous_cocoa_farm.shp", log, "shadeless")
    other = clean_other(RAW / "other_land_uses/other_land_uses.shp", log)

    # Shadeless sub-polygons should sit inside a farm; flag the ones that don't
    inside = gpd.sjoin(shadeless[["geometry"]], farms[["geometry"]], predicate="intersects", how="left")
    orphan = inside.groupby(level=0)["index_right"].apply(lambda s: s.isna().all())
    shadeless["inside_farm"] = ~orphan.reindex(shadeless.index).fillna(True)
    log["shadeless_not_inside_any_farm"] = int((~shadeless["inside_farm"]).sum())

    # Non-cocoa points that fall inside a cocoa farm are label conflicts
    hit = gpd.sjoin(other[["geometry"]], farms[["geometry"]], predicate="within", how="inner")
    conflict = other.index.isin(hit.index)
    log["other_points_inside_cocoa_farm_dropped"] = int(conflict.sum())
    other = other[~conflict]

    out = OUT / "cersgis_clean.gpkg"
    out.unlink(missing_ok=True)
    farms.to_file(out, layer="cocoa_farms", driver="GPKG")
    shadeless.to_file(out, layer="cocoa_shadeless", driver="GPKG")
    other.to_file(out, layer="other_points", driver="GPKG")

    log["final_cocoa_farms"] = len(farms)
    log["final_cocoa_farms_too_small"] = int(farms["too_small"].sum())
    log["final_shadeless"] = len(shadeless)
    log["final_other_points"] = other["label"].value_counts().to_dict()
    log["final_other_by_cersgis_class"] = other["cersgis_class"].value_counts().to_dict()
    (OUT / "cleaning_log.json").write_text(json.dumps(log, indent=2, default=str))
    print(json.dumps(log, indent=2, default=str))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
