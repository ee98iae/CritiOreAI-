from app.auth import hash_password, verify_password
from tests.conftest import CLIENT, TEAM


def test_password_hash_round_trip():
    h = hash_password("correct horse")
    assert verify_password("correct horse", h)
    assert not verify_password("wrong horse", h)
    assert not verify_password("anything", "not-a-hash")


def test_api_needs_login(client):
    assert client.get("/api/regions").status_code == 401
    assert client.get("/api/regions", headers={"Authorization": "Bearer junk"}).status_code == 401
    assert client.get("/api/health").status_code == 200


def test_login_rejects_bad_password(client):
    r = client.post("/api/auth/login", json={"email": TEAM[0], "password": "nope"})
    assert r.status_code == 401


def test_login_is_case_insensitive_on_email(client):
    r = client.post("/api/auth/login", json={"email": TEAM[0].upper(), "password": TEAM[1]})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "team"


def test_me(client, team):
    assert client.get("/api/auth/me", headers=team).json()["email"] == TEAM[0]


def test_client_only_sees_own_regions(client, client_user):
    assert client.get("/api/regions", headers=client_user).json() == []
    assert client.get("/api/targets", headers=client_user).status_code == 403
    assert client.get("/api/layers", headers=client_user).status_code == 403
    assert client.get("/api/occurrences", headers=client_user).json()["features"] == []
    assert client.get("/api/auth/me", headers=client_user).json()["email"] == CLIENT[0]
