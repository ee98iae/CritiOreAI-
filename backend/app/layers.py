"""Serves the pipeline's raster layers: manifest, map tiles and point values."""

import json
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import HTTPException, Response
from rio_tiler.colormap import cmap
from rio_tiler.errors import TileOutsideBounds
from rio_tiler.io import Reader

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data" / "layers"
LEGEND_STOPS = 6
_EMPTY_PNG: bytes | None = None


def layers_dir() -> Path:
    return Path(os.environ.get("CRITIORE_LAYERS_DIR", DEFAULT_DIR))


@lru_cache(maxsize=16)
def _manifest_cached(path: str, mtime: float) -> dict:
    return json.loads(Path(path).read_text())


def manifest(region_id: str) -> dict | None:
    path = layers_dir() / region_id / "layers.json"
    if not path.exists():
        return None
    return _manifest_cached(str(path), path.stat().st_mtime)


def legend(colormap: str | None) -> list[str]:
    if not colormap:
        return []
    cm = cmap.get(colormap)
    idx = np.linspace(0, 255, LEGEND_STOPS).round().astype(int)
    return ["#{:02x}{:02x}{:02x}".format(*cm[int(i)][:3]) for i in idx]


def public_layers(region_id: str) -> dict:
    m = manifest(region_id)
    if m is None:
        return {"region": region_id, "built": False, "layers": []}
    layers = [
        {k: v for k, v in layer.items() if k not in ("file", "extra")} | {"legend": legend(layer.get("colormap"))}
        for layer in m["layers"]
    ]
    meta = {k: v for k, v in m.items() if k != "layers"}
    return {**meta, "built": True, "layers": layers}


def _layer(region_id: str, layer_id: str) -> tuple[dict, Path]:
    m = manifest(region_id)
    layer = next((l for l in (m or {}).get("layers", []) if l["id"] == layer_id), None)
    if layer is None:
        raise HTTPException(404, f"Unknown layer '{layer_id}' for region '{region_id}'")
    return layer, layers_dir() / region_id / layer["file"]


def _empty_png() -> bytes:
    global _EMPTY_PNG
    if _EMPTY_PNG is None:
        from rio_tiler.models import ImageData

        _EMPTY_PNG = ImageData(np.zeros((4, 1, 1), dtype="uint8")).render(img_format="PNG", add_mask=False)
    return _EMPTY_PNG


def tile_png(region_id: str, layer_id: str, z: int, x: int, y: int) -> Response:
    layer, path = _layer(region_id, layer_id)
    headers = {"Cache-Control": "private, max-age=3600"}
    try:
        with Reader(str(path)) as src:
            img = src.tile(x, y, z, tilesize=256)
    except TileOutsideBounds:
        return Response(_empty_png(), media_type="image/png", headers=headers)
    if layer["kind"] == "continuous":
        lo, hi = layer["rescale"]
        img.rescale(in_range=((lo, hi),))
        png = img.render(img_format="PNG", colormap=cmap.get(layer["colormap"]))
    else:
        png = img.render(img_format="PNG")
    return Response(png, media_type="image/png", headers=headers)


def point_values(region_id: str, lat: float, lon: float) -> dict[str, float | None]:
    """Every continuous layer's value at a point, e.g. for the clicked-point evidence card."""
    m = manifest(region_id)
    out: dict[str, float | None] = {}
    for layer in (m or {}).get("layers", []):
        if layer["kind"] != "continuous":
            continue
        with Reader(str(layers_dir() / region_id / layer["file"])) as src:
            try:
                pt = src.point(lon, lat)
            except Exception:  # outside the layer's bounds
                out[layer["id"]] = None
                continue
        v = float(pt.data[0])
        masked = bool(np.ma.getmaskarray(pt.array)[0]) if hasattr(pt, "array") else False
        out[layer["id"]] = None if masked or not np.isfinite(v) else round(v, 4)
    return out
