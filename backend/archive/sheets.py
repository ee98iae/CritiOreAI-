"""Soviet / international map sheet nomenclature -> bounding box (WGS84 degrees).

Soviet survey reports locate everything by map sheet, e.g. "M-46-86-Б" (1:50,000).

- 1:1,000,000  "M-46": row letter A.. (4 deg of latitude each, from the equator),
  column 1..60 (6 deg of longitude each, from 180 W).
- 1:100,000    "M-46-86": 144 sheets in a 12 x 12 grid, numbered row by row from the
  north-west corner; each is 30' of longitude by 20' of latitude.
- 1:50,000     "M-46-86-Б": quarters of a 1:100k sheet, А Б / В Г (NW NE / SW SE).
- 1:25,000     "M-46-86-Б-в": quarters again, а б / в г.

Northern hemisphere only, which is all CritiOre needs.
"""

import re
from dataclasses import dataclass

ROWS = "ABCDEFGHIJKLMNOPQRSTUV"
# Cyrillic letters that look like, or stand in for, the Latin ones in scanned text.
CYR_TO_LAT = str.maketrans({"А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P",
                            "С": "C", "Т": "T", "Х": "X"})
QUARTERS = {"А": (0, 0), "Б": (0, 1), "В": (1, 0), "Г": (1, 1)}
SUBQUARTERS = {"а": (0, 0), "б": (0, 1), "в": (1, 0), "г": (1, 1)}
# Latin letters people use when transliterating the quarter letters.
LATIN_QUARTERS = {"A": "А", "B": "Б", "V": "В", "G": "Г"}

PATTERN = re.compile(
    r"^\s*(?P<row>[A-VА-Я])\s*-\s*(?P<col>\d{1,2})"
    r"(?:\s*-\s*(?P<n100>\d{1,3}))?"
    r"(?:\s*-\s*(?P<q50>[АБВГABVG]))?"
    r"(?:\s*-\s*(?P<q25>[абвг]))?\s*$"
)


@dataclass(frozen=True)
class Box:
    south: float
    west: float
    north: float
    east: float

    @property
    def centre(self) -> tuple[float, float]:
        return (self.south + self.north) / 2, (self.west + self.east) / 2

    @property
    def half_diagonal_km(self) -> float:
        import math

        lat = math.radians((self.south + self.north) / 2)
        dy = (self.north - self.south) * 111.32
        dx = (self.east - self.west) * 111.32 * math.cos(lat)
        return math.hypot(dx, dy) / 2


def sheet_bbox(sheet: str) -> Box:
    m = PATTERN.match(sheet)
    if not m:
        raise ValueError(f"not a map sheet: {sheet!r}")
    row = m["row"].translate(CYR_TO_LAT)
    col = int(m["col"])
    if row not in ROWS or not 1 <= col <= 60:
        raise ValueError(f"not a map sheet: {sheet!r}")
    south = ROWS.index(row) * 4.0
    west = (col - 31) * 6.0
    box = Box(south, west, south + 4.0, west + 6.0)

    if m["n100"]:
        n = int(m["n100"])
        if not 1 <= n <= 144:
            raise ValueError(f"1:100,000 sheet number out of range in {sheet!r}")
        r, c = divmod(n - 1, 12)
        north = box.north - r * (4.0 / 12)
        west = box.west + c * 0.5
        box = Box(north - 4.0 / 12, west, north, west + 0.5)
    if m["q50"]:
        r, c = QUARTERS[LATIN_QUARTERS.get(m["q50"], m["q50"])]
        box = _quarter(box, r, c)
    if m["q25"]:
        r, c = SUBQUARTERS[m["q25"]]
        box = _quarter(box, r, c)
    return box


def _quarter(box: Box, r: int, c: int) -> Box:
    h = (box.north - box.south) / 2
    w = (box.east - box.west) / 2
    north = box.north - r * h
    west = box.west + c * w
    return Box(north - h, west, north, west + w)
