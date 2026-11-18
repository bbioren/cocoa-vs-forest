# Overnight log, 2026-11-18

## 2020 test set (scripts/make_test2020.py -> data/test2020/)
Built from records instead of hand labels (hand-labelling shaded cocoa vs forest from Esri chips was unreliable).

| slice | label | n | source |
|---|---|---|---|
| cocoa_2020 | cocoa | 800 | CERSGIS farms, last major replanting <= 2019, no Hansen loss 2020-24, held-out blocks |
| forest_reserve | forest | 400 | reserve-interior points, held-out blocks |
| forest_degraded | forest | 127 | CERSGIS open/degraded forest, no Hansen loss 2001-24, held-out blocks |
| other_2020 | other | 400 | CERSGIS oil palm/rubber, no Hansen loss 2020-24, held-out blocks |
| converted | forest | 37 | farms replanted 2021-24 with Hansen loss 2021-24 at the point (all blocks) |

JRC GFC2020 forest share by slice: cocoa 0.00, forest_reserve 1.00, forest_degraded 0.01 (!), other 0.00, converted 0.00.
GFC2020 calls 99% of CERSGIS "open/degraded forest" points non-forest. Either those points miss the FAO
thresholds or GFC2020 under-maps degraded forest in the cocoa belt. Worth a paragraph.

### Converted slice: visual check (data/chips/conv_sheet_*.jpg, before vs after)
Esri Wayback has almost no 2019-2021 imagery here: "before" chips are mostly 2015-2018, and many points have
the same capture on both sides. Where the two dates differ, most look like farm mosaic in both, not
closed forest -> farm. So Hansen loss + recent replanting mostly reflects replanting of old cocoa, not
deforestation. **Treat `converted` as unreliable; report it only as a small, caveated slice, or drop it.**

## Studio runs
- v0 `bc5c9bbb-a9f6-473c-95cd-74ad9cef82ff` (Base, fine-tuned, S2, 160 m, Jan-Dec, spatial 85/15): started 06:25 UTC.
  48% at ~08:16, 56% at 11:07 UTC (~3%/h after a faster start). Progress % is only in the UI tooltip, not the API.
- Frozen-encoder probe `80d08a99-2e26-4367-9b7f-718492b04f41` (same config, freeze_encoder=True, default LR):
  queued 11:20 UTC. Studio estimated ~31 compute units (same as v0; the estimate may ignore freezing).

## Prediction plan once a model finishes (scripts/studio_predict.py)
- held-out 2024-25: data/test2024/holdout2024.csv (2,223 pts, <=400 per source, per-point year windows)
- 2020: data/test2020/test2020.csv (1,764 pts), window 2020-01-01..2020-12-31

## Baseline: JRC GFC2020 V4 on the 2020 test set (scripts/score.py, results/scores.csv)
forest vs not-forest acc 0.907, forest recall 0.711, forest precision 0.998.
Per slice: cocoa 0.999, other 1.000, forest_reserve 1.000, forest_degraded 0.008, converted 0.000.
Caveat: the cocoa score is inflated by circularity (GFC2020 masks cocoa with the FDaP model trained partly on
CERSGIS), and the reserve-forest points were selected with GFC2020 == 1. The informative number is
forest_degraded: GFC2020 misses almost all field-surveyed open/degraded forest.

## v0 finished 14:49 UTC (~8.4 h). Studio validation metrics (spatial 85/15 val split, pixel level)
Overall acc 98.7%, mean F1 96.1%, 148,651 val pixels.
| class | precision | recall | F1 | GT pixels |
|---|---|---|---|---|
| cocoa | 99.7 | 99.8 | 99.8 | 114,777 |
| other | 95.4 | 98.1 | 96.7 | 23,332 |
| forest | 95.5 | 88.5 | 91.9 | 10,542 |
Confusion (rows true; cols cocoa/other/forest): cocoa 114563/84/130; other 127/22894/311; forest 193/1019/9330.
Main error: forest -> other (1,019 px, ~10% of forest). Cocoa vs forest confusion is small (130 + 193).
Pixel-weighted (cocoa polygons dominate), and Studio's val split is not our block hold-out, so expect lower on ours.
wandb: https://wandb.ai/eai-ai2/olmoearth_run_develop/runs/65ynp9fg (Ai2-internal; may not be viewable)

## Predictions via API
- Trial: 20 cocoa_2020 points on 2020 imagery, prediction 6b347dcd (result 2e6edfb0), ~64 min. 15/20 cocoa, 5 forest.
  pixel-value returns class + top-3 probs (raw/254). Results are web-optimised GeoTIFFs grouped by region.
- Compute meter: 80/500 after v0 (31) + probe (31) + trial -> trial ~18 units?? Cost may scale with the
  raster extent Studio builds around grouped windows, not with point count. Measuring with a 100-point
  stratified batch (f310998d, data/test2020/batch100.csv) before running the full sets.

## 100-point 2020 batch (v0, prediction f310998d) — 17:12 UTC
Stratified: cocoa 30, reserve 20, degraded 20, other 20, converted 10. Cost: meter 80 -> 90, so ~0.1 unit/point.

| slice | v0 | GFC2020 |
|---|---|---|
| cocoa_2020 (30) | 0.867 | 1.0* |
| forest_reserve (20) | 1.0 | 1.0 |
| forest_degraded (20) | 0.25 | 0.0 |
| other_2020 (20) | 0.80 | 1.0 (as not-forest) |
| converted (10) | 0.50 | 0.0 |
| forest-binary acc / recall / precision | 0.73 / 0.60 / 0.81 | 0.70 / 0.40 / 1.0 |

v0 3-class acc 0.72, macro F1 0.74. Main error: degraded forest -> cocoa (12/20). Model recovers some of the forest GFC2020 misses
(degraded + converted) at the cost of some cocoa -> forest false alarms (4/30). *GFC cocoa score is circular (FDaP mask).

Submitted full runs: test2020 (1,764 pts, 66e26aea) and holdout2024 (2,223 pts, per-row year windows, 32864543). ~40 units expected.
