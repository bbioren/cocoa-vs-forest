# Nov 19 — v1 results

fetch fix: v1's output band is `label_v1` (named after the dataset field), so studio_predict.py fetch now auto-detects
the field name. Same 104 test2020 points return no data as for the probe (n=1660).

## v1 on test2020 (n=1660) vs v0 on the same points
| | v0 | v1 |
|---|---|---|
| 3-class acc | 0.817 | 0.762 |
| forest recall | 0.843 | 0.864 |
| forest precision | 0.706 | 0.610 |
| cocoa_2020 | 0.872 | 0.696 |
| forest_degraded | 0.460 | 0.516 |
| converted (n=37) | 0.459 | 0.595 |
| reserve | 1.0 | 1.0 |
| other_2020 | 0.680 | 0.739 |
Rebalancing overshot: degraded/converted up a little, but 215 of 713 cocoa farms now called forest.
Next (free): prior-shift / ensemble of v0+v1 probabilities, tuned on holdout2024, applied to test2020.

## v1 on holdout2024 (n=2217) — worse than v0 here too
acc 0.852 (v0 0.891); forest recall 0.798 / precision 0.768 (v0 0.835 / 0.81).
Sources v1 (v0): farm 0.807 (0.888), galamsey 0.972 (0.938), oil palm 0.938 (0.928), rubber 0.772 (0.900),
degraded 0.435 (0.543), reserve 1.0 (0.998).
So rebalancing did NOT help degraded forest even in-period. Confound: v1 also clipped cocoa farms to 30 m squares
(less cocoa context) and used an 85/15 Studio split, so it is not a clean balance-only ablation.

## v0+v1 blend (scripts/combine.py), tuned on holdout2024 only, applied unchanged to test2020
chosen: 0.6*v0 + 0.4*v1, class weights cocoa 1 / forest 0.7 / other 1.0
- holdout2024: acc 0.915, forest recall 0.833, precision 0.883, degraded 0.538  (in-sample: tuned here, optimistic)
- test2020 (n=1660): acc 0.830 (v0 0.817), forest-binary acc 0.842 (0.831), recall 0.837 (0.843), precision 0.728 (0.706)
  slices: cocoa 0.868, reserve 1.0, other 0.749, degraded 0.452, converted 0.405 (n=37)
Small, honest gain on 2020; degraded forest stays ~45-54% in every model (v0, v1, blend, probe, Tiny all <= 0.55).

## Decision
Degraded forest is the ceiling and no class-balance change moves it; likely the CERSGIS "open/degraded forest"
class genuinely overlaps shaded cocoa / fallow at 10 m. Not spending more compute on balance variants.
Best model for the paper: v0+v1 blend (or v0 alone if we want a single model). ~160 units left in reserve.
