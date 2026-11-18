"""Fetch a dated high-resolution image chip around each point, for the labelling page.

For every point we check each Esri World Imagery "Wayback" release in a window, read the actual
capture date of the imagery at that point from Esri's metadata service, and keep the release whose
capture date is closest to TARGET. We then stitch 3x3 zoom-17 tiles (~1.2 m/px; zoom 18 here is only upsampled) into one chip
centred on the point.

Outputs (git-ignored; Esri imagery is not ours to redistribute):
  <out>/chips/<cand_id>.jpg     384x384 px, ~450 m across, point at the centre
  <out>/points.json             id, lat, lon, labeler, capture date, source, resolution, release

Usage:
  uv run python scripts/fetch_label_chips.py --points labels/border_candidates.csv \
      --target 2025-01-01 --from 2024-01-01 --to 2026-12-31 --out data/chips/border
  # later, for the 2020 test set:
  uv run python scripts/fetch_label_chips.py --points labels/test2020_candidates.csv \
      --target 2020-12-31 --from 2020-01-01 --to 2023-12-31 --out data/chips/test2020

Imagery: Esri World Imagery Wayback (Maxar, Airbus, etc.). Attribution is shown on the page.
"""

from __future__ import annotations

import argparse
import io
import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from PIL import Image

CONFIG = "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json"
TILE = ("https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/"
        "default028mm/MapServer/tile/{rel}/{z}/{y}/{x}")
Z = 17
CHIP = 384
META_LAYERS = (6, 5, 7)  # 1.2 m (zoom 17's band), 60 cm, 2.4 m metadata layers

S = requests.Session()
S.headers["User-Agent"] = "cocoa-vs-forest-research/0.1"


def releases(d0: date, d1: date) -> list[dict]:
    cfg = S.get(CONFIG, timeout=60).json()
    out = []
    for k, v in cfg.items():
        d = date.fromisoformat(v["itemTitle"].split("Wayback ")[1].rstrip(")"))
        if d0 <= d <= d1:
            out.append({"rel": int(k), "release_date": d, "meta": v["metadataLayerUrl"]})
    return sorted(out, key=lambda r: r["release_date"])


def capture_info(meta_url: str, lat: float, lon: float) -> dict | None:
    for layer in META_LAYERS:
        try:
            r = S.get(f"{meta_url}/{layer}/query", timeout=30, params=dict(
                geometry=f"{lon},{lat}", geometryType="esriGeometryPoint", inSR=4326,
                spatialRel="esriSpatialRelIntersects", returnGeometry="false", f="json",
                outFields="SRC_DATE,SRC_RES,NICE_NAME,NICE_DESC"))
            feats = r.json().get("features") or []
        except Exception:
            continue
        if feats:
            a = feats[0]["attributes"]
            s = str(a.get("SRC_DATE") or "")
            if len(s) == 8:
                return {"capture_date": f"{s[:4]}-{s[4:6]}-{s[6:]}", "res_m": a.get("SRC_RES"),
                        "source": " ".join(x for x in [a.get("NICE_DESC"), a.get("NICE_NAME")] if x)}
    return None


def tile_xy(lat: float, lon: float, z: int) -> tuple[float, float]:
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def chip(rel: int, lat: float, lon: float) -> Image.Image:
    fx, fy = tile_xy(lat, lon, Z)
    cx, cy = int(fx), int(fy)
    canvas = Image.new("RGB", (256 * 3, 256 * 3))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            r = None
            for _ in range(4):  # Wayback drops connections under load; retry
                try:
                    r = S.get(TILE.format(rel=rel, z=Z, y=cy + dy, x=cx + dx), timeout=30, allow_redirects=True)
                    break
                except requests.RequestException:
                    continue
            if r is not None and r.ok and r.headers.get("content-type", "").startswith("image"):
                canvas.paste(Image.open(io.BytesIO(r.content)).convert("RGB"), ((dx + 1) * 256, (dy + 1) * 256))
    px, py = (fx - cx + 1) * 256, (fy - cy + 1) * 256  # point position on the canvas
    h = CHIP // 2
    return canvas.crop((int(px - h), int(py - h), int(px + h), int(py + h)))


def process(row, rels, target: date, out: Path) -> dict:
    lat, lon = float(row["lat"]), float(row["lon"])
    best, seen = None, set()
    for r in rels:
        info = capture_info(r["meta"], lat, lon)
        if not info or info["capture_date"] in seen:
            continue
        seen.add(info["capture_date"])
        gap = abs((date.fromisoformat(info["capture_date"]) - target).days)
        if best is None or gap < best["gap_days"]:
            best = {**info, "rel": r["rel"], "release_date": str(r["release_date"]), "gap_days": gap}
    m_per_px = 156543.03392 * math.cos(math.radians(lat)) / 2 ** Z
    rec = {"id": row["cand_id"], "lat": lat, "lon": lon, "labeler": row.get("labeler", ""),
           "m_per_px": round(m_per_px, 3), "chip_px": CHIP}
    if best is None:
        return {**rec, "error": "no imagery metadata"}
    img = chip(best["rel"], lat, lon)
    img.save(out / "chips" / f"{row['cand_id']}.jpg", quality=72, optimize=True, progressive=True)
    return {**rec, **{k: best[k] for k in ("capture_date", "res_m", "source", "rel", "release_date", "gap_days")},
            "all_capture_dates": sorted(seen)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--points", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--from", dest="d0", required=True)
    ap.add_argument("--to", dest="d1", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=40)
    a = ap.parse_args()

    out = Path(a.out); (out / "chips").mkdir(parents=True, exist_ok=True)
    rels = releases(date.fromisoformat(a.d0), date.fromisoformat(a.d1))
    print(f"{len(rels)} Wayback releases between {a.d0} and {a.d1}")
    pts = pd.read_csv(a.points).to_dict("records")
    target = date.fromisoformat(a.target)
    with ThreadPoolExecutor(a.workers) as ex:
        recs = list(ex.map(lambda r: process(r, rels, target, out), pts))
    (out / "points.json").write_text(json.dumps(recs, indent=1))
    df = pd.DataFrame(recs)
    print(df.get("error", pd.Series(dtype=str)).value_counts(dropna=False).to_dict())
    if "capture_date" in df:
        d = pd.to_datetime(df["capture_date"])
        print("capture dates:", d.min().date(), "→", d.max().date(), "| median gap days:", df["gap_days"].median())
        print(d.dt.year.value_counts().sort_index().to_dict())


if __name__ == "__main__":
    main()
