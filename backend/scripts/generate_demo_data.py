"""Generate the synthetic demo occurrence dataset for the pilot region.

These points are NOT real mineral occurrences. They exist so the map, API and
scoring endpoint have something to work with until the Soviet archive digitiser
and public datasets (see import_mrds.py) are loaded.

Usage (from backend/): python -m scripts.generate_demo_data > data/occurrences_demo.geojson
"""

import json
import random

from app.regions import PILOT_REGION

SEED = 20261016

# Hypothetical mineralised belts (centre lat, centre lon, main commodity, extra commodities).
BELTS = [
    (49.55, 91.45, "Cu", ["Mo", "Au"]),
    (49.20, 91.95, "Ni", ["Cu", "Co"]),
    (49.95, 91.10, "Cu", ["Co"]),
    (49.05, 91.30, "Au", ["Cu"]),
    (50.15, 92.25, "Ni", ["Co"]),
]

TYPES = [("deposit", 0.1), ("occurrence", 0.4), ("showing", 0.5)]
SOURCES = ["Soviet 1:200,000 sheet (placeholder)", "Soviet 1:50,000 sheet (placeholder)"]


def pick_type(rng: random.Random) -> str:
    r = rng.random()
    acc = 0.0
    for name, p in TYPES:
        acc += p
        if r <= acc:
            return name
    return TYPES[-1][0]


def main() -> None:
    rng = random.Random(SEED)
    south, west, north, east = PILOT_REGION.bbox
    features = []
    n = 0
    for lat0, lon0, main, extras in BELTS:
        for _ in range(rng.randint(8, 14)):
            n += 1
            commodities = [main] + [c for c in extras if rng.random() < 0.5]
            features.append(_feature(n, lat0 + rng.gauss(0, 0.08), lon0 + rng.gauss(0, 0.12),
                                     commodities, pick_type(rng), rng))
    # Scattered background showings.
    for _ in range(15):
        n += 1
        commodity = rng.choice(["Cu", "Ni", "Co", "Au", "Mo"])
        features.append(_feature(n, rng.uniform(south, north), rng.uniform(west, east),
                                 [commodity], "showing", rng))

    fc = {
        "type": "FeatureCollection",
        "name": "critiore-demo-occurrences",
        "note": "SYNTHETIC DEMO DATA - not real mineral occurrences.",
        "features": features,
    }
    print(json.dumps(fc, indent=1))


def _feature(n, lat, lon, commodities, occ_type, rng):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
        "properties": {
            "id": f"DEMO-{n:04d}",
            "name": f"Demo site {n}",
            "commodities": commodities,
            "type": occ_type,
            "source": rng.choice(SOURCES),
            "synthetic": True,
        },
    }


if __name__ == "__main__":
    main()
