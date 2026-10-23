"""Build all milestone-1 layers for a region.

    python -m pipeline.run --region kharkhiraa
    python -m pipeline.run --region kharkhiraa --res 0.0004 --years 2024 2023

Writes to data/layers/<region>/ unless --out is given.
"""

import argparse
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import json

import numpy as np
import rasterio

from app.regions import REGIONS

from . import dem, indices, sentinel2
from .grid import Grid
from .output import Layer, save_layer, write_cog, write_manifest

log = logging.getLogger("pipeline")
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "layers"


REFLECTANCE = "sentinel2_reflectance.tif"


def save_reflectance(out_dir: Path, bands: dict[str, np.ndarray], grid: Grid, scenes: list[str]) -> None:
    """Keep the composite (reflectance x 10000, uint16, 0 = no data) so indices and the model can reuse it."""
    stack = []
    for b in sentinel2.BANDS:
        scaled = np.clip(np.round(np.nan_to_num(bands[b]) * 10000), 1, 65535)
        scaled[np.isnan(bands[b])] = 0
        stack.append(scaled.astype("uint16"))
    write_cog(out_dir / REFLECTANCE, np.stack(stack), grid)
    (out_dir / "sentinel2_scenes.json").write_text(json.dumps({"bands": list(sentinel2.BANDS), "scenes": scenes}))


def load_reflectance(out_dir: Path) -> tuple[dict[str, np.ndarray], list[str]]:
    meta = json.loads((out_dir / "sentinel2_scenes.json").read_text())
    with rasterio.open(out_dir / REFLECTANCE) as src:
        data = src.read().astype("float32")
    data[data == 0] = np.nan
    return {b: data[i] / 10000 for i, b in enumerate(meta["bands"])}, meta["scenes"]


def build(
    region_id: str,
    res: float,
    years: list[int],
    months: list[int],
    out_dir: Path,
    skip_s2: bool = False,
    reuse: bool = False,
) -> Path:
    region = REGIONS[region_id]
    grid = Grid(region.bbox, res)
    dx, dy = grid.cell_size_m()
    log.info("grid %d x %d cells, %.0f x %.0f m", grid.width, grid.height, dx, dy)
    layers: list[Layer] = []

    t = time.time()
    elev = load_layer(out_dir / "elevation.tif") if reuse and (out_dir / "elevation.tif").exists() else dem.elevation(grid)
    log.info("DEM read in %.0fs", time.time() - t)
    filled = np.where(np.isnan(elev), np.nanmean(elev), elev)
    cop = "Copernicus DEM GLO-30 (ESA, AWS Open Data)"
    layers.append(save_layer(out_dir, Layer(
        "elevation", "Elevation", "Terrain", "Height above sea level.", cop, units="m", colormap="terrain"), elev, grid))
    layers.append(save_layer(out_dir, Layer(
        "slope", "Slope", "Terrain", "Steepness of the ground; steep breaks often follow faults and resistant units.",
        cop, units="degrees", colormap="magma"), dem.slope_degrees(filled, dx, dy), grid))
    layers.append(save_layer(out_dir, Layer(
        "hillshade", "Hillshade", "Terrain", "Shaded relief lit from the north-west, for reading structure and lineaments.",
        cop, colormap="greys_r", rescale=(0, 255)), dem.hillshade(filled, dx, dy), grid))

    scene_ids: list[str] = []
    if not skip_s2:
        t = time.time()
        if reuse and (out_dir / REFLECTANCE).exists():
            bands, scene_ids = load_reflectance(out_dir)
            log.info("reusing the saved Sentinel-2 composite (%d scenes)", len(scene_ids))
        else:
            bands, scenes = sentinel2.composite(grid, years, months)
            scene_ids = [s.id for s in scenes]
            log.info("Sentinel-2 composite from %d scenes in %.0fs", len(scenes), time.time() - t)
            save_reflectance(out_dir, bands, grid, scene_ids)
        # Scene ids carry the date: S2B_46UDV_20240916_0_L2A
        dates = sorted(f"{d[:4]}-{d[4:6]}-{d[6:8]}" for d in (sid.split("_")[2] for sid in scene_ids))
        acquired = f"{dates[0]} to {dates[-1]}" if dates else ""
        s2 = "Sentinel-2 L2A (ESA Copernicus, AWS Open Data)"
        layers.append(save_layer(out_dir, Layer(
            "true_colour", "True colour", "Imagery", "Cloud-free Sentinel-2 composite (bands 4, 3, 2).",
            s2, kind="rgb", colormap=None, acquired=acquired), indices.true_colour(bands), grid))
        layers.append(save_layer(out_dir, Layer(
            "ndvi", "Vegetation (NDVI)", "Imagery", "Green vegetation; alteration layers are masked where NDVI > "
            f"{indices.VEG_NDVI}.", s2, colormap="rdylgn", rescale=(-0.1, 0.6), acquired=acquired),
            indices.ndvi(bands), grid))
        alt = indices.alteration(bands)
        layers.append(save_layer(out_dir, Layer(
            "ferric_iron", "Iron oxide (ferric)", "Alteration",
            "Band ratio B4/B2. High values flag hematite, goethite and jarosite, as in gossans over sulphides.",
            s2, units="ratio", colormap="ylorrd", acquired=acquired), alt["ferric_iron"], grid))
        layers.append(save_layer(out_dir, Layer(
            "ferrous_iron", "Ferrous iron", "Alteration",
            "B12/B8 + B3/B4. High values flag ferrous silicates and mafic to ultramafic rocks (Ni, Co hosts).",
            s2, units="ratio", colormap="purples", acquired=acquired), alt["ferrous_iron"], grid))
        layers.append(save_layer(out_dir, Layer(
            "clay_hydroxyl", "Clay and hydroxyl", "Alteration",
            "Band ratio B11/B12. High values flag clays, micas, chlorite and carbonate, as in phyllic and argillic "
            "alteration around porphyry copper.", s2, units="ratio", colormap="ylgnbu", acquired=acquired),
            alt["clay_hydroxyl"], grid))

    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sentinel2_scenes": scene_ids,
    }
    path = write_manifest(out_dir, region_id, grid, layers, meta)
    log.info("wrote %d layers to %s", len(layers), out_dir)
    return path


def load_layer(path: Path) -> np.ndarray:
    with rasterio.open(path) as src:
        return src.read(1)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--region", default="kharkhiraa", choices=sorted(REGIONS))
    p.add_argument("--res", type=float, default=0.0005, help="cell size in degrees (0.0005 is about 35 x 55 m here)")
    p.add_argument("--years", type=int, nargs="+", default=[2024, 2023])
    p.add_argument("--months", type=int, nargs="+", default=[7, 8, 9], help="snow-free months to draw scenes from")
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--skip-s2", action="store_true", help="terrain only")
    p.add_argument("--reuse", action="store_true", help="reuse the saved DEM and Sentinel-2 composite; only recompute layers")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("rasterio").setLevel(logging.WARNING)
    build(a.region, a.res, a.years, a.months, a.out or DATA_DIR / a.region, a.skip_s2, a.reuse)


if __name__ == "__main__":
    main()
