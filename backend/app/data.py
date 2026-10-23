"""Loads mineral occurrences from GeoJSON into memory.

The MVP keeps everything in one GeoJSON file. When the archive digitiser lands,
this module is the seam to swap for PostGIS.
"""

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_PATH = DATA_DIR / "occurrences_neasia_mongolia.geojson"
DEMO_PATH = DATA_DIR / "occurrences_demo.geojson"
LISTED_MINERS_PATH = DATA_DIR / "listed_miners_mongolia.geojson"


@dataclass(frozen=True)
class Occurrence:
    id: str
    name: str
    lat: float
    lon: float
    commodities: tuple[str, ...]
    type: str
    source: str
    synthetic: bool

    def to_feature(self) -> dict:
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [self.lon, self.lat]},
            "properties": {
                "id": self.id,
                "name": self.name,
                "commodities": list(self.commodities),
                "type": self.type,
                "source": self.source,
                "synthetic": self.synthetic,
            },
        }


def _parse(feature: dict) -> Occurrence:
    lon, lat = feature["geometry"]["coordinates"][:2]
    p = feature["properties"]
    return Occurrence(
        id=str(p["id"]),
        name=p.get("name") or str(p["id"]),
        lat=float(lat),
        lon=float(lon),
        commodities=tuple(c.strip() for c in p.get("commodities", []) if c.strip()),
        type=p.get("type", "occurrence"),
        source=p.get("source", "unknown"),
        synthetic=bool(p.get("synthetic", False)),
    )


@lru_cache(maxsize=1)
def load_occurrences() -> tuple[Occurrence, ...]:
    path = Path(os.environ.get("CRITIORE_OCCURRENCES", DEFAULT_PATH))
    with path.open(encoding="utf-8") as f:
        fc = json.load(f)
    return tuple(_parse(feat) for feat in fc["features"] if feat.get("geometry"))


@lru_cache(maxsize=1)
def load_listed_miners() -> dict:
    """Mines and projects run by publicly traded companies (built by scripts/build_listed_miners.py)."""
    with LISTED_MINERS_PATH.open(encoding="utf-8") as f:
        return json.load(f)
