"""Placeholder prospectivity model.

Scores a location by its proximity to known occurrences of the target
commodity (a Gaussian kernel density, squashed to 0..1). This stands in for the
ML model from the PRD so the API contract and UI can be built now; swap
`score_point` for the trained model later without changing callers.
"""

import math
from dataclasses import dataclass

from .data import Occurrence

MODEL_VERSION = "placeholder-proximity-v0"

# How much a known site counts, by how well established it is.
TYPE_WEIGHT = {"deposit": 1.0, "occurrence": 0.6, "showing": 0.3}
# Commodities that commonly occur together; a related hit counts half.
RELATED = {
    "Cu": {"Mo", "Au", "Co", "Ni"},
    "Ni": {"Co", "Cu"},
    "Co": {"Ni", "Cu"},
    "Au": {"Cu"},
    "Mo": {"Cu", "W"},
    "W": {"Mo", "Sn"},
}
SIGMA_KM = 8.0
EVIDENCE_LIMIT = 5


@dataclass(frozen=True)
class Evidence:
    occurrence: Occurrence
    distance_km: float
    contribution: float


@dataclass(frozen=True)
class Score:
    score: float
    confidence: str
    evidence: list[Evidence]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _commodity_factor(occ: Occurrence, commodity: str) -> float:
    if commodity in occ.commodities:
        return 1.0
    if RELATED.get(commodity, set()) & set(occ.commodities):
        return 0.5
    return 0.0


def score_point(lat: float, lon: float, commodity: str, occurrences: tuple[Occurrence, ...]) -> Score:
    evidence = []
    cutoff_km = 4 * SIGMA_KM
    for occ in occurrences:
        factor = _commodity_factor(occ, commodity)
        if factor == 0.0:
            continue
        d = haversine_km(lat, lon, occ.lat, occ.lon)
        if d > cutoff_km:
            continue
        w = TYPE_WEIGHT.get(occ.type, 0.3) * factor * math.exp(-(d**2) / (2 * SIGMA_KM**2))
        evidence.append(Evidence(occ, d, w))

    density = sum(e.contribution for e in evidence)
    score = 1.0 - math.exp(-density)
    near = sum(1 for e in evidence if e.distance_km <= 2 * SIGMA_KM)
    confidence = "high" if near >= 5 else "medium" if near >= 2 else "low"
    evidence.sort(key=lambda e: e.contribution, reverse=True)
    return Score(round(score, 4), confidence, evidence[:EVIDENCE_LIMIT])


@dataclass(frozen=True)
class Cell:
    south: float
    west: float
    north: float
    east: float
    score: Score

    @property
    def center(self) -> tuple[float, float]:
        return ((self.south + self.north) / 2, (self.west + self.east) / 2)


def score_grid(bbox: tuple[float, float, float, float], cell_deg: float, commodity: str,
               occurrences: tuple[Occurrence, ...]) -> list[Cell]:
    south, west, north, east = bbox
    rows = max(1, round((north - south) / cell_deg))
    cols = max(1, round((east - west) / cell_deg))
    dlat = (north - south) / rows
    dlon = (east - west) / cols
    cells = []
    for i in range(rows):
        for j in range(cols):
            s, w = south + i * dlat, west + j * dlon
            n, e = s + dlat, w + dlon
            cells.append(Cell(s, w, n, e, score_point((s + n) / 2, (w + e) / 2, commodity, occurrences)))
    return cells


def rank_targets(cells: list[Cell], limit: int, min_separation_km: float = 10.0) -> list[Cell]:
    """Highest-scoring cells, skipping any too close to one already picked."""
    picked: list[Cell] = []
    for cell in sorted(cells, key=lambda c: c.score.score, reverse=True):
        if cell.score.score <= 0:
            break
        lat, lon = cell.center
        if all(haversine_km(lat, lon, *p.center) >= min_separation_km for p in picked):
            picked.append(cell)
            if len(picked) == limit:
                break
    return picked
