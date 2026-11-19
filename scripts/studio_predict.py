"""Run an OlmoEarth Studio model on our own test points through the API, and read the answers back.

Studio's API (base https://olmoearth.allenai.org/api/v1/, Bearer key in ~/olmo-earth-key.txt) lets us
create a prediction from a GeoJSON of small windows, each with its own time range, then read the
predicted class at any lon/lat. So we can score the held-out 2024-25 blocks and the 2020 test set
ourselves, with no download of rasters.

  submit   build windows around the points and start a prediction
             uv run python scripts/studio_predict.py submit --points data/test2020/test2020.csv \
                 --start 2020-01-01 --end 2020-12-31 --name test2020-v0 --model <model_id>
  status   uv run python scripts/studio_predict.py status --prediction <id>
  fetch    read the class at every point -> CSV
             uv run python scripts/studio_predict.py fetch --prediction <id> \
                 --points data/test2020/test2020.csv --out data/preds/test2020-v0.csv

--points is a CSV with cand_id, lat, lon (and optionally per-row start_time/end_time, which override
--start/--end). Windows are WINDOW_M squares centred on each point.
"""

from __future__ import annotations

import argparse
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

API = "https://olmoearth.allenai.org/api/v1"
PROJECT = "8f25c866-d8be-49e6-ac5b-8fc47846945e"
KEY = (Path.home() / "olmo-earth-key.txt").read_text().strip()
S = requests.Session()
S.headers["Authorization"] = f"Bearer {KEY}"
WINDOW_M = 160


def square(lat: float, lon: float, m: float) -> list:
    dlat = m / 2 / 111_320
    dlon = m / 2 / (111_320 * math.cos(math.radians(lat)))
    return [[[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat],
             [lon - dlon, lat + dlat], [lon - dlon, lat - dlat]]]


def submit(a):
    pts = pd.read_csv(a.points)
    if a.limit:
        pts = pts.head(a.limit)
    feats = []
    for r in pts.itertuples():
        st = getattr(r, "start_time", None) if "start_time" in pts else a.start
        en = getattr(r, "end_time", None) if "end_time" in pts else a.end
        feats.append({"type": "Feature", "id": str(r.cand_id),
                      "geometry": {"type": "Polygon", "coordinates": square(r.lat, r.lon, a.window)},
                      "properties": {"start_time": f"{st}T00:00:00Z", "end_time": f"{en}T23:59:59Z"}})
    body = {"name": a.name, "project_id": PROJECT, "model_id": a.model,
            "start_time": f"{a.start}T00:00:00Z", "end_time": f"{a.end}T23:59:59Z",
            "target_area_ids": [], "geojson": {"type": "FeatureCollection", "features": feats}}
    if a.top_k:
        body["probability_output"] = {"top_k": a.top_k}
    if a.dry_run:
        print(json.dumps(body)[:1500]); print(len(feats), "features"); return
    r = S.post(f"{API}/predictions", json=body, timeout=300)
    print(r.status_code, r.text[:2000])


def status(a):
    r = S.get(f"{API}/predictions/{a.prediction}", timeout=60).json()
    print(json.dumps(r, indent=1)[:3000])
    rr = S.post(f"{API}/prediction-results/search", json={"prediction_id": {"eq": a.prediction}}, timeout=60)
    print(rr.status_code, json.dumps(rr.json(), indent=1)[:2000])


def result_ids(pred: str) -> list[str]:
    rr = S.post(f"{API}/prediction-results/search", json={"prediction_id": {"eq": pred}}, timeout=60).json()
    return [x["id"] for x in rr.get("records", [])]


def fetch(a):
    pts = pd.read_csv(a.points)
    rids = [a.result] if a.result else result_ids(a.prediction)
    print(f"{len(rids)} prediction result(s)")

    def one(r):
        out = {"cand_id": r.cand_id, "pred": None}
        for rid in rids:
            for _ in range(3):
                try:
                    q = S.get(f"{API}/prediction-results/{rid}/pixel-value",
                              params={"lon": r.lon, "lat": r.lat}, timeout=60)
                    break
                except requests.RequestException:
                    q = None
            if q is None or not q.ok:
                out["err"] = f"HTTP {getattr(q, 'status_code', 'conn')}"
                continue
            recs = q.json().get("records") or []
            if not recs:
                continue
            b = {x["property_name"]: x for x in recs[0]["bands"]}
            cls = lambda k: (b.get(k) or {}).get("classification") or {}
            raw = lambda k: (b.get(k) or {}).get("raw_value")
            # the band is named after the dataset's label field ("label", "label_v1", ...)
            f = next((k for k in b if not k.endswith(("_class", "_prob"))), None)
            if f is None:
                continue
            out["pred"] = cls(f).get("label")
            for rank, ck in [(1, f), (2, f"{f}_rank2_class"), (3, f"{f}_rank3_class")]:
                c, pr = cls(ck).get("label"), raw(f"{f}_rank{rank}_prob")
                if c and pr is not None:
                    out[f"p_{c}"] = round(pr / 254, 4)
            out["file"] = recs[0]["prediction_result_file"]["file_name"]
            if out["pred"]:
                break
        return out

    with ThreadPoolExecutor(16) as ex:
        rows = list(ex.map(one, pts.itertuples()))
    df = pd.DataFrame(rows)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False)
    print(df.pred.value_counts(dropna=False).to_string())


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit")
    s.add_argument("--points", required=True); s.add_argument("--model", required=True)
    s.add_argument("--start"); s.add_argument("--end"); s.add_argument("--name", required=True)
    s.add_argument("--window", type=float, default=WINDOW_M); s.add_argument("--top-k", type=int, default=3)
    s.add_argument("--limit", type=int); s.add_argument("--dry-run", action="store_true")
    t = sub.add_parser("status"); t.add_argument("--prediction", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--prediction"); f.add_argument("--result"); f.add_argument("--points", required=True)
    f.add_argument("--out", required=True)
    a = ap.parse_args()
    {"submit": submit, "status": status, "fetch": fetch}[a.cmd](a)


if __name__ == "__main__":
    main()
