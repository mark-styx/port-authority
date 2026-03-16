"""Tests for the port-authority HTTP API."""

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from port_authority import db
from port_authority.server import app


@pytest.fixture(autouse=True)
def _use_temp_db(monkeypatch):
    """Use a temporary database for each test."""
    tmpdir = tempfile.mkdtemp()
    path = Path(tmpdir) / "test.db"
    conn = db.get_connection(path)

    import port_authority.server as srv
    monkeypatch.setattr(srv, "_conn", conn)

    yield
    conn.close()


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_assign_port(client):
    resp = client.post("/assign", json={"project": "web-app"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["project"] == "web-app"
    assert data["port"] == 8000


def test_assign_idempotent(client):
    resp1 = client.post("/assign", json={"project": "web-app"})
    resp2 = client.post("/assign", json={"project": "web-app"})
    assert resp1.json()["port"] == resp2.json()["port"]


def test_assign_preferred_port(client):
    resp = client.post("/assign", json={"project": "api", "preferred_port": 9090})
    assert resp.json()["port"] == 9090


def test_assign_port_conflict(client):
    client.post("/assign", json={"project": "first", "preferred_port": 9090})
    resp = client.post("/assign", json={"project": "second", "preferred_port": 9090})
    assert resp.status_code == 409


def test_release_port(client):
    client.post("/assign", json={"project": "temp"})
    resp = client.delete("/release/temp")
    assert resp.status_code == 200


def test_release_not_found(client):
    resp = client.delete("/release/ghost")
    assert resp.status_code == 404


def test_list_assignments(client):
    client.post("/assign", json={"project": "a"})
    client.post("/assign", json={"project": "b"})
    resp = client.get("/assignments")
    assert len(resp.json()) == 2


def test_lookup_project(client):
    client.post("/assign", json={"project": "web-app"})
    resp = client.get("/lookup/web-app")
    assert resp.status_code == 200
    assert resp.json()["project"] == "web-app"


def test_lookup_not_found(client):
    resp = client.get("/lookup/ghost")
    assert resp.status_code == 404


def test_lookup_by_port(client):
    client.post("/assign", json={"project": "web-app", "preferred_port": 8080})
    resp = client.get("/port/8080")
    assert resp.status_code == 200
    assert resp.json()["project"] == "web-app"


def test_next_available(client):
    resp = client.get("/next-available")
    assert resp.status_code == 200
    assert resp.json()["port"] == 8000


def test_port_range(client):
    resp = client.get("/range")
    assert resp.json()["port_min"] == 8000

    resp = client.put("/range", json={"port_min": 3000, "port_max": 4000})
    assert resp.status_code == 200

    resp = client.get("/range")
    assert resp.json()["port_min"] == 3000


def test_port_range_validation(client):
    resp = client.put("/range", json={"port_min": 5000, "port_max": 3000})
    assert resp.status_code == 400


def test_lan_exposed(client):
    resp = client.post("/assign", json={"project": "home-server", "lan_exposed": True})
    assert resp.json()["lan_exposed"] is True
