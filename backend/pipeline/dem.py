"""Copernicus DEM GLO-30 terrain: elevation, slope and hillshade.

Tiles come from the public AWS Open Data bucket, no account needed.
"""

import math

import numpy as np

from .grid import Grid
from .sources import first_valid, read_onto_grid

BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
NATIVE_M = 30.0


def tile_name(lat: int, lon: int) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"Copernicus_DSM_COG_10_{ns}{abs(lat):02d}_00_{ew}{abs(lon):03d}_00_DEM"


def tile_urls(bbox: tuple[float, float, float, float]) -> list[str]:
    s, w, n, e = bbox
    urls = []
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            name = tile_name(lat, lon)
            urls.append(f"{BUCKET}/{name}/{name}.tif")
    return urls


def elevation(grid: Grid) -> np.ndarray:
    tiles = [a for a in (read_onto_grid(u, grid, NATIVE_M) for u in tile_urls(grid.bbox)) if a is not None]
    if not tiles:
        raise RuntimeError("no Copernicus DEM tiles found for this region")
    return first_valid(tiles)


def slope_degrees(dem: np.ndarray, dx_m: float, dy_m: float) -> np.ndarray:
    gy, gx = np.gradient(dem, dy_m, dx_m)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")


def hillshade(dem: np.ndarray, dx_m: float, dy_m: float, azimuth: float = 315.0, altitude: float = 45.0) -> np.ndarray:
    """0–255 shaded relief, lit from the north-west by default."""
    gy, gx = np.gradient(dem, dy_m, dx_m)
    slope = np.arctan(np.hypot(gx, gy))
    # Rows run north to south, so a positive gy means the ground drops to the north.
    aspect = np.arctan2(-gx, gy)
    az, alt = math.radians(azimuth), math.radians(altitude)
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return (np.clip(shade, 0, 1) * 255).astype("float32")
