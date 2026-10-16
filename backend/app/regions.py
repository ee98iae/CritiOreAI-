from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    id: str
    name: str
    # (south, west, north, east) in WGS84 degrees
    bbox: tuple[float, float, float, float]
    commodities: tuple[str, ...]


PILOT_REGION = Region(
    id="kharkhiraa",
    name="Kharkhiraa uplands, Western Mongolia (pilot)",
    bbox=(48.8, 90.6, 50.4, 92.8),
    commodities=("Cu", "Ni", "Co"),
)

REGIONS = {PILOT_REGION.id: PILOT_REGION}
