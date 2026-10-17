"""Builds the per-cell evidence stack from the satellite and terrain layers.

The source layers are ~50 m Sentinel-2 / Copernicus DEM rasters. They are averaged
onto a coarser model grid (default 0.005 deg, ~360 x 555 m), then each layer gets
neighbourhood context: alteration around a porphyry system spans kilometres, so the
mean and spread over ~1.5 km and ~5 km windows matter more than any single pixel.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import ndimage

# Single-band layers used as evidence. Hillshade and true colour are left out:
# they are display layers, and hillshade mostly encodes sun angle.
LAYERS = ("elevation", "slope", "ndvi", "ferric_iron", "ferrous_iron", "clay_hydroxyl")
S2_BANDS = ("B02", "B03", "B04", "B08", "B11", "B12")
# Neighbourhood windows in model cells (3 cells ~1.5 km, 9 cells ~5 km at 0.005 deg).
WINDOWS = (3, 9)


@dataclass
class Grid:
    """Model grid: north-up, cell (row, col) centre = (north - (row+.5)*res, west + (col+.5)*res)."""

    west: float
    north: float
    res: float
    shape: tuple[int, int]

    def cell_centres(self) -> tuple[np.ndarray, np.ndarray]:
        rows, cols = self.shape
        lat = self.north - (np.arange(rows) + 0.5) * self.res
        lon = self.west + (np.arange(cols) + 0.5) * self.res
        return lat, lon

    def index(self, lat: float, lon: float) -> tuple[int, int]:
        return int((self.north - lat) / self.res), int((lon - self.west) / self.res)


@dataclass
class Stack:
    grid: Grid
    names: list[str]
    values: np.ndarray  # (rows, cols, n_features), NaN where no data
    valid: np.ndarray  # (rows, cols) bool


def _read(path: Path, shape: tuple[int, int]) -> tuple[np.ndarray, "object"]:
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(path) as src:
        data = src.read(out_shape=(src.count, *shape), resampling=Resampling.average, masked=True)
        return np.ma.filled(data.astype("float32"), np.nan), src.bounds


def _nanmean_filter(a: np.ndarray, size: int) -> np.ndarray:
    ok = np.isfinite(a)
    num = ndimage.uniform_filter(np.where(ok, a, 0.0), size, mode="nearest")
    den = ndimage.uniform_filter(ok.astype("float32"), size, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0.2, num / den, np.nan)


def add_context(base: dict[str, np.ndarray], windows=WINDOWS) -> dict[str, np.ndarray]:
    """Per layer: the cell value, and per window its local mean, local std, and the
    cell minus the local mean (a 'stands out from its surroundings' signal)."""
    out = {}
    for name, a in base.items():
        out[name] = a
        for w in windows:
            m = _nanmean_filter(a, w)
            sq = _nanmean_filter(a * a, w)
            out[f"{name}_mean{w}"] = m
            out[f"{name}_std{w}"] = np.sqrt(np.clip(sq - m * m, 0, None))
            out[f"{name}_anom{w}"] = a - m
    return out


def build_stack(layers_dir: Path, res: float = 0.005, structure: bool = False) -> Stack:
    layers_dir = Path(layers_dir)
    import rasterio

    with rasterio.open(layers_dir / "elevation.tif") as ref:
        b = ref.bounds
    shape = (round((b.top - b.bottom) / res), round((b.right - b.left) / res))
    grid = Grid(west=b.left, north=b.top, res=res, shape=shape)

    base = {}
    for name in LAYERS:
        data, _ = _read(layers_dir / f"{name}.tif", shape)
        base[name] = data[0]
    s2, _ = _read(layers_dir / "sentinel2_reflectance.tif", shape)
    for i, band in enumerate(S2_BANDS):
        base[f"s2_{band}"] = s2[i]

    feats = add_context(base)
    if structure:
        from .structure import structure_layers

        extra = structure_layers(layers_dir, shape, res, (b.top + b.bottom) / 2)
        groups = {n: a for n, a in extra.items() if n.startswith("rock_group_")}
        feats.update(add_context({n: a for n, a in extra.items() if n not in groups}))
        # Rock-group shares only need the neighbourhood mean, not spread and anomaly.
        for n, a in groups.items():
            feats[n] = a
            feats[f"{n}_mean9"] = _nanmean_filter(a, 9)
    names = list(feats)
    values = np.stack([feats[n] for n in names], axis=-1)
    valid = np.isfinite(base["elevation"]) & np.isfinite(base["s2_B04"])
    return Stack(grid, names, values, valid)
