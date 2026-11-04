# cocoa-vs-forest

Distinguishing cocoa plantations from forest in Ghana at the EUDR cutoff date (31 Dec 2020) by fine-tuning [OlmoEarth](https://github.com/allenai/olmoearth_pretrain) on Sentinel-1/Sentinel-2 time series.

CSE 580: Computing for Social Good, University of Washington, Autumn 2026. Kyvalya Reddy and Ben Bioren.

## Motivation

The EU Deforestation Regulation (EUDR) bars imports of commodities such as cocoa grown on land deforested after 2020. Existing 2020 forest maps (e.g. JRC GFC2020) often misclassify shaded cocoa as forest in West Africa. This project tests whether OlmoEarth's learned representations can separate the two and serve as a scalable screening tool for EUDR compliance.

## Plan

1. **Labels.** Build cocoa / forest / other labels for Ghana from existing maps plus a hand-labeled, spatially held-out test set.
2. **Baseline.** Train a linear probe / kNN on frozen OlmoEarth embeddings of 2020 imagery.
3. **Fine-tune.** Fine-tune OlmoEarth with a segmentation head via [rslearn](https://github.com/allenai/rslearn).
4. **Evaluate.** Compare against GFC2020 and existing cocoa maps, with emphasis on shaded cocoa.

## Layout

```
configs/    rslearn dataset and model configs
scripts/    label preparation, training, evaluation
notebooks/  exploration and figures
data/       local data (git-ignored)
```
