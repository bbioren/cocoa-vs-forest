# Nov 19 — v1 results

fetch fix: v1's output band is `label_v1` (named after the dataset field), so studio_predict.py fetch now auto-detects
the field name. Same 104 test2020 points return no data as for the probe (n=1660).

## v1 on test2020 (n=1660) vs v0 on the same points
| | v0 | v1 |
|---|---|---|
| 3-class acc | ~0.83 | 0.762 |
| forest recall | 0.843 | 0.864 |
| forest precision | 0.706 | 0.610 |
| cocoa_2020 | 0.872 | 0.696 |
| forest_degraded | 0.460 | 0.516 |
| converted (n=37) | 0.459 | 0.595 |
| reserve | 1.0 | 1.0 |
| other_2020 | ? | 0.739 |
Rebalancing overshot: degraded/converted up a little, but 215 of 713 cocoa farms now called forest.
Next (free): prior-shift / ensemble of v0+v1 probabilities, tuned on holdout2024, applied to test2020.
