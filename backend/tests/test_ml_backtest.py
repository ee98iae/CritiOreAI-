"""Back-test mechanics on a synthetic grid where the answer is known."""

import numpy as np
import pytest

pytest.importorskip("sklearn")

from ml.backtest import Site, backtest, hit_rate, site_rank  # noqa: E402
from ml.features import Grid, Stack, add_context  # noqa: E402


def synthetic_stack(sites, size=120, res=0.005, west=91.0, north=49.5, seed=0):
    """Noise everywhere, plus a strong 'alteration' halo around each site."""
    rng = np.random.default_rng(seed)
    grid = Grid(west=west, north=north, res=res, shape=(size, size))
    lat, lon = grid.cell_centres()
    alteration = rng.normal(0, 1, grid.shape)
    for s in sites:
        d = np.hypot((lat[:, None] - s.lat) * 111, (lon[None, :] - s.lon) * 73)
        alteration += 4 * np.exp(-(d**2) / (2 * 1.5**2))
    feats = add_context({"alteration": alteration, "noise": rng.normal(0, 1, grid.shape)})
    names = list(feats)
    return Stack(grid, names, np.stack([feats[n] for n in names], -1), np.ones(grid.shape, bool))


def test_model_finds_held_out_sites_by_their_signature():
    sites = [Site(str(i), f"s{i}", 49.5 - 0.05 - 0.1 * (i % 5), 91.05 + 0.1 * (i // 5), ("Cu",)) for i in range(6)]
    stack = synthetic_stack(sites)
    results = backtest(stack, sites, background=3000, max_iter=40)
    assert hit_rate([r.model_rank for r in results]) >= 5 / 6


def test_site_rank_is_share_of_area_scoring_higher():
    stack = synthetic_stack([])
    score = np.zeros(stack.grid.shape)
    score[:12, :] = 1.0  # top 10% of the area
    inside = Site("a", "a", stack.grid.north - 0.02, stack.grid.west + 0.3, ("Cu",))
    outside = Site("b", "b", stack.grid.north - 0.4, stack.grid.west + 0.3, ("Cu",))
    assert site_rank(score, stack, inside) == 0.0
    assert site_rank(score, stack, outside) == pytest.approx(0.1)


def test_hit_rate_ignores_sites_without_data():
    assert hit_rate([0.05, 0.5, float("nan")]) == 0.5


def test_lineaments_find_a_straight_valley_and_contacts_find_boundaries():
    from ml.structure import contacts, lineaments

    from scipy import ndimage

    yy, xx = np.mgrid[0:200, 0:200].astype(float)
    hills = ndimage.gaussian_filter(np.random.default_rng(0).normal(0, 1, (200, 200)), 6)
    dem = 1000 + 0.5 * xx + 400 * hills
    dem -= 60 * np.exp(-((xx - 100) ** 2) / (2 * 3.0**2))  # straight N-S valley at x = 100
    lin = lineaments(dem, 0.1, 0.1)
    near = np.abs(xx - 100) <= 6
    assert lin[near].any(axis=None) and np.mean(lin[:, 94:107].any(axis=1)) > 0.8  # traced along its length
    assert lin[near].mean() > 5 * lin[~near].mean()  # and far denser than anywhere else

    groups = np.zeros((10, 10), np.int16)
    groups[:, 5:] = 1
    c = contacts(groups)
    assert c[:, 4].all() and c.sum() == 10
