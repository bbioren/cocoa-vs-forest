# Hand labels: cocoa–forest border

`border_candidates.*` holds 600 points 30 m–2 km outside CERSGIS cocoa farms. 400 have high tree cover (Hansen ≥60% in 2000, no loss through 2024), so each is either real forest or shaded cocoa. That confusion is the core of the project. The other 200 are random. The strata are shuffled and hidden from labellers on purpose.

Each point has a `labeler` (300 each for Ben and Kyvalya). Overlap some later to measure agreement.

## What to label

Label what is on the ground **in 2024–25**, the period the training imagery covers. Use the historical imagery closest to that, not the newest.

| `label` | Use when |
|---|---|
| `forest` | Natural or degraded forest: irregular crowns of mixed sizes, no planting rows or clearings. Under the EUDR's FAO-based definition, degraded or open forest still counts as forest. |
| `cocoa` | Cocoa: low uniform understory canopy, often with scattered tall shade trees, small clearings or paths, next to farms. Shaded cocoa can look like thin forest; look for the low, even layer under the shade trees. |
| `other` | Anything else: oil palm (star-shaped crowns in rows), rubber (regular rows), food crops, fallow/bush, bare ground, mining, settlement, water. |
| `unsure` | Can't tell. Use this freely. A wrong label does more harm than a missing one. |

Also fill in:
- `confidence`: `high` / `med` / `low`
- `imagery_date`: the date of the image you judged from
- `notes`: anything odd, e.g. "edge of farm", "cloud", "young cocoa"

The point marks a single 10 m pixel. Judge the ~30 m around it. If it falls on a boundary, label the majority and note it.

## Tools (pick one)

**Google Earth Pro (easiest).** Open `border_candidates.kml`. Click each point and use the clock icon (historical imagery) to pick a 2024–25 image. Record answers in `border_candidates.csv`, either in a spreadsheet or by editing the CSV directly.

**QGIS.**
1. Install: `brew install --cask qgis`.
2. Open `border_candidates.gpkg` (layer `candidates`) and add an imagery basemap: XYZ Tiles → Esri World Imagery or Google Satellite.
3. Toggle editing and fill in the attribute table.
4. Optional: draw whole forest or cocoa areas in the `hand_polygons` layer. Each polygon gives many training pixels.

The CSV's `google_maps` column also opens each point in Google Maps satellite view for a quick look. Google Maps doesn't show the imagery date, so prefer Earth Pro when unsure.

## After labelling

Commit the edited CSV or GeoPackage. The training-set builder will merge:
- labels with `confidence` of `high` or `med`
- labels other than `unsure`

Points where both of you labelled and disagree are dropped.
