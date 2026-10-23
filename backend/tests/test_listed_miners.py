from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Rough bounding box of Mongolia: south, west, north, east.
MONGOLIA = (41.5, 87.7, 52.2, 120.0)
STATUSES = {"producing", "development", "exploration", "standby", "unverified"}


def test_every_site_is_in_mongolia_and_sourced():
    feats = client.get("/api/listed-miners").json()["features"]
    assert len(feats) >= 20
    assert len({f["properties"]["id"] for f in feats}) == len(feats)
    s, w, n, e = MONGOLIA
    for f in feats:
        lon, lat = f["geometry"]["coordinates"]
        p = f["properties"]
        assert s <= lat <= n and w <= lon <= e, p["id"]
        assert p["status"] in STATUSES, p["id"]
        assert p["precision"] in {"exact", "approximate"}, p["id"]
        assert p["companies"] and all(c["tickers"] for c in p["companies"]), p["id"]
        assert p["sources"] and all(u.startswith("https://") for u in p["sources"]), p["id"]


def test_filter_by_status():
    feats = client.get("/api/listed-miners", params={"status": "producing"}).json()["features"]
    assert feats
    assert all(f["properties"]["status"] == "producing" for f in feats)
    assert "oyu-tolgoi" in {f["properties"]["id"] for f in feats}
