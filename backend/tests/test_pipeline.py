import math

import numpy as np

from pipeline import dem, indices, sentinel2
from pipeline.grid import Grid
from pipeline.output import stretch
from pipeline.sources import first_valid, pick_overview

KHARKHIRAA = (48.8, 90.6, 50.4, 92.8)


def test_grid_geometry():
    g = Grid(KHARKHIRAA, 0.0005)
    assert g.shape == (3200, 4400)
    assert g.transform.c == 90.6 and g.transform.f == 50.4
    dx, dy = g.cell_size_m()
    assert 34 < dx < 37 and 55 < dy < 56


def test_pick_overview():
    assert pick_overview(10, [2, 4, 8, 16], 40) == 1  # 40 m
    assert pick_overview(10, [2, 4, 8, 16], 15) is None  # full resolution
    assert pick_overview(20, [2, 4], 45) == 0


def test_dem_tile_urls_cover_bbox():
    urls = dem.tile_urls(KHARKHIRAA)
    assert len(urls) == 9
    assert urls[0].endswith("Copernicus_DSM_COG_10_N48_00_E090_00_DEM/Copernicus_DSM_COG_10_N48_00_E090_00_DEM.tif")
    assert dem.tile_name(-1, -70) == "Copernicus_DSM_COG_10_S01_00_W070_00_DEM"


def test_sentinel2_squares_for_pilot():
    assert sentinel2.grid_squares(KHARKHIRAA) == ["46UCA", "46UCV", "46UDA", "46UDV"]
    assert sentinel2.square_path("46UDV") == "sentinel-s2-l2a-cogs/46/U/DV"


def test_rank_scenes_prefers_clear_full_scenes():
    mk = lambda i, cc, nd: sentinel2.Scene(i, "", "", cc, nd, {})  # noqa: E731
    ranked = sentinel2.rank_scenes([mk("edge", 0, 90), mk("cloudy", 30, 0), mk("clear", 2, 5)])
    assert [s.id for s in ranked] == ["clear", "cloudy", "edge"]


def test_first_valid():
    a = np.array([[1.0, np.nan], [np.nan, np.nan]])
    b = np.array([[9.0, 2.0], [np.nan, 3.0]])
    out = first_valid([a, b])
    assert out[0, 0] == 1 and out[0, 1] == 2 and out[1, 1] == 3 and np.isnan(out[1, 0])


def test_slope_of_a_plane():
    # Rises 1 m per 10 m eastward: atan(0.1) = 5.71 degrees everywhere.
    x = np.arange(20, dtype="float32") * 1.0
    plane = np.tile(x, (10, 1))
    s = dem.slope_degrees(plane, 10, 10)
    assert np.allclose(s, math.degrees(math.atan(0.1)), atol=1e-4)


def test_hillshade_lights_slopes_facing_the_sun():
    flat = dem.hillshade(np.zeros((5, 5)), 10, 10)
    # Ground rising to the south-east faces north-west, toward a 315 degree sun.
    rows, cols = np.mgrid[0:5, 0:5].astype("float32")
    facing = dem.hillshade((rows + cols) * 5, 10, 10)
    away = dem.hillshade(-(rows + cols) * 5, 10, 10)
    assert facing.mean() > flat.mean() > away.mean()


def _bands(**vals):
    shape = (2, 2)
    return {b: np.full(shape, vals.get(b, 0.2), dtype="float32") for b in ("B02", "B03", "B04", "B08", "B11", "B12")}


def test_alteration_ratios():
    b = _bands(B02=0.1, B04=0.3, B03=0.2, B08=0.32, B11=0.4, B12=0.2)
    alt = indices.alteration(b)
    assert np.allclose(alt["ferric_iron"], 3.0)
    assert np.allclose(alt["clay_hydroxyl"], 2.0)
    assert np.allclose(alt["ferrous_iron"], 0.2 / 0.32 + 0.2 / 0.3)


def test_alteration_masked_on_vegetation():
    b = _bands(B04=0.05, B08=0.5)  # NDVI 0.82
    assert np.isnan(indices.alteration(b)["ferric_iron"]).all()


def test_ratio_handles_zero_and_nan():
    b = _bands(B02=0.0)
    b["B04"][0, 0] = np.nan
    assert np.isnan(indices.alteration(b)["ferric_iron"]).all()


def test_true_colour_marks_missing_as_zero():
    b = _bands()
    b["B02"][0, 0] = np.nan
    rgb = indices.true_colour(b)
    assert rgb.shape == (3, 2, 2) and rgb.dtype == np.uint8
    assert (rgb[:, 0, 0] == 0).all() and (rgb[:, 1, 1] > 0).all()


def test_stretch_ignores_nan():
    arr = np.array([np.nan, *range(101)], dtype="float32")
    assert stretch(arr) == (2.0, 98.0)


def test_offset_skipped_when_dns_already_harmonised():
    # Blue DNs around 700-1300: applying -0.1 would make many negative.
    harmonised = np.linspace(683, 1369, 100)
    assert sentinel2.effective_offset(harmonised, 0.0001, -0.1) == 0.0
    # DNs that still carry the +1000 offset keep it.
    raw = harmonised + 1000
    assert sentinel2.effective_offset(raw, 0.0001, -0.1) == -0.1
    assert sentinel2.effective_offset(raw, 0.0001, 0.0) == 0.0


def test_ratios_ignore_dark_pixels():
    b = _bands(B02=0.002, B04=0.1)
    assert np.isnan(indices.alteration(b)["ferric_iron"]).all()
