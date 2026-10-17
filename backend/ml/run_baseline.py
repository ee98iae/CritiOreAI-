"""Train the baseline prospectivity model and run the blind back-test.

    cd backend
    pip install -r requirements-ml.txt
    python -m ml.run_baseline --layers /path/to/layers/kharkhiraa --out out/kharkhiraa

Writes, per commodity group: a GeoTIFF score map from a model trained on all sites,
and report.json with the back-test numbers. Prints a summary table.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app.data import load_occurrences
from app.regions import PILOT_REGION

from .backtest import (
    BACKGROUND_CELLS,
    EXCLUDE_KM,
    POSITIVE_KM,
    TOP_SHARE,
    Site,
    backtest,
    feature_importance,
    hit_rate,
    make_model,
    predict_map,
    training_set,
)
from .features import build_stack

# Cu alone, and the porphyry / skarn family the pilot targets (Cu, Mo, Au, W occur together).
GROUPS = {"Cu": {"Cu"}, "Cu-Mo-Au-W": {"Cu", "Mo", "Au", "W"}}
MODEL_VERSION = "gbt-baseline-v0"
STRUCTURE_MODEL_VERSION = "gbt-structure-v1"


def sites_for(commodities: set[str]) -> list[Site]:
    s, w, n, e = PILOT_REGION.bbox
    return [
        Site(o.id, o.name, o.lat, o.lon, o.commodities)
        for o in load_occurrences()
        if s <= o.lat <= n and w <= o.lon <= e and commodities & set(o.commodities)
    ]


def write_geotiff(path: Path, score: np.ndarray, stack) -> None:
    import rasterio
    from rasterio.transform import from_origin

    g = stack.grid
    with rasterio.open(
        path, "w", driver="GTiff", height=g.shape[0], width=g.shape[1], count=1,
        dtype="float32", crs="EPSG:4326", transform=from_origin(g.west, g.north, g.res, g.res),
        nodata=np.nan, compress="deflate",
    ) as dst:
        dst.write(score.astype("float32"), 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layers", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--res", type=float, default=0.005, help="model cell size in degrees")
    ap.add_argument("--seeds", type=int, default=3, help="repeat with this many background samples")
    ap.add_argument("--structure", action="store_true", help="add DEM lineament and rock-type layers")
    args = ap.parse_args()

    stack = build_stack(args.layers, args.res, structure=args.structure)
    print(f"grid {stack.grid.shape}, {len(stack.names)} features, {stack.valid.mean():.0%} valid")
    args.out.mkdir(parents=True, exist_ok=True)
    report = {
        "model_version": STRUCTURE_MODEL_VERSION if args.structure else MODEL_VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "region": PILOT_REGION.id,
        "cell_deg": args.res,
        "positive_km": POSITIVE_KM,
        "exclude_km": EXCLUDE_KM,
        "background_cells": BACKGROUND_CELLS,
        "top_share": TOP_SHARE,
        "features": stack.names,
        "groups": {},
    }

    for label, comms in GROUPS.items():
        sites = sites_for(comms)
        runs = [backtest(stack, sites, seed) for seed in range(args.seeds)]
        per_site = []
        for i, s in enumerate(sites):
            m = [r[i].model_rank for r in runs]
            per_site.append({
                "id": s.id, "name": s.name, "lat": s.lat, "lon": s.lon, "commodities": list(s.commodities),
                "model_rank": float(np.mean(m)), "model_rank_runs": m,
                "proximity_rank": runs[0][i].proximity_rank,
            })
        model_hits = [hit_rate([r.model_rank for r in run]) for run in runs]
        prox_hit = hit_rate([r.proximity_rank for r in runs[0]])

        X, y = training_set(stack, sites, np.zeros(stack.grid.shape, bool), np.random.default_rng(0))
        model = make_model(0).fit(X, y)
        write_geotiff(args.out / f"prospectivity_{label}.tif", predict_map(model, stack), stack)

        report["groups"][label] = {
            "sites": len(sites),
            "model_hit_rate": float(np.mean(model_hits)),
            "model_hit_rate_runs": model_hits,
            "model_median_rank": float(np.median([p["model_rank"] for p in per_site])),
            "proximity_hit_rate": prox_hit,
            "proximity_median_rank": float(np.median([p["proximity_rank"] for p in per_site])),
            "random_hit_rate": TOP_SHARE,
            "top_features": feature_importance(model, X, y, stack.names),
            "per_site": per_site,
            "map": f"prospectivity_{label}.tif",
        }

    (args.out / "report.json").write_text(json.dumps(report, indent=2))
    print(f"\nShare of held-out sites inside the top {TOP_SHARE:.0%} of the area (gate: 70%)")
    print(f"{'group':<12}{'sites':>6}{'model':>9}{'proximity':>11}{'random':>8}")
    for label, g in report["groups"].items():
        print(f"{label:<12}{g['sites']:>6}{g['model_hit_rate']:>9.0%}{g['proximity_hit_rate']:>11.0%}{TOP_SHARE:>8.0%}")
        for p in g["per_site"]:
            print(f"    {p['name']:<16}{'/'.join(p['commodities']):<10} model top {p['model_rank']:.0%}"
                  f"   proximity top {p['proximity_rank']:.0%}")
        print("    leans on:", ", ".join(n for n, _ in g["top_features"][:6]))


if __name__ == "__main__":
    main()
