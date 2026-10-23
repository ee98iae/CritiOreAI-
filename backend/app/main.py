import os
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .data import Occurrence, load_listed_miners, load_occurrences
from .regions import PILOT_REGION, REGIONS
from .scoring import MODEL_VERSION, Cell, Score, rank_targets, score_grid, score_point

Commodity = Literal["Cu", "W", "Au", "Mo", "Ni", "Co"]

app = FastAPI(title="CritiOre AI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CRITIORE_CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScoreRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    commodity: Commodity = "Cu"


def _score_json(s: Score) -> dict:
    return {
        "score": s.score,
        "confidence": s.confidence,
        "evidence": [
            {
                "id": e.occurrence.id,
                "name": e.occurrence.name,
                "type": e.occurrence.type,
                "commodities": list(e.occurrence.commodities),
                "distance_km": round(e.distance_km, 2),
                "contribution": round(e.contribution, 4),
            }
            for e in s.evidence
        ],
    }


def _cell_feature(c: Cell, **extra) -> dict:
    ring = [[c.west, c.south], [c.east, c.south], [c.east, c.north], [c.west, c.north], [c.west, c.south]]
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": {"score": c.score.score, "confidence": c.score.confidence, **extra},
    }


def _region_or_404(region_id: str):
    region = REGIONS.get(region_id)
    if region is None:
        raise HTTPException(404, f"Unknown region '{region_id}'")
    return region


def _in_bbox(o: Occurrence, bbox: tuple[float, float, float, float]) -> bool:
    s, w, n, e = bbox
    return s <= o.lat <= n and w <= o.lon <= e


@app.get("/api/health")
def health():
    return {"status": "ok", "model_version": MODEL_VERSION, "occurrences": len(load_occurrences())}


@app.get("/api/regions")
def regions():
    return [
        {"id": r.id, "name": r.name, "bbox": list(r.bbox), "commodities": list(r.commodities)}
        for r in REGIONS.values()
    ]


@app.get("/api/occurrences")
def occurrences(
    commodity: Commodity | None = None,
    bbox: str | None = Query(None, description="south,west,north,east"),
):
    items = load_occurrences()
    if commodity:
        items = tuple(o for o in items if commodity in o.commodities)
    if bbox:
        try:
            box = tuple(float(v) for v in bbox.split(","))
        except ValueError:
            raise HTTPException(422, "bbox must be four numbers: south,west,north,east")
        if len(box) != 4:
            raise HTTPException(422, "bbox must be four numbers: south,west,north,east")
        items = tuple(o for o in items if _in_bbox(o, box))
    return {"type": "FeatureCollection", "features": [o.to_feature() for o in items]}


@app.get("/api/occurrences/{occurrence_id}")
def occurrence(occurrence_id: str):
    for o in load_occurrences():
        if o.id == occurrence_id:
            return o.to_feature()
    raise HTTPException(404, f"Unknown occurrence '{occurrence_id}'")


@app.get("/api/listed-miners")
def listed_miners(status: str | None = Query(None, description="producing, development, exploration, standby or unverified")):
    fc = load_listed_miners()
    feats = fc["features"]
    if status:
        feats = [f for f in feats if f["properties"]["status"] == status]
    return {"type": "FeatureCollection", "features": feats}


@app.post("/api/prospectivity/score")
def prospectivity_score(req: ScoreRequest):
    s = score_point(req.lat, req.lon, req.commodity, load_occurrences())
    return {"model_version": MODEL_VERSION, "commodity": req.commodity,
            "lat": req.lat, "lon": req.lon, **_score_json(s)}


@app.get("/api/prospectivity/grid")
def prospectivity_grid(
    commodity: Commodity = "Cu",
    region: str = PILOT_REGION.id,
    cell_deg: float = Query(0.05, ge=0.01, le=0.5),
):
    r = _region_or_404(region)
    cells = score_grid(r.bbox, cell_deg, commodity, load_occurrences())
    return {
        "type": "FeatureCollection",
        "model_version": MODEL_VERSION,
        "commodity": commodity,
        "features": [_cell_feature(c) for c in cells if c.score.score > 0.01],
    }


@app.get("/api/targets")
def targets(
    commodity: Commodity = "Cu",
    region: str = PILOT_REGION.id,
    limit: int = Query(10, ge=1, le=50),
):
    r = _region_or_404(region)
    cells = score_grid(r.bbox, 0.05, commodity, load_occurrences())
    ranked = rank_targets(cells, limit)
    return {
        "model_version": MODEL_VERSION,
        "commodity": commodity,
        "targets": [
            {
                "rank": i + 1,
                "lat": round(c.center[0], 4),
                "lon": round(c.center[1], 4),
                **_score_json(c.score),
            }
            for i, c in enumerate(ranked)
        ],
    }
