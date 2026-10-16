"""Sentinel-2 L2A surface reflectance from the public AWS Open Data COG bucket.

The Earth Search STAC API is the usual way in, but the bucket itself can be
listed directly, which is all this needs: every scene folder carries its own
STAC item JSON with cloud cover, coverage and band scale/offset.
"""

import json
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import mgrs
import numpy as np
from rasterio.enums import Resampling

from .grid import Grid
from .sources import first_valid, read_onto_grid

log = logging.getLogger(__name__)

BUCKET = "https://sentinel-cogs.s3.us-west-2.amazonaws.com"
PREFIX = "sentinel-s2-l2a-cogs"
S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"

# Band name in the bucket -> (STAC asset key, native resolution in metres)
BANDS = {
    "B02": ("blue", 10),
    "B03": ("green", 10),
    "B04": ("red", 10),
    "B08": ("nir", 10),
    "B11": ("swir16", 20),
    "B12": ("swir22", 20),
}
# Scene classification classes treated as unusable: saturated, cloud shadow,
# cloud (medium, high), thin cirrus, snow and ice.
SCL_BAD = (1, 3, 8, 9, 10, 11)


@dataclass(frozen=True)
class Scene:
    id: str
    url: str  # folder URL, no trailing slash
    datetime: str
    cloud_cover: float
    nodata_pct: float
    item: dict

    def band_url(self, band: str) -> str:
        return f"{self.url}/{band}.tif"

    def scale_offset(self, band: str) -> tuple[float, float]:
        asset = self.item["assets"].get(BANDS[band][0], {})
        rb = (asset.get("raster:bands") or [{}])[0]
        return float(rb.get("scale", 0.0001)), float(rb.get("offset", 0.0))


def grid_squares(bbox: tuple[float, float, float, float], step: float = 0.05) -> list[str]:
    """MGRS 100 km squares (e.g. '46UDV') that touch the bbox."""
    m = mgrs.MGRS()
    s, w, n, e = bbox
    squares = set()
    lat = s
    while lat <= n + 1e-9:
        lon = w
        while lon <= e + 1e-9:
            squares.add(m.toMGRS(min(lat, n), min(lon, e), MGRSPrecision=0))
            lon += step
        lat += step
    return sorted(squares)


def square_path(square: str) -> str:
    zone, band, sq = re.fullmatch(r"(\d{1,2})([C-X])([A-Z]{2})", square).groups()
    return f"{PREFIX}/{int(zone)}/{band}/{sq}"


def _list_prefixes(prefix: str) -> list[str]:
    url = f"{BUCKET}/?list-type=2&delimiter=/&prefix={prefix}"
    with urllib.request.urlopen(url, timeout=60) as r:
        root = ET.fromstring(r.read())
    return [p.text for p in root.iter(f"{S3_NS}Prefix") if p.text and p.text != prefix]


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def list_scenes(square: str, years: list[int], months: list[int]) -> list[Scene]:
    scenes = []
    for y in years:
        for mo in months:
            for prefix in _list_prefixes(f"{square_path(square)}/{y}/{mo}/"):
                sid = prefix.rstrip("/").rsplit("/", 1)[-1]
                url = f"{BUCKET}/{prefix.rstrip('/')}"
                try:
                    item = _get_json(f"{url}/{sid}.json")
                except Exception as exc:  # a scene without metadata is skipped, not fatal
                    log.warning("no metadata for %s: %s", sid, exc)
                    continue
                p = item["properties"]
                scenes.append(
                    Scene(
                        id=sid,
                        url=url,
                        datetime=p["datetime"],
                        cloud_cover=float(p.get("eo:cloud_cover", 100)),
                        nodata_pct=float(p.get("s2:nodata_pixel_percentage", 0)),
                        item=item,
                    )
                )
    return scenes


def rank_scenes(scenes: list[Scene], max_nodata_pct: float = 20.0) -> list[Scene]:
    """Clearest, fullest scenes first. Mostly-empty edge-of-swath scenes go last."""
    full = [s for s in scenes if s.nodata_pct <= max_nodata_pct]
    partial = [s for s in scenes if s.nodata_pct > max_nodata_pct]
    key = lambda s: (s.cloud_cover, s.nodata_pct)  # noqa: E731
    return sorted(full, key=key) + sorted(partial, key=key)


def effective_offset(dn: np.ndarray, scale: float, offset: float) -> float:
    """The offset to apply to these DNs.

    Since processing baseline 04.00 the L2A DNs carry a +1000 offset and the
    STAC item says offset -0.1. The COGs in this bucket have been seen with
    that offset already removed while the metadata still lists it (blue-band
    DNs well under 1000 over bare ground). Real reflectance can't be negative,
    so if more than 1% of pixels would come out below zero, the offset has
    already been applied and is skipped.
    """
    if offset >= 0:
        return offset
    valid = dn[np.isfinite(dn) & (dn > 0)]
    if valid.size and np.mean(valid * scale + offset < 0) > 0.01:
        return 0.0
    return offset


def read_scene(scene: Scene, grid: Grid) -> dict[str, np.ndarray] | None:
    """Reflectance (0–1) per band on the grid, with clouds, shadow and snow set to NaN."""
    scl = read_onto_grid(scene.band_url("SCL"), grid, native_m=20, resampling=Resampling.nearest)
    if scl is None:
        return None
    bad = np.isnan(scl) | np.isin(scl, SCL_BAD)
    if bad.all():
        return None
    out = {}
    for band, (_, native_m) in BANDS.items():
        dn = read_onto_grid(scene.band_url(band), grid, native_m=native_m)
        if dn is None:
            return None
        scale, listed = scene.scale_offset(band)
        offset = effective_offset(dn, scale, listed)
        if offset != listed:
            log.info("%s %s: DNs already harmonised, ignoring listed offset %s", scene.id, band, listed)
        refl = dn * scale + offset
        refl[bad | (dn <= 0)] = np.nan
        out[band] = refl.astype("float32")
    return out


def composite(
    grid: Grid,
    years: list[int],
    months: list[int],
    scenes_per_square: int = 3,
) -> tuple[dict[str, np.ndarray], list[Scene]]:
    """Cloud-free mosaic: each cell takes the clearest scene that sees it."""
    layers: list[dict[str, np.ndarray]] = []
    used: list[Scene] = []
    for square in grid_squares(grid.bbox):
        ranked = rank_scenes(list_scenes(square, years, months))
        log.info("%s: %d candidate scenes", square, len(ranked))
        for scene in ranked[:scenes_per_square]:
            log.info("reading %s (cloud %.1f%%, nodata %.1f%%)", scene.id, scene.cloud_cover, scene.nodata_pct)
            bands = read_scene(scene, grid)
            if bands is not None:
                layers.append(bands)
                used.append(scene)
    if not layers:
        raise RuntimeError("no usable Sentinel-2 scenes found for this region")
    # A cell must come from one scene for every band, so mosaic on a shared validity mask.
    valid = [~np.isnan(np.stack(list(b.values()))).any(axis=0) for b in layers]
    mosaic = {}
    for band in BANDS:
        stack = []
        for b, ok in zip(layers, valid):
            arr = b[band].copy()
            arr[~ok] = np.nan
            stack.append(arr)
        mosaic[band] = first_valid(stack)
    return mosaic, used
