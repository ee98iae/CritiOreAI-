import json
import os

import numpy as np
import pytest

from app.data import DEMO_PATH

# Must be set before the app reads them.
os.environ.setdefault("CRITIORE_SECRET", "test-secret")
# The API tests assert on the synthetic demo set, which has known Ni/Co/Cu sites.
# test_real_data.py checks the real default file separately.
os.environ["CRITIORE_OCCURRENCES"] = str(DEMO_PATH)

TEAM = ("team@critiore.test", "team-password-1")
CLIENT = ("client@miner.test", "client-password-1")


@pytest.fixture(autouse=True, scope="session")
def accounts(tmp_path_factory):
    from app.auth import hash_password

    path = tmp_path_factory.mktemp("auth") / "users.json"
    path.write_text(json.dumps([
        {"email": TEAM[0], "name": "Team", "role": "team", "regions": ["*"], "password_hash": hash_password(TEAM[1])},
        {"email": CLIENT[0], "name": "Client", "role": "client", "regions": ["nowhere"],
         "password_hash": hash_password(CLIENT[1])},
    ]))
    os.environ["CRITIORE_USERS_FILE"] = str(path)
    yield path


@pytest.fixture(scope="session")
def layers_dir(tmp_path_factory):
    """A tiny built region: one float layer and one RGB layer over the pilot bbox."""
    from pipeline.grid import Grid
    from pipeline.output import Layer, save_layer, write_manifest

    out = tmp_path_factory.mktemp("layers")
    grid = Grid((48.8, 90.6, 50.4, 92.8), 0.02)
    ramp = np.tile(np.linspace(0, 10, grid.width, dtype="float32"), (grid.height, 1))
    ramp[:5, :5] = np.nan
    rgb = np.full((3, *grid.shape), 120, dtype="uint8")
    region_dir = out / "kharkhiraa"
    layers = [
        save_layer(region_dir, Layer("ramp", "Ramp", "Terrain", "test", "test", colormap="viridis"), ramp, grid),
        save_layer(region_dir, Layer("rgb", "RGB", "Imagery", "test", "test", kind="rgb", colormap=None), rgb, grid),
    ]
    write_manifest(region_dir, "kharkhiraa", grid, layers, {"built_at": "test"})
    os.environ["CRITIORE_LAYERS_DIR"] = str(out)
    return out


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _login(client, who):
    r = client.post("/api/auth/login", json={"email": who[0], "password": who[1]})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def team(client):
    return _login(client, TEAM)


@pytest.fixture(scope="session")
def client_user(client):
    return _login(client, CLIENT)
