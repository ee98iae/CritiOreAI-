"""Reads remote Cloud-Optimized GeoTIFFs onto a Grid.

Only the overview level that matches the grid's resolution is fetched, so a
whole pilot region costs a few hundred MB of HTTP range requests, not the full
10 m archives.
"""

import logging

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.errors import RasterioIOError
from rasterio.warp import reproject

from .grid import Grid

log = logging.getLogger(__name__)

# GDAL settings for fast, read-only HTTP access to public buckets.
GDAL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "GDAL_HTTP_MULTIRANGE": "YES",
    "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    "GDAL_HTTP_MAX_RETRY": "4",
    "GDAL_HTTP_RETRY_DELAY": "2",
    "VSI_CACHE": "TRUE",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.TIF,.tiff",
}


def pick_overview(native_m: float, factors: list[int], target_m: float, tolerance: float = 1.25) -> int | None:
    """Index of the coarsest overview still fine enough for target_m, or None for full resolution."""
    best = None
    for i, f in enumerate(factors):
        if native_m * f <= target_m * tolerance:
            best = i
    return best


def read_onto_grid(
    url: str,
    grid: Grid,
    native_m: float,
    resampling: Resampling = Resampling.average,
    dtype: str = "float32",
    band: int = 1,
) -> np.ndarray | None:
    """Reproject one band of a remote raster onto the grid. Cells it doesn't cover are NaN.

    Returns None when the file doesn't exist.
    """
    with rasterio.Env(**GDAL_ENV):
        try:
            with rasterio.open(url) as probe:
                factors = probe.overviews(band)
        except RasterioIOError as exc:
            log.warning("skipping %s: %s", url, exc)
            return None
        level = pick_overview(native_m, factors, grid.finest_m())
        opts = {} if level is None else {"overview_level": level}
        with rasterio.open(url, **opts) as src:
            out = np.full(grid.shape, np.nan, dtype=dtype)
            reproject(
                source=rasterio.band(src, band),
                destination=out,
                dst_transform=grid.transform,
                dst_crs=grid.crs,
                dst_nodata=np.nan,
                src_nodata=src.nodata,
                resampling=resampling,
            )
    return out


def first_valid(stack: list[np.ndarray]) -> np.ndarray:
    """Mosaic: each cell takes the first array in the list that has a value there."""
    out = np.full_like(stack[0], np.nan)
    for arr in stack:
        fill = np.isnan(out) & ~np.isnan(arr)
        out[fill] = arr[fill]
    return out
