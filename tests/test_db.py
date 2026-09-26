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


def test_assign_skips_port_in_use(conn, in_use):
    in_use[8000] = "nginx (pid 1)"
    row = db.assign_port(conn, "my-app")
    assert row["port"] == 8001
    hold = db.get_hold(conn, 8000)
    assert hold is not None
    assert hold["process"] == "nginx (pid 1)"


def test_next_available_skips_held_port(conn, in_use):
    in_use[8000] = ""
    db.scan_ports(conn)
    del in_use[8000]  # process went away, but the hold is still active
    assert db.find_next_available_port(conn) == 8001


def test_preferred_port_in_use_conflicts(conn, in_use):
    in_use[9090] = "node (pid 42)"
    with pytest.raises(db.PortConflictError, match="node"):
        db.assign_port(conn, "api", preferred_port=9090)
    assert db.get_hold(conn, 9090) is not None


def test_preferred_port_claims_stale_hold(conn):
    db.hold_port(conn, 9090)
    row = db.assign_port(conn, "api", preferred_port=9090)
    assert row["port"] == 9090
    assert db.get_hold(conn, 9090) is None


def test_scan_holds_unassigned_ports(conn, in_use):
    db.assign_port(conn, "web")  # 8000
    in_use[8000] = "python (pid 5)"
    in_use[8500] = "redis (pid 6)"
    in_use[12345] = "outside range"
    results = db.scan_ports(conn)
    assert results == [
        {"port": 8000, "status": "assigned", "project": "web", "process": "python (pid 5)"},
        {"port": 8500, "status": "held", "project": None, "process": "redis (pid 6)"},
    ]
    assert [h["port"] for h in db.list_holds(conn)] == [8500]


def test_scan_refresh_keeps_known_process_name(conn, in_use):
    in_use[8500] = "redis (pid 6)"
    db.scan_ports(conn)
    in_use[8500] = ""  # later probe couldn't identify the owner
    db.scan_ports(conn)
    assert db.get_hold(conn, 8500)["process"] == "redis (pid 6)"


def test_holds_expire(conn):
    db.set_hold_ttl(conn, 60)
    db.hold_port(conn, 8000)
    conn.execute("UPDATE holds SET expires_at = 0")
    conn.commit()
    assert db.get_hold(conn, 8000) is None
    assert db.list_holds(conn) == []
    assert db.find_next_available_port(conn) == 8000


def test_release_hold(conn):
    db.hold_port(conn, 8000)
    assert db.release_hold(conn, 8000) is True
    assert db.release_hold(conn, 8000) is False
