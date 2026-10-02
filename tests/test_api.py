import sqlite3

import pytest

from app.db import MIGRATIONS
from app.server import create_app

MATTER = {
    "name": "Kitchen light",
    "protocol": "matter",
    "qr_payload": "MT:Y.K9042C00KA0648G00",
    "manual_code": "3497-011-2332",
    "serial_number": "SN123",
    "location": "Kitchen",
}


@pytest.fixture
def client(tmp_path):
    app = create_app(str(tmp_path))
    app.testing = True
    return app.test_client()


def test_crud_roundtrip(client):
    res = client.post("/api/devices", json=MATTER)
    assert res.status_code == 201
    dev = res.get_json()
    assert dev["id"] and dev["uuid"] and dev["created_at"]
    assert dev["qr_payload"] == MATTER["qr_payload"]

    res = client.put(f"/api/devices/{dev['id']}", json={"location": "  Pantry  ", "notes": "line 1\nline 2"})
    assert res.status_code == 200
    updated = res.get_json()
    assert updated["location"] == "Pantry"
    assert updated["notes"] == "line 1\nline 2"
    assert updated["name"] == "Kitchen light"

    assert [d["id"] for d in client.get("/api/devices").get_json()] == [dev["id"]]
    assert client.delete(f"/api/devices/{dev['id']}").status_code == 204
    assert client.get(f"/api/devices/{dev['id']}").status_code == 404
    assert client.delete(f"/api/devices/{dev['id']}").status_code == 404


def test_search(client):
    client.post("/api/devices", json=MATTER)
    client.post("/api/devices", json={"name": "Front door lock", "protocol": "zwave",
                                      "dsk": "34028-23669-20938-46346-33746-07431-56821-14553"})
    assert [d["name"] for d in client.get("/api/devices?q=sn123").get_json()] == ["Kitchen light"]
    assert [d["name"] for d in client.get("/api/devices?q=34028").get_json()] == ["Front door lock"]
    assert len(client.get("/api/devices").get_json()) == 2


@pytest.mark.parametrize("body, field", [
    ({"protocol": "matter"}, "name"),
    ({"name": "x", "protocol": "zigbee"}, "protocol"),
    ({"name": "x", "protocol": "matter", "notes": 5}, "notes"),
])
def test_validation(client, body, field):
    res = client.post("/api/devices", json=body)
    assert res.status_code == 400
    assert field in res.get_json()["fields"]


def test_rejects_non_object_body(client):
    assert client.post("/api/devices", json=[1]).status_code == 400


def test_cannot_overwrite_managed_fields(client):
    dev = client.post("/api/devices", json=MATTER).get_json()
    res = client.put(f"/api/devices/{dev['id']}", json={"uuid": "x", "id": 99, "created_at": "y"})
    after = res.get_json()
    assert (after["id"], after["uuid"], after["created_at"]) == (dev["id"], dev["uuid"], dev["created_at"])


def test_ui_served(client):
    res = client.get("/")
    assert res.status_code == 200 and b"Pairing Vault" in res.data
    assert client.get("/static/app.js").status_code == 200
    for lib in ("jsQR.min.js", "qrcode.min.js"):
        assert client.get(f"/static/vendor/{lib}").status_code == 200


def test_insteon_id_normalised(client):
    dev = client.post("/api/devices", json={"name": "Modem", "protocol": "insteon", "insteon_id": "1a2b3c"}).get_json()
    assert dev["protocol"] == "insteon" and dev["insteon_id"] == "1A.2B.3C"
    assert [d["name"] for d in client.get("/api/devices?q=2b.3c").get_json()] == ["Modem"]


def test_migrates_v1_database(tmp_path):
    # A database created by 0.1/0.2 (schema version 1) keeps its rows and gains Insteon.
    conn = sqlite3.connect(tmp_path / "pairing_vault.db")
    for sql in MIGRATIONS[0]:
        conn.execute(sql)
    conn.execute("PRAGMA user_version = 1")
    conn.execute("INSERT INTO devices (uuid, name, protocol, created_at, updated_at) "
                 "VALUES ('u1', 'Old', 'zwave', 't', 't')")
    conn.commit()
    conn.close()
    client = create_app(str(tmp_path)).test_client()
    assert [(d["name"], d["insteon_id"]) for d in client.get("/api/devices").get_json()] == [("Old", "")]
    assert client.post("/api/devices", json={"name": "Hub", "protocol": "insteon"}).status_code == 201


def test_ingress_only(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOWED_CLIENTS", "172.30.32.2")
    client = create_app(str(tmp_path)).test_client()
    assert client.get("/api/devices", environ_base={"REMOTE_ADDR": "172.30.33.5"}).status_code == 403
    assert client.get("/api/devices", environ_base={"REMOTE_ADDR": "172.30.32.2"}).status_code == 200


def test_schema_version_and_persistence(tmp_path):
    client = create_app(str(tmp_path)).test_client()
    client.post("/api/devices", json=MATTER)
    # Reopening runs migrations again without touching existing data.
    client = create_app(str(tmp_path)).test_client()
    assert len(client.get("/api/devices").get_json()) == 1
    version = sqlite3.connect(tmp_path / "pairing_vault.db").execute("PRAGMA user_version").fetchone()[0]
    assert version == len(MIGRATIONS)


def test_security_headers(client):
    res = client.get("/")
    assert "frame-ancestors 'self'" in res.headers["Content-Security-Policy"]
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert client.get("/api/devices").headers["Referrer-Policy"] == "no-referrer"


def test_cross_site_writes_rejected(client):
    cross = {"Sec-Fetch-Site": "cross-site"}
    assert client.post("/api/devices", json=MATTER, headers=cross).status_code == 403
    assert client.get("/api/devices", headers=cross).status_code == 200
    same = {"Sec-Fetch-Site": "same-origin"}
    assert client.post("/api/devices", json=MATTER, headers=same).status_code == 201


def test_form_posts_rejected(client):
    # Cross-site HTML forms can't send JSON, so they get a validation error.
    res = client.post("/api/devices", data={"name": "x", "protocol": "other"})
    assert res.status_code == 400


def test_large_body_rejected(client):
    res = client.post("/api/devices", json={**MATTER, "notes": "x" * 300_000})
    assert res.status_code == 413
