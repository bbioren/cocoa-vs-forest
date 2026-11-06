"""Exploratory figures for the cleaned CERSGIS labels. Writes PNGs to figures/.

Run after clean_cersgis.py:  uv run python scripts/plot_cersgis.py
"""

from __future__ import annotations

from pathlib import Path

import contextily as cx
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import requests

ROOT = Path(__file__).resolve().parents[1]
GPKG = ROOT / "data/processed/cersgis_clean.gpkg"
FIG = ROOT / "figures"
BOUNDS = ROOT / "data/raw/boundaries/gha_adm1.geojson"
# geoBoundaries (CC BY 4.0), Ghana regions
BOUNDS_URL = ("https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/GHA/ADM1/"
              "geoBoundaries-GHA-ADM1_simplified.geojson")
UTM = "EPSG:32630"

COLORS = {"cocoa": "#8c510a", "forest": "#1b7837", "Oil Palm": "#e08214",
          "Rubber": "#8073ac", "Galamsey": "#b2182b", "Open/Degraded Forest": "#1b7837"}


def ghana() -> gpd.GeoDataFrame:
    if not BOUNDS.exists():
        BOUNDS.parent.mkdir(parents=True, exist_ok=True)
        BOUNDS.write_bytes(requests.get(BOUNDS_URL, timeout=60).content)
    return gpd.read_file(BOUNDS).to_crs(UTM)


def overview(farms, other, adm):
    fig, ax = plt.subplots(figsize=(8, 9))
    adm.boundary.plot(ax=ax, color="0.6", lw=0.6)
    for cls, g in other.groupby("cersgis_class"):
        g.plot(ax=ax, markersize=1, color=COLORS[cls], label=f"{cls} ({len(g):,})", alpha=0.6)
    farms.centroid.plot(ax=ax, markersize=1, color=COLORS["cocoa"], label=f"Cocoa farm ({len(farms):,})", alpha=0.6)
    ax.set_title("CERSGIS reference labels, 2024–25")
    ax.legend(markerscale=8, loc="upper right", fontsize=8)
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(FIG / "01_overview_map.png", dpi=150)
    # zoom on the cocoa belt
    x0, y0, x1, y1 = farms.total_bounds
    ax.set_xlim(x0 - 2e4, x1 + 2e4); ax.set_ylim(y0 - 2e4, y1 + 2e4)
    fig.savefig(FIG / "02_overview_map_cocoa_belt.png", dpi=150)
    plt.close(fig)


def farm_sizes(farms, shadeless):
    fig, ax = plt.subplots(figsize=(8, 4))
    bins = np.logspace(-1, 3.5, 60)
    ax.hist(farms["area_px"], bins=bins, alpha=0.7, label="cocoa farm", color=COLORS["cocoa"])
    ax.hist(shadeless["area_px"], bins=bins, alpha=0.6, label="shadeless sub-polygon", color="#dfc27d")
    for v, t in [(2, "2 px"), (9, "3×3 px"), (16, "4×4 px")]:
        ax.axvline(v, color="k", ls="--", lw=0.8); ax.text(v * 1.05, ax.get_ylim()[1] * 0.9, t, fontsize=8)
    ax.set_xscale("log"); ax.set_xlabel("area in 10 m Sentinel-2 pixels (log)"); ax.set_ylabel("count")
    med = farms["area_px"].median()
    ax.set_title(f"Polygon size (median farm = {med:.0f} px ≈ {med / 100:.2f} ha)")
    ax.legend(); fig.tight_layout(); fig.savefig(FIG / "03_polygon_sizes.png", dpi=150); plt.close(fig)


