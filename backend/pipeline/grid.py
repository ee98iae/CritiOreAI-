"""The common grid every layer is resampled onto: WGS84, square degree cells."""

import math
from dataclasses import dataclass

from affine import Affine
from rasterio.crs import CRS

WGS84 = CRS.from_epsg(4326)
M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON_EQUATOR = 111_320.0


@dataclass(frozen=True)
class Grid:
    # (south, west, north, east) in degrees, same order as app.regions.Region.bbox
    bbox: tuple[float, float, float, float]
    res: float  # cell size in degrees

    @property
    def width(self) -> int:
        s, w, n, e = self.bbox
        return math.ceil(round((e - w) / self.res, 6))

    @property
    def height(self) -> int:
        s, w, n, e = self.bbox
        return math.ceil(round((n - s) / self.res, 6))

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    @property
    def transform(self) -> Affine:
        s, w, n, e = self.bbox
        return Affine(self.res, 0.0, w, 0.0, -self.res, n)

    @property
    def crs(self) -> CRS:
        return WGS84

    @property
    def mid_lat(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    def cell_size_m(self) -> tuple[float, float]:
        """(x, y) cell size in metres at the grid's middle latitude."""
        dx = self.res * M_PER_DEG_LON_EQUATOR * math.cos(math.radians(self.mid_lat))
        return dx, self.res * M_PER_DEG_LAT

    def finest_m(self) -> float:
        return min(self.cell_size_m())
