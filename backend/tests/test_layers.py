def test_layers_manifest(client, team, layers_dir):
    body = client.get("/api/layers", headers=team).json()
    assert body["built"] is True
    ids = [l["id"] for l in body["layers"]]
    assert ids == ["ramp", "rgb"]
    ramp = body["layers"][0]
    assert "file" not in ramp
    assert len(ramp["legend"]) == 6 and ramp["legend"][0].startswith("#")
    lo, hi = ramp["rescale"]
    assert 0 <= lo < hi <= 10


def test_tile_inside_region_is_png(client, team, layers_dir):
    # z7 tile over the Kharkhiraa pilot area
    for layer in ("ramp", "rgb"):
        r = client.get(f"/api/layers/kharkhiraa/{layer}/tiles/7/96/41.png", headers=team)
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_tile_outside_region_is_empty_png(client, team, layers_dir):
    r = client.get("/api/layers/kharkhiraa/ramp/tiles/7/0/0.png", headers=team)
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_unknown_layer_and_region(client, team, layers_dir):
    assert client.get("/api/layers/kharkhiraa/nope/tiles/7/96/41.png", headers=team).status_code == 404
    assert client.get("/api/layers/mars/ramp/tiles/7/96/41.png", headers=team).status_code == 404


def test_tiles_need_login(client, layers_dir):
    assert client.get("/api/layers/kharkhiraa/ramp/tiles/7/96/41.png").status_code == 401


def test_point_values(client, team, layers_dir):
    # The ramp runs 0 -> 10 west to east, so the middle of the region is about 5.
    body = client.get("/api/layers/kharkhiraa/values", params={"lat": 49.6, "lon": 91.7}, headers=team).json()
    assert abs(body["values"]["ramp"] - 5) < 0.3
    assert "rgb" not in body["values"]
    corner = client.get("/api/layers/kharkhiraa/values", params={"lat": 50.39, "lon": 90.61}, headers=team).json()
    assert corner["values"]["ramp"] is None
    outside = client.get("/api/layers/kharkhiraa/values", params={"lat": 10, "lon": 10}, headers=team).json()
    assert outside["values"]["ramp"] is None
