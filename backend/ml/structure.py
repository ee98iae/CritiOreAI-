"""Structure and rock-type evidence derived from the DEM and Sentinel-2 layers.

Stand-ins until mapped geology and geophysics are available. Porphyry Cu-Mo-Au and
W skarns are controlled by faults and by intrusion contacts, so:

- Lineaments: long, straight valleys in the DEM, which in this terrain mostly follow
  faults and fracture zones. Gives lineament density and distance to the nearest one.
- Rock-type groups: unsupervised clusters of the Sentinel-2 spectra (brightness
  removed), a rough proxy for lithology. Gives the share of each group around a cell
  and the density of contacts between groups (intrusion margins show up here).

Everything is computed on a fine grid (default 0.001 deg, ~70 x 110 m) and averaged
onto the model grid by the caller.
"""

from pathlib import Path

import numpy as np
from scipy import ndimage

FINE_RES = 0.001
LITH_CLASSES = 8
MIN_LINEAMENT_KM = 1.5
MIN_ELONGATION = 3.0


def _read(path: Path, shape):
    import rasterio
    from rasterio.enums import Resampling

    with rasterio.open(path) as src:
        data = src.read(out_shape=(src.count, *shape), resampling=Resampling.average, masked=True)
    return np.ma.filled(data.astype("float32"), np.nan)


def pixel_size_km(lat_deg: float, res: float) -> tuple[float, float]:
    """(dy, dx) of a res-degree pixel in km."""
    return res * 111.32, res * 111.32 * np.cos(np.radians(lat_deg))


def lineaments(dem: np.ndarray, dy_km: float, dx_km: float, seed: int = 0) -> np.ndarray:
    """Boolean mask of lineament pixels: straight, elongated valley segments."""
    filled = np.where(np.isfinite(dem), dem, np.nanmean(dem))
    # Valleys: positive Laplacian of the smoothed surface (concave up).
    lap = ndimage.gaussian_laplace(filled, sigma=2.0)
    # Straightness: coherence of the gradient structure tensor.
    gy, gx = np.gradient(ndimage.gaussian_filter(filled, 1.0), dy_km, dx_km)
    j11 = ndimage.gaussian_filter(gx * gx, 3)
    j22 = ndimage.gaussian_filter(gy * gy, 3)
    j12 = ndimage.gaussian_filter(gx * gy, 3)
    root = np.sqrt((j11 - j22) ** 2 + 4 * j12**2)
    with np.errstate(invalid="ignore", divide="ignore"):
        coherence = np.where(j11 + j22 > 0, root / (j11 + j22), 0.0)
    ok = np.isfinite(dem)
    cand = ok & (lap > np.nanpercentile(lap[ok], 85)) & (coherence > np.nanpercentile(coherence[ok], 50))
    cand = ndimage.binary_opening(cand, iterations=1)

    labels, n = ndimage.label(cand, structure=np.ones((3, 3)))
    if n == 0:
        return cand
    keep = np.zeros(n + 1, bool)
    objs = ndimage.find_objects(labels)
    for i, sl in enumerate(objs, start=1):
        ys, xs = np.nonzero(labels[sl] == i)
        if ys.size < 8:
            continue
        pts = np.column_stack([ys * dy_km, xs * dx_km])
        pts -= pts.mean(0)
        evals = np.linalg.eigvalsh(np.cov(pts.T))
        major = 4 * np.sqrt(max(evals[1], 1e-9))  # ~ full length of a uniform segment
        minor = 4 * np.sqrt(max(evals[0], 1e-9))
        keep[i] = major >= MIN_LINEAMENT_KM and major / max(minor, 1e-6) >= MIN_ELONGATION
    return keep[labels]


def rock_groups(s2: np.ndarray, k: int = LITH_CLASSES, seed: int = 0) -> np.ndarray:
    """Cluster label per pixel (-1 where no data) from brightness-normalised spectra."""
    from sklearn.cluster import MiniBatchKMeans

    bands = s2.reshape(s2.shape[0], -1).T
    ok = np.all(np.isfinite(bands), axis=1) & (bands.sum(1) > 0)
    x = bands[ok]
    total = x.sum(1, keepdims=True)
    feats = np.column_stack([x / total, np.log(total)])
    feats = (feats - feats.mean(0)) / feats.std(0)
    rng = np.random.default_rng(seed)
    sample = feats[rng.choice(len(feats), size=min(200_000, len(feats)), replace=False)]
    km = MiniBatchKMeans(n_clusters=k, random_state=seed, n_init=3, batch_size=4096).fit(sample)
    out = np.full(bands.shape[0], -1, dtype=np.int16)
    out[ok] = km.predict(feats)
    out = out.reshape(s2.shape[1:])
    # Mode filter (3 x 3) to drop speckle before looking for contacts.
    counts = np.stack([ndimage.uniform_filter((out == c).astype("float32"), 3, mode="nearest") for c in range(k)])
    return np.where(out >= 0, counts.argmax(0), -1).astype(np.int16)


def contacts(groups: np.ndarray) -> np.ndarray:
    """Pixels whose right or lower neighbour belongs to a different rock group."""
    c = np.zeros(groups.shape, bool)
    valid = groups >= 0
    dx = (groups[:, 1:] != groups[:, :-1]) & valid[:, 1:] & valid[:, :-1]
    dy = (groups[1:, :] != groups[:-1, :]) & valid[1:, :] & valid[:-1, :]
    c[:, :-1] |= dx
    c[:-1, :] |= dy
    return c


def block_mean(a: np.ndarray, factor: int) -> np.ndarray:
    r, c = a.shape[0] // factor, a.shape[1] // factor
    a = a[: r * factor, : c * factor].reshape(r, factor, c, factor)
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN blocks stay NaN
        return np.nanmean(a, axis=(1, 3))


def structure_layers(layers_dir: Path, model_shape: tuple[int, int], model_res: float, mid_lat: float,
                     fine_res: float = FINE_RES) -> dict[str, np.ndarray]:
    """Structure and rock-type layers on the model grid, keyed by feature name."""
    factor = round(model_res / fine_res)
    fine_shape = (model_shape[0] * factor, model_shape[1] * factor)
    dy, dx = pixel_size_km(mid_lat, fine_res)

    dem = _read(Path(layers_dir) / "elevation.tif", fine_shape)[0]
    lin = lineaments(dem, dy, dx)
    dist = ndimage.distance_transform_edt(~lin, sampling=(dy, dx)).astype("float32")

    s2 = _read(Path(layers_dir) / "sentinel2_reflectance.tif", fine_shape)
    groups = rock_groups(s2)
    cont = contacts(groups)

    nodata = ~np.isfinite(dem)
    out = {
        "lineament_density": block_mean(np.where(nodata, np.nan, lin.astype("float32")), factor),
        "lineament_dist_km": block_mean(np.where(nodata, np.nan, dist), factor),
        "contact_density": block_mean(np.where(groups < 0, np.nan, cont.astype("float32")), factor),
    }
    for k in range(LITH_CLASSES):
        out[f"rock_group_{k}"] = block_mean(np.where(groups < 0, np.nan, (groups == k).astype("float32")), factor)
    return out
