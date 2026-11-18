# Project plan

_Last updated 2026-11-17 (switched training to OlmoEarth Studio; no Klone needed)._ Paper and poster due the week of Dec 7._

## Goal

Fine-tune OlmoEarth to segment **cocoa / forest / other** at 10 m in Ghana's cocoa belt. Then answer the EUDR question for any plot: **was it cocoa or forest on 31 Dec 2020?**

The headline claim to test is whether OlmoEarth beats the EU's GFC2020 map at separating shaded cocoa from forest in Ghana. No existing map has a published Ghana accuracy.

## Approach

1. **Train on 2024–25.** Labels were collected in 2024–25, so pair them with 2024–25 Sentinel-1/2 imagery. No 2020 filtering is needed for training.
2. **Infer on 2020.** Run the trained model on 2020 imagery.
3. **Evaluate on 2020.** Score it on a small hand-labelled 2020 test set, alongside existing maps.

## Status

- [x] Repo, label pipeline, exploratory figures (`scripts/`, `figures/`)
- [x] Cocoa labels: 21,027 CERSGIS farm polygons
- [x] Forest labels: 6,255 automatic reserve-interior points + 1,606 CERSGIS degraded-forest points
- [x] Other labels: 18,122 CERSGIS points (oil palm, rubber, mining)
- [ ] Border hand labels: 0 of 600 done
- [x] Studio project `cocoa-vs-forest` created; 39,134 training labels uploaded (Studio counts 39,066)
- [x] **v0 training started 11/17**: "cocoa-vs-forest 160m Jan-Dec". Settings:
  - OlmoEarth Base, Sentinel-2 only, per-pixel segmentation
  - 160 m window, patch size 2, Jan–Dec annual monthly stack
  - Studio spatial split 85/15; lr 1e-4, encoder unfrozen
  - Cost ~31 of 500 compute units/month
- [ ] Evaluation on our held-out blocks: not started

## Timeline

### Week 1: Nov 17–23. First model trained

| # | Task | Owner | Done when |
|---|---|---|---|
| 1 | ~~Compute~~ **Use OlmoEarth Studio** (access confirmed 11/17: builder role, UW CSE org). Sign in, create project `cocoa-vs-forest`, check split control / 2020 inference / limits | Ben | Project exists |
| 2 | Email OlmoEarth team the open questions below | Ben | Sent |
| 3 | ~~rslearn builder~~ **Studio export** `scripts/export_studio.py` ✅ → upload `data/studio/train_upload.geojson` (39k labels; 15% of 10 km blocks held out in `test_holdout.geojson`) | Ben (+Claude) | Uploaded to Studio |
| 4 | **Frozen-embedding baseline**: OlmoEarth features + logistic regression / kNN | Ben (+Claude) | Per-class P/R/F1 on val |
| 5 | **Label border points**, 300 each (`labels/README.md`) | Ben, Kyvalya | 600 labelled, committed |
| 6 | Draft paper skeleton: intro, related work, data sections (reuse the proposal) | Kyvalya | Overleaf draft exists |

### Week 2: Nov 24–30. Fine-tune and answer the 2020 question

| # | Task | Owner | Done when |
|---|---|---|---|
| 7 | Fine-tune in Studio: v0 (no border labels), then v1 (with border labels). Score predictions on our held-out blocks | Ben (+Claude) | Studio metrics + our held-out metrics |
| 8 | Ablations: S2 only vs S2+S1; patch size 1 vs 2 vs 4 | Ben (+Claude) | Results table |
| 9 | **Build 2020 test set**: ~300 points labelled on 2020 imagery | Kyvalya (sampling script: Ben) | 300 labelled, 60 double-labelled |
| 10 | 2020 inference over the cocoa belt (or at test points if compute is tight) | Ben (+Claude) | 2020 prediction map |
| 11 | Score on 2020 test set: ours vs GFC2020 V4 vs Kalischek vs FDaP 2020 | Ben, Kyvalya | Comparison table |

### Week 3: Dec 1–7. Write up

