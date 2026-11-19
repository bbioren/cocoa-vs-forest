"""Combine two models' class probabilities, with per-class weights, at no extra compute.

v0 (natural class mix) is under-confident on forest; v1 (rebalanced) over-calls forest on 2020 cocoa.
A blend  p = a*p_A + (1-a)*p_B, then  argmax_c w_c * p_c  covers everything in between (the weights are
a prior-shift correction). The blend weight and class weights are chosen on the 2024-25 holdout only, then
applied unchanged to the 2020 test set, so the 2020 numbers stay honest.

  uv run python scripts/combine.py --a v0 --b v1
writes data/preds/{holdout2024,test2020}-<a>+<b>.csv, which score.py can score.
"""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ["cocoa", "forest", "other"]
PRED = ROOT / "data/preds"


def probs(name: str, test: str) -> pd.DataFrame:
    p = pd.read_csv(PRED / f"{test}-{name}.csv").dropna(subset=["pred"]).set_index("cand_id")
    return p[[f"p_{c}" for c in CLASSES]].fillna(0.0)


def decide(pa, pb, a, w):
    p = a * pa.values + (1 - a) * pb.values
    return np.array(CLASSES)[np.argmax(p * np.array(w), axis=1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="v0"); ap.add_argument("--b", default="v1")
    a_ = ap.parse_args()

    tests = {"holdout2024": ROOT / "data/test2024/holdout2024.csv", "test2020": ROOT / "data/test2020/test2020.csv"}
    data = {}
    for t, path in tests.items():
        pa, pb = probs(a_.a, t), probs(a_.b, t)
        ids = pa.index.intersection(pb.index)
        y = pd.read_csv(path).set_index("cand_id").loc[ids, "label"]
        data[t] = (pa.loc[ids], pb.loc[ids], y)

    pa, pb, y = data["holdout2024"]
    grid = np.round(np.arange(0.4, 2.51, 0.1), 2)
    best = (-1, None)
    for a in np.round(np.arange(0, 1.01, 0.1), 2):
        for wf, wo in itertools.product(grid, grid):  # cocoa weight fixed at 1
            f = f1_score(y, decide(pa, pb, a, (1, wf, wo)), labels=CLASSES, average="macro")
            if f > best[0]:
                best = (f, (a, (1, wf, wo)))
    f, (a, w) = best
    print(f"chosen on holdout2024: a={a} (weight on {a_.a}), class weights cocoa/forest/other={w}, macro F1 {f:.4f}")

    name = f"{a_.a}+{a_.b}"
    for t, (pa, pb, y) in data.items():
        out = pd.DataFrame({"cand_id": pa.index, "pred": decide(pa, pb, a, w)})
        out.to_csv(PRED / f"{t}-{name}.csv", index=False)
        print(f"{t}: n={len(out)}, acc {(out.pred.values == y.values).mean():.4f} -> {PRED / f'{t}-{name}.csv'}")


if __name__ == "__main__":
    main()
