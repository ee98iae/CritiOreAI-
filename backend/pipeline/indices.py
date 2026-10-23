"""Alteration and vegetation indices from Sentinel-2 reflectance.

Band ratios follow van der Werff & van der Meer (2016), "Sentinel-2A MSI and
Landsat 8 OLI provide data continuity for geological remote sensing":
- ferric iron (iron oxides, gossans):       B4 / B2
- ferrous iron:                             B12 / B8 + B3 / B4
- clay / hydroxyl (AlOH, MgOH, carbonate):  B11 / B12

Green vegetation also lifts these ratios, so alteration layers are masked
where NDVI is above VEG_NDVI.
"""

import numpy as np

VEG_NDVI = 0.35
# Below this reflectance (water, deep shadow) a band is mostly noise and ratios blow up.
MIN_REFL = 0.01


def _ratio(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        r = a / b
    r[~np.isfinite(r) | (b < MIN_REFL) | (a < MIN_REFL)] = np.nan
    return r.astype("float32")


def ndvi(b: dict[str, np.ndarray]) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        v = (b["B08"] - b["B04"]) / (b["B08"] + b["B04"])
    v[~np.isfinite(v)] = np.nan
    return v.astype("float32")


def alteration(b: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    veg = ndvi(b) > VEG_NDVI
    out = {
        "ferric_iron": _ratio(b["B04"], b["B02"]),
        "ferrous_iron": _ratio(b["B12"], b["B08"]) + _ratio(b["B03"], b["B04"]),
        "clay_hydroxyl": _ratio(b["B11"], b["B12"]),
    }
    for arr in out.values():
        arr[veg] = np.nan
    return out


def true_colour(b: dict[str, np.ndarray], max_refl: float = 0.3, gamma: float = 1 / 1.6) -> np.ndarray:
    """3 x H x W uint8 RGB; 0 marks no data."""
    rgb = np.stack([b["B04"], b["B03"], b["B02"]])
    missing = np.isnan(rgb).any(axis=0)
    scaled = np.clip(np.nan_to_num(rgb) / max_refl, 0, 1) ** gamma
    out = (1 + scaled * 254).astype("uint8")
    out[:, missing] = 0
    return out