| # | Task | Owner |
|---|---|---|
| 12 | Results figures: confusion matrices, map panels, shaded vs sunny cocoa | Ben |
| 13 | Paper: methods + results + discussion (incl. GFC2020 circularity, limitations) | Both |
| 14 | Poster | Kyvalya |
| 15 | OlmoEarth team review, final edits, submit | Both |

**Cut list if behind**, in this order:
1. S1 ablation
2. Patch-size ablation
3. Whisp comparison
4. Full-belt 2020 map (score at test points only)

**Never cut:** the 2020 test set and the GFC2020 comparison.

## Technical spec

### Training set (`build_windows.py`)

**Classes:**

| Value | Class |
|---|---|
| 0 | ignore (unlabelled) |
| 1 | cocoa |
| 2 | forest |
| 3 | other |

Unlabelled pixels are **ignored**, never treated as negatives.

**Label rasterisation:**
- **Cocoa farms:** buffer −10 m (one pixel, to avoid mixed edge pixels). Drop farms under 2 px.
- **Points:** label a 3×3 px square, but only the centre pixel for points within 20 m of a different label.

**Windows:**
- 64×64 px (640 m) tiles in UTM 30N.
- One window per label cluster, merging nearby labels.
- Cap windows per class to keep balance.

**Imagery** (training):

| Source | Detail |
|---|---|
| Sentinel-2 L2A | 12 monthly mosaics, **Apr 2024 – Mar 2025** |
| Sentinel-1 RTC | Same months, ablation only |

Pulled from Planetary Computer through rslearn.

**Split:**
- 10 km grid blocks, assigned 70 / 15 / 15 train / val / test by block.
- Stratified by region.
- Border hand labels split by the same blocks.

### Model

- **Starting point:** OlmoEarth Base (`OLMOEARTH_V1_*`; check v1.2 with Ai2). Use the `olmoearth_projects` polygon-segmentation tutorial pipeline with `togo_cropland` / `nandi` settings.
- **Decoder and optimiser:** UNet decoder, patch size 2 to start, `LayerDecayAdamW` lr 1e-4.

### Metrics

- **Classes:** per-class precision / recall / F1 plus a confusion matrix. **Cocoa F1** is the headline.
- **Strata:** every cocoa metric also broken down by the CERSGIS shade class (none / 1–5 / 6+ shade trees) and canopy (open / gaps / closed).
- **Reference numbers from prior work:** cocoa F1 ~0.83 (Kalischek map) and ~0.86 (best embeddings), both in Côte d'Ivoire.

### 2020 test set

- **Sampling:** stratified on Kalischek cocoa × GFC2020 forest (4 strata), plus extra points with high tree cover near cocoa (the shaded-cocoa confusions).
- **Labelling:** from Google Earth Pro historical imagery, as close to Dec 2020 as possible. Same classes and rules as `labels/README.md`.
- **Agreement:** 20% labelled by both of you; report Cohen's kappa.
- **Independence:** never used in training. GFC2020 and FDaP are circular with CERSGIS, so they get scored **only** on this set.

## Risks

| Risk | Mitigation |
|---|---|
| Studio can't control split / limits / 2020 inference | We hold out our own test blocks and score exported predictions ourselves; fall back to rslearn on Klone if Studio blocks us |
| Imagery download slow or cloudy (Ghana is very cloudy) | Monthly mosaics; S1 as fallback; start materialising early (task 3) |
| Model learns "reserve = forest" shortcut | Border hand labels; report border-point accuracy separately |
| Hand labelling slips | v0 trains without border labels. The 2020 test set is protected (see cut list). |
| Shaded cocoa can't be told from forest even by eye | Allow `unsure`; report labeller agreement; discuss as a limitation |

## Open questions for the OlmoEarth team

1. Which model version and size do you recommend for fine-tuning: v1 Base or v1.2?
2. Is `togo_cropland` / the polygon-segmentation tutorial the right template? Are there any config gotchas with the current rslearn?
3. Do the v1.3 embeddings on Source Cooperative cover Ghana for 2020 and 2024?
4. Can you provide compute, or OlmoEarth Studio access?
5. Would you review the paper draft around Dec 3?
