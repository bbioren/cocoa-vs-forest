"""Score point predictions against a labelled test set, overall and per slice.

  uv run python scripts/score.py --test data/test2020/test2020.csv --pred data/preds/test2020-v0.csv \
      --name v0 [--slice-col slice]

--pred is a CSV with cand_id and pred (cocoa/forest/other). Without --pred, scores the JRC GFC2020
baseline from the test set's own gfc2020 column (forest vs not-forest only).

Reports: accuracy, macro F1, per-class precision/recall, confusion matrix, per-slice accuracy, and the
EUDR-relevant binary view (forest vs not-forest). Appends a row to results/scores.csv.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ["cocoa", "forest", "other"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", required=True)
    ap.add_argument("--pred")
    ap.add_argument("--name", required=True)
    ap.add_argument("--slice-col", default=None)
    a = ap.parse_args()

    t = pd.read_csv(a.test)
    sc = a.slice_col or ("slice" if "slice" in t else "source")
    if a.pred:
        p = pd.read_csv(a.pred)[["cand_id", "pred"]]
        t = t.merge(p, on="cand_id", how="left")
        missing = t.pred.isna().sum()
        print(f"{missing} of {len(t)} points have no prediction (dropped)")
        t = t.dropna(subset=["pred"])
    else:
        t["pred"] = t.gfc2020.map({1: "forest"}).fillna("not_forest")

    y, yh = t.label, t.pred
    yb, yhb = (y == "forest"), (yh == "forest")
    rows = {"name": a.name, "test": Path(a.test).stem, "n": len(t),
            "forest_binary_acc": round((yb == yhb).mean(), 4),
            "forest_recall": round(yhb[yb].mean(), 4), "forest_precision": round(yb[yhb].mean(), 4) if yhb.any() else None}
    print(f"\n== {a.name} on {Path(a.test).stem} (n={len(t)})")
    if a.pred:
        rows["acc"] = round((y == yh).mean(), 4)
        rows["macro_f1"] = round(f1_score(y, yh, labels=CLASSES, average="macro", zero_division=0), 4)
        print(classification_report(y, yh, labels=CLASSES, zero_division=0, digits=3))
        print("confusion (rows=true, cols=pred):")
        print(pd.DataFrame(confusion_matrix(y, yh, labels=CLASSES), index=CLASSES, columns=CLASSES))
    print(f"\nforest vs not-forest: acc {rows['forest_binary_acc']}, forest recall {rows['forest_recall']}, "
          f"forest precision {rows['forest_precision']}")
    correct = (y == yh) if a.pred else (yb == yhb)
    per = t.assign(ok=correct).groupby(sc).ok.agg(["mean", "size"]).round(3)
    print(f"\nper {sc}:\n{per.to_string()}")
    for s, r in per.iterrows():
        rows[f"acc_{s}"] = r["mean"]

    out = ROOT / "results/scores.csv"
    out.parent.mkdir(exist_ok=True)
    df = pd.DataFrame([rows])
    if out.exists():
        df = pd.concat([pd.read_csv(out), df], ignore_index=True)
    df.to_csv(out, index=False)


if __name__ == "__main__":
    main()