def attributes(farms, other):
    fig, axs = plt.subplots(2, 3, figsize=(14, 7))
    order = {"canopy": ["open", "gaps", "closed", "unknown"],
             "shade_class": ["none", "low(1-5)", "high(6+)"]}
    panels = [("canopy", "Cocoa canopy (field estimate)"),
              ("shade_class", "Shade trees per farm"),
              ("region", "Cocoa farms by region")]
    for ax, (col, title) in zip(axs[0], panels):
        vc = farms[col].value_counts()
        if col in order: vc = vc.reindex(order[col]).fillna(0)
        vc.plot.bar(ax=ax, color=COLORS["cocoa"]); ax.set_title(title); ax.set_xlabel("")
        ax.tick_params(axis="x", rotation=30)
    farms["collected"].dt.strftime("%Y-%m").value_counts().sort_index().plot.bar(
        ax=axs[1, 0], color=COLORS["cocoa"]); axs[1, 0].set_title("Cocoa farm collection month")
    vc = other["cersgis_class"].value_counts()
    vc.plot.bar(ax=axs[1, 1], color=[COLORS[c] for c in vc.index]); axs[1, 1].set_title("Non-cocoa points (CERSGIS class)")
    axs[1, 1].tick_params(axis="x", rotation=30)
    proj = {"cocoa (polygons)": len(farms), **other["label"].value_counts().rename(lambda s: f"{s} (points)").to_dict()}
    axs[1, 2].bar(proj.keys(), proj.values(), color=[COLORS["cocoa"], "0.5", COLORS["forest"]][: len(proj)])
    axs[1, 2].set_title("Project classes (forest still needs more labels)")
    axs[1, 2].tick_params(axis="x", rotation=30)
    for ax in axs.flat: ax.set_xlabel("")
    fig.tight_layout(); fig.savefig(FIG / "04_attributes.png", dpi=150); plt.close(fig)


def zooms(farms, shadeless, other, n=4, seed=0):
    """Satellite basemap close-ups: farms (brown), shadeless parts (yellow), points."""
    rng = np.random.default_rng(seed)
    # pick farms in dense clusters so each tile shows several labels
    picks = farms[(farms["area_px"] > 20)].sample(n, random_state=seed)
    fig, axs = plt.subplots(1, n, figsize=(5 * n, 5))
    for ax, (_, f) in zip(axs, picks.iterrows()):
        c = f.geometry.centroid; r = 600
        box = (c.x - r, c.y - r, c.x + r, c.y + r)
        sub = farms.cx[box[0]:box[2], box[1]:box[3]]
        sub.to_crs(3857).boundary.plot(ax=ax, color="#ff9900", lw=1.2)
        sh = shadeless.cx[box[0]:box[2], box[1]:box[3]]
        if len(sh): sh.to_crs(3857).boundary.plot(ax=ax, color="yellow", lw=0.8, ls="--")
        pts = other.cx[box[0]:box[2], box[1]:box[3]]
        if len(pts): pts.to_crs(3857).plot(ax=ax, color="cyan", markersize=20)
        b = gpd.GeoSeries.from_xy([box[0], box[2]], [box[1], box[3]], crs=UTM).to_crs(3857)
        ax.set_xlim(b.x.min(), b.x.max()); ax.set_ylim(b.y.min(), b.y.max())
        try:
            cx.add_basemap(ax, source=cx.providers.Esri.WorldImagery, attribution_size=5)
        except Exception as e:  # offline: still save the outlines
            print("basemap failed:", e)
        ax.set_title(f"{f.district} · canopy={f.canopy} · shade trees={f.n_shade_trees}", fontsize=9)
        ax.set_axis_off()
    fig.suptitle("Cocoa farm polygons (orange) and shadeless sub-polygons (yellow) on current Esri imagery — 1.2 km tiles")
    fig.tight_layout(); fig.savefig(FIG / "05_example_farms.png", dpi=130); plt.close(fig)


def main():
    FIG.mkdir(exist_ok=True)
    farms = gpd.read_file(GPKG, layer="cocoa_farms")
    shadeless = gpd.read_file(GPKG, layer="cocoa_shadeless")
    other = gpd.read_file(GPKG, layer="other_points")
    adm = ghana()
    overview(farms, other, adm)
    farm_sizes(farms, shadeless)
    attributes(farms, other)
    zooms(farms, shadeless, other)
    print("wrote", sorted(p.name for p in FIG.glob("*.png")))


if __name__ == "__main__":
    main()
