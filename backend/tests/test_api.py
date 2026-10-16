from app.data import load_occurrences
from app.scoring import haversine_km, score_point


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["occurrences"] > 0


def test_occurrences_filter_by_commodity(client, team):
    feats = client.get("/api/occurrences", params={"commodity": "Ni"}, headers=team).json()["features"]
    assert feats
    assert all("Ni" in f["properties"]["commodities"] for f in feats)


def test_occurrences_bad_bbox(client, team):
    assert client.get("/api/occurrences", params={"bbox": "1,2,3"}, headers=team).status_code == 422


def test_occurrence_not_found(client, team):
    assert client.get("/api/occurrences/NOPE", headers=team).status_code == 404


def test_score_is_higher_on_a_known_site_than_far_away(client, team):
    occ = next(o for o in load_occurrences() if "Cu" in o.commodities and o.type == "deposit")
    near = client.post("/api/prospectivity/score", json={"lat": occ.lat, "lon": occ.lon, "commodity": "Cu"}, headers=team).json()
    far = client.post("/api/prospectivity/score", json={"lat": 10.0, "lon": 10.0, "commodity": "Cu"}, headers=team).json()
    assert near["score"] > 0.3
    assert far["score"] == 0
    assert far["confidence"] == "low"
    assert near["evidence"][0]["distance_km"] < 1


def test_score_rejects_unknown_commodity(client, team):
    r = client.post("/api/prospectivity/score", json={"lat": 49.5, "lon": 91.5, "commodity": "Xx"}, headers=team)
    assert r.status_code == 422


def test_grid_and_targets(client, team):
    grid = client.get("/api/prospectivity/grid", params={"commodity": "Cu", "cell_deg": 0.1}, headers=team).json()
    assert grid["features"]
    targets = client.get("/api/targets", params={"commodity": "Cu", "limit": 5}, headers=team).json()["targets"]
    assert len(targets) == 5
    scores = [t["score"] for t in targets]
    assert scores == sorted(scores, reverse=True)
    for a in targets:
        for b in targets:
            if a is not b:
                assert haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) >= 10


def test_unknown_region(client, team):
    assert client.get("/api/targets", params={"region": "mars"}, headers=team).status_code == 404


def test_related_commodity_counts_half():
    occ = next(o for o in load_occurrences() if o.commodities == ("Ni",))
    direct = score_point(occ.lat, occ.lon, "Ni", (occ,))
    related = score_point(occ.lat, occ.lon, "Co", (occ,))
    assert 0 < related.score < direct.score


def test_pilot_region_commodities():
    region = client.get("/api/regions").json()[0]
    assert region["commodities"] == ["Cu", "W", "Au", "Mo"]


def test_tungsten_targets():
    body = client.get("/api/targets", params={"commodity": "W", "limit": 3})
    assert body.status_code == 200
    assert body.json()["targets"]
