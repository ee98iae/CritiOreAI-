import os
from typing import Literal

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path as PathParam, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import layers as layer_store
from .auth import User, authenticate, current_user, issue_token, require_region
from .data import Occurrence, load_occurrences
from .regions import PILOT_REGION, REGIONS
from .scoring import MODEL_VERSION, Cell, Score, rank_targets, score_grid, score_point

Commodity = Literal["Cu", "Ni", "Co", "Au", "Mo"]

app = FastAPI(title="CritiOre AI API", version="0.2.0")
# Everything except health and login needs a signed-in user.
api = APIRouter(dependencies=[Depends(current_user)])
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


def _visible(user: User, items: tuple[Occurrence, ...]) -> tuple[Occurrence, ...]:
    """A client sees only occurrences inside the regions on their account."""
    if user.role == "team" or "*" in user.regions:
        return items
    boxes = [REGIONS[r].bbox for r in user.regions if r in REGIONS]
    return tuple(o for o in items if any(_in_bbox(o, b) for b in boxes))


def _in_bbox(o: Occurrence, bbox: tuple[float, float, float, float]) -> bool:
    s, w, n, e = bbox
    return s <= o.lat <= n and w <= o.lon <= e


@app.get("/api/health")
def health():
    return {"status": "ok", "model_version": MODEL_VERSION, "occurrences": len(load_occurrences())}


@api.get("/api/regions")
def regions(user: User = Depends(current_user)):
    return [
        {"id": r.id, "name": r.name, "bbox": list(r.bbox), "commodities": list(r.commodities)}
        for r in REGIONS.values()
        if user.can_see(r.id)
    ]


@api.get("/api/occurrences")
def occurrences(
    commodity: Commodity | None = None,
    bbox: str | None = Query(None, description="south,west,north,east"),
    user: User = Depends(current_user),
):
    items = _visible(user, load_occurrences())
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


@api.get("/api/occurrences/{occurrence_id}")
def occurrence(occurrence_id: str, user: User = Depends(current_user)):
    for o in _visible(user, load_occurrences()):
        if o.id == occurrence_id:
            return o.to_feature()
    raise HTTPException(404, f"Unknown occurrence '{occurrence_id}'")


@api.post("/api/prospectivity/score")
def prospectivity_score(req: ScoreRequest):
    s = score_point(req.lat, req.lon, req.commodity, load_occurrences())
    return {"model_version": MODEL_VERSION, "commodity": req.commodity,
            "lat": req.lat, "lon": req.lon, **_score_json(s)}


@api.get("/api/prospectivity/grid")
def prospectivity_grid(
    commodity: Commodity = "Cu",
    region: str = PILOT_REGION.id,
    cell_deg: float = Query(0.05, ge=0.01, le=0.5),
    user: User = Depends(current_user),
):
    r = _region_or_404(region)
    require_region(user, r.id)
    cells = score_grid(r.bbox, cell_deg, commodity, load_occurrences())
    return {
        "type": "FeatureCollection",
        "model_version": MODEL_VERSION,
        "commodity": commodity,
        "features": [_cell_feature(c) for c in cells if c.score.score > 0.01],
    }


@api.get("/api/targets")
def targets(
    commodity: Commodity = "Cu",
    region: str = PILOT_REGION.id,
    limit: int = Query(10, ge=1, le=50),
    user: User = Depends(current_user),
):
    r = _region_or_404(region)
    require_region(user, r.id)
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


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


@app.post("/api/auth/login")
def login(req: LoginRequest):
    user = authenticate(req.email, req.password)
    if user is None:
        raise HTTPException(401, "Wrong email or password")
    return {"token": issue_token(user), "user": user.public()}


@api.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return user.public()


@api.get("/api/layers")
def layers(region: str = PILOT_REGION.id, user: User = Depends(current_user)):
    r = _region_or_404(region)
    require_region(user, r.id)
    return layer_store.public_layers(r.id)


@api.get("/api/layers/{region}/{layer_id}/tiles/{z}/{x}/{y}.png")
def layer_tile(
    region: str,
    layer_id: str,
    z: int = PathParam(ge=0, le=22),
    x: int = PathParam(ge=0),
    y: int = PathParam(ge=0),
    user: User = Depends(current_user),
):
    r = _region_or_404(region)
    require_region(user, r.id)
    return layer_store.tile_png(r.id, layer_id, z, x, y)


@api.get("/api/layers/{region}/values")
def layer_values(
    region: str,
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    user: User = Depends(current_user),
):
    r = _region_or_404(region)
    require_region(user, r.id)
    return {"lat": lat, "lon": lon, "values": layer_store.point_values(r.id, lat, lon)}


app.include_router(api)
