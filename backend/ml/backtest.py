"""Baseline prospectivity model and its blind back-test.

Model: gradient-boosted trees (scikit-learn HistGradientBoostingClassifier) on the
evidence stack. Cells within POSITIVE_KM of a known site are positives; a random
sample of the remaining area is "background". Background is unlabelled, not barren
(positive-unlabelled learning), so the output is a relative ranking, not a probability.

Back-test (the PRD gate: >= 70% of known deposits inside the top 10% of the area):
leave one site out. Its cells, and everything within EXCLUDE_KM of it, are dropped
from training; the model scores the whole area; the site's score is the mean over
cells within POSITIVE_KM (USGS coordinates are only good to a few km). Its rank is
the share of the area that scores higher. A site "hits" when that share is <= 10%.
The same test is run for the proximity placeholder (scored from the other sites
only) and for a random map, which hits 10% of the time by definition.
"""

import math
from dataclasses import dataclass

import numpy as np

from .features import Stack

POSITIVE_KM = 1.5
EXCLUDE_KM = 5.0
BACKGROUND_CELLS = 20_000
TOP_SHARE = 0.10


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    lat: float
    lon: float
    commodities: tuple[str, ...]


@dataclass
class SiteResult:
    site: Site
    model_rank: float  # share of area scoring higher (0 = best)
    proximity_rank: float


def distance_km(stack: Stack, lat: float, lon: float) -> np.ndarray:
    """Approximate distance from every model cell to a point (equirectangular, fine at this scale)."""
    clat, clon = stack.grid.cell_centres()
    dy = (clat[:, None] - lat) * 111.32
    dx = (clon[None, :] - lon) * 111.32 * math.cos(math.radians(lat))
    return np.hypot(dy, dx)


def make_model(seed: int = 0, max_iter: int = 200):
    from sklearn.ensemble import HistGradientBoostingClassifier

    return HistGradientBoostingClassifier(
        max_iter=max_iter,
        learning_rate=0.05,
        max_leaf_nodes=15,
        min_samples_leaf=40,
        l2_regularization=1.0,
        class_weight="balanced",
        random_state=seed,
    )


def training_set(
    stack: Stack, sites: list[Site], exclude: np.ndarray, rng: np.random.Generator, background: int = BACKGROUND_CELLS
):
    near_any = np.zeros(stack.grid.shape, bool)
    pos = np.zeros(stack.grid.shape, bool)
    for s in sites:
        d = distance_km(stack, s.lat, s.lon)
        pos |= d <= POSITIVE_KM
        near_any |= d <= 2 * POSITIVE_KM
    usable = stack.valid & ~exclude
    pos &= usable
    bg_pool = np.flatnonzero((usable & ~near_any).ravel())
    bg = rng.choice(bg_pool, size=min(background, bg_pool.size), replace=False)
    flat = stack.values.reshape(-1, stack.values.shape[-1])
    pos_idx = np.flatnonzero(pos.ravel())
    X = np.concatenate([flat[pos_idx], flat[bg]])
    y = np.concatenate([np.ones(pos_idx.size), np.zeros(bg.size)])
    return X, y


def predict_map(model, stack: Stack) -> np.ndarray:
    flat = stack.values.reshape(-1, stack.values.shape[-1])
    out = np.full(flat.shape[0], np.nan, dtype="float32")
    ok = stack.valid.ravel()
    out[ok] = model.predict_proba(flat[ok])[:, 1]
    return out.reshape(stack.grid.shape)


def proximity_map(stack: Stack, sites: list[Site], sigma_km: float = 8.0) -> np.ndarray:
    """Same kernel as the placeholder in app/scoring.py (type and commodity weights aside)."""
    dens = np.zeros(stack.grid.shape)
    for s in sites:
        d = distance_km(stack, s.lat, s.lon)
        dens += np.exp(-(d**2) / (2 * sigma_km**2))
    out = 1 - np.exp(-dens)
    return np.where(stack.valid, out, np.nan)


def site_rank(score: np.ndarray, stack: Stack, site: Site) -> float:
    d = distance_km(stack, site.lat, site.lon)
    cells = (d <= POSITIVE_KM) & stack.valid
    if not cells.any():
        return float("nan")
    value = float(np.nanmean(score[cells]))
    area = score[stack.valid]
    return float(np.mean(area > value))


def backtest(
    stack: Stack, sites: list[Site], seed: int = 0, background: int = BACKGROUND_CELLS, max_iter: int = 200
) -> list[SiteResult]:
    rng = np.random.default_rng(seed)
    results = []
    for held in sites:
        rest = [s for s in sites if s is not held]
        exclude = distance_km(stack, held.lat, held.lon) <= EXCLUDE_KM
        X, y = training_set(stack, rest, exclude, rng, background)
        model = make_model(seed, max_iter).fit(X, y)
        results.append(
            SiteResult(
                site=held,
                model_rank=site_rank(predict_map(model, stack), stack, held),
                proximity_rank=site_rank(proximity_map(stack, rest), stack, held),
            )
        )
    return results


def hit_rate(ranks: list[float], top: float = TOP_SHARE) -> float:
    ranks = [r for r in ranks if not math.isnan(r)]
    return sum(r <= top for r in ranks) / len(ranks) if ranks else float("nan")


def feature_importance(model, X: np.ndarray, y: np.ndarray, names: list[str], seed: int = 0, top: int = 12):
    """Permutation importance on the training set: a rough guide to what the model leans on."""
    from sklearn.inspection import permutation_importance

    r = permutation_importance(model, X, y, n_repeats=3, random_state=seed, scoring="roc_auc")
    order = np.argsort(r.importances_mean)[::-1][:top]
    return [(names[i], float(r.importances_mean[i])) for i in order]
