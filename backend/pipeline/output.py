"""Writes layers as Cloud-Optimized GeoTIFFs and keeps the layers.json manifest."""

import json
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import rasterio
from rasterio.shutil import copy as rio_copy

from .grid import Grid

MANIFEST = "layers.json"


@dataclass
class Layer:
    id: str
    title: str
    group: str  # Imagery, Terrain, Alteration
    description: str
    source: str
    units: str = ""
    kind: str = "continuous"  # continuous | rgb
    colormap: str | None = "viridis"  # a rio-tiler colormap name
    rescale: tuple[float, float] | None = None
    acquired: str = ""
    file: str = ""
    bounds: tuple[float, float, float, float] = (0, 0, 0, 0)  # west, south, east, north
    extra: dict = field(default_factory=dict)


def stretch(arr: np.ndarray, lo_pct: float = 2, hi_pct: float = 98) -> tuple[float, float]:
    vals = arr[np.isfinite(arr)]
    if vals.size == 0:
        return (0.0, 1.0)
    lo, hi = np.percentile(vals, [lo_pct, hi_pct])
    if hi <= lo:
        hi = lo + 1e-6
    return (round(float(lo), 4), round(float(hi), 4))


def write_cog(path: Path, data: np.ndarray, grid: Grid) -> None:
    """data is H x W float32 (NaN = no data) or B x H x W uint8 (0 = no data)."""
    if data.ndim == 2:
        data = data[np.newaxis]
    is_float = data.dtype.kind == "f"
    profile = {
        "driver": "GTiff",
        "width": grid.width,
        "height": grid.height,
        "count": data.shape[0],
        "dtype": data.dtype.name,
        "crs": grid.crs,
        "transform": grid.transform,
        "nodata": np.nan if is_float else 0,
        "tiled": True,
        "blockxsize": 512,
        "blockysize": 512,
        "compress": "deflate",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "staging.tif"
        with rasterio.open(staging, "w", **profile) as dst:
            dst.write(data)
        rio_copy(
            staging,
            path,
            driver="COG",
            compress="DEFLATE",
            predictor="3" if is_float else "2",
            overview_resampling="average",
            blocksize=512,
        )


def save_layer(out_dir: Path, layer: Layer, data: np.ndarray, grid: Grid) -> Layer:
    layer.file = f"{layer.id}.tif"
    s, w, n, e = grid.bbox
    layer.bounds = (w, s, e, n)
    if layer.kind == "continuous" and layer.rescale is None:
        layer.rescale = stretch(data)
    write_cog(out_dir / layer.file, data, grid)
    return layer


def write_manifest(out_dir: Path, region_id: str, grid: Grid, layers: list[Layer], meta: dict) -> Path:
    path = out_dir / MANIFEST
    doc = {
        "region": region_id,
        "bbox": list(grid.bbox),
        "resolution_deg": grid.res,
        "cell_size_m": [round(v, 1) for v in grid.cell_size_m()],
        **meta,
        "layers": [asdict(l) for l in layers],
    }
    path.write_text(json.dumps(doc, indent=2))
    return path
