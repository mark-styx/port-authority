"""Tests for the port-authority database layer."""

import tempfile
from pathlib import Path

import pytest

from port_authority import db


@pytest.fixture
def conn():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.db"
        connection = db.get_connection(path)
        yield connection
        connection.close()


def test_assign_persistent_port(conn):
    row = db.assign_port(conn, "my-app", "persistent")
    assert row["project"] == "my-app"
    assert row["port"] == 8000  # first in default range
    assert row["allocation_type"] == "persistent"


def test_assign_returns_existing(conn):
    first = db.assign_port(conn, "my-app", "persistent")
    second = db.assign_port(conn, "my-app", "persistent")
    assert first["port"] == second["port"]


def test_assign_sequential_ports(conn):
    a = db.assign_port(conn, "app-a")
    b = db.assign_port(conn, "app-b")
    assert a["port"] == 8000
    assert b["port"] == 8001


def test_assign_preferred_port(conn):
    row = db.assign_port(conn, "special-app", preferred_port=9090)
    assert row["port"] == 9090


def test_assign_preferred_port_conflict(conn):
    db.assign_port(conn, "first", preferred_port=9090)
    with pytest.raises(db.PortConflictError):
        db.assign_port(conn, "second", preferred_port=9090)


def test_release_port(conn):
    db.assign_port(conn, "temp-app", "ephemeral")
    assert db.release_port(conn, "temp-app") is True
    assert db.get_assignment(conn, "temp-app") is None


def test_release_nonexistent(conn):
    assert db.release_port(conn, "ghost") is False


def test_list_assignments(conn):
    db.assign_port(conn, "app-a")
    db.assign_port(conn, "app-b")
    assignments = db.list_assignments(conn)
    assert len(assignments) == 2
    assert assignments[0]["port"] < assignments[1]["port"]


def test_lan_exposed_flag(conn):
    row = db.assign_port(conn, "lan-app", lan_exposed=True)
    assert row["lan_exposed"] == 1


def test_get_assignment_by_port(conn):
    db.assign_port(conn, "my-app", preferred_port=8080)
    row = db.get_assignment_by_port(conn, 8080)
    assert row["project"] == "my-app"


def test_get_assignment_by_port_not_found(conn):
    assert db.get_assignment_by_port(conn, 9999) is None


def test_port_range_config(conn):
    db.set_port_range(conn, 3000, 4000)
    port_min, port_max = db.get_port_range(conn)
    assert port_min == 3000
    assert port_max == 4000
    row = db.assign_port(conn, "range-app")
    assert row["port"] == 3000


def test_find_next_available_fills_gaps(conn):
    db.assign_port(conn, "app-a")  # 8000
    db.assign_port(conn, "app-b")  # 8001
    db.release_port(conn, "app-a")
    port = db.find_next_available_port(conn)
    assert port == 8000  # reuses freed port


def test_no_ports_available(conn):
    db.set_port_range(conn, 9000, 9001)
    db.assign_port(conn, "a")
    db.assign_port(conn, "b")
    with pytest.raises(db.NoPortAvailableError):
        db.assign_port(conn, "c")


def test_description_stored(conn):
    row = db.assign_port(conn, "my-app", description="Main web server")
    assert row["description"] == "Main web server"
