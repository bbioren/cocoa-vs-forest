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
