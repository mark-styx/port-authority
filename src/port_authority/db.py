"""SQLite persistence layer for port assignments."""

import sqlite3
import time
from pathlib import Path

from port_authority import scanner

DEFAULT_DB_PATH = Path.home() / ".config" / "port-authority" / "ports.db"
DEFAULT_PORT_MIN = 8000
DEFAULT_PORT_MAX = 9999
DEFAULT_HOLD_TTL = 3600  # seconds a hold survives after its port was last seen in use


def get_db_path() -> Path:
    return DEFAULT_DB_PATH


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            port INTEGER NOT NULL UNIQUE,
            allocation_type TEXT NOT NULL CHECK(allocation_type IN ('persistent', 'ephemeral')),
            lan_exposed INTEGER NOT NULL DEFAULT 0,
            description TEXT DEFAULT '',
            created_at REAL NOT NULL,
            last_seen_at REAL NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_project_unique
            ON assignments(project);

        CREATE TABLE IF NOT EXISTS holds (
            port INTEGER PRIMARY KEY,
            process TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            last_seen_at REAL NOT NULL,
            expires_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()


def get_config(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_config(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_port_range(conn: sqlite3.Connection) -> tuple[int, int]:
    port_min = int(get_config(conn, "port_min", str(DEFAULT_PORT_MIN)))
    port_max = int(get_config(conn, "port_max", str(DEFAULT_PORT_MAX)))
    return port_min, port_max


def set_port_range(conn: sqlite3.Connection, port_min: int, port_max: int) -> None:
    set_config(conn, "port_min", str(port_min))
    set_config(conn, "port_max", str(port_max))


def get_hold_ttl(conn: sqlite3.Connection) -> int:
    return int(get_config(conn, "hold_ttl", str(DEFAULT_HOLD_TTL)))


def set_hold_ttl(conn: sqlite3.Connection, ttl: int) -> None:
    set_config(conn, "hold_ttl", str(ttl))


def hold_port(conn: sqlite3.Connection, port: int, process: str = "") -> dict:
    """Place (or refresh) a temporary hold on a port that is in use outside port-authority."""
    now = time.time()
    expires = now + get_hold_ttl(conn)
    conn.execute(
        """INSERT INTO holds (port, process, created_at, last_seen_at, expires_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(port) DO UPDATE SET
               process = CASE WHEN excluded.process != '' THEN excluded.process ELSE process END,
               last_seen_at = excluded.last_seen_at,
               expires_at = excluded.expires_at""",
        (port, process, now, now, expires),
    )
    conn.commit()
    return dict(conn.execute("SELECT * FROM holds WHERE port = ?", (port,)).fetchone())


def _hold_in_use_port(conn: sqlite3.Connection, port: int) -> dict:
    """Hold a port just found in use, naming the owning process where possible."""
    process = scanner.listening_ports(port, port).get(port, "")
    return hold_port(conn, port, process)


def purge_expired_holds(conn: sqlite3.Connection) -> int:
    cursor = conn.execute("DELETE FROM holds WHERE expires_at <= ?", (time.time(),))
    conn.commit()
    return cursor.rowcount


def list_holds(conn: sqlite3.Connection) -> list[dict]:
    purge_expired_holds(conn)
    rows = conn.execute("SELECT * FROM holds ORDER BY port ASC").fetchall()
    return [dict(r) for r in rows]


def get_hold(conn: sqlite3.Connection, port: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM holds WHERE port = ? AND expires_at > ?", (port, time.time())
    ).fetchone()
    return dict(row) if row else None


def release_hold(conn: sqlite3.Connection, port: int) -> bool:
    cursor = conn.execute("DELETE FROM holds WHERE port = ?", (port,))
    conn.commit()
    return cursor.rowcount > 0


def scan_ports(conn: sqlite3.Connection) -> list[dict]:
    """Scan the managed range for ports in use and hold any that aren't assigned.

    Returns one entry per in-use port: ``{"port", "status", "project", "process"}``
    where status is ``"assigned"`` (in use by its registered project) or ``"held"``.
    """
    purge_expired_holds(conn)
    port_min, port_max = get_port_range(conn)
    in_use = scanner.listening_ports(port_min, port_max)
    assigned = {
        row["port"]: row["project"]
        for row in conn.execute("SELECT port, project FROM assignments").fetchall()
    }
    results = []
    for port in sorted(in_use):
        if port in assigned:
            results.append(
                {
                    "port": port,
                    "status": "assigned",
                    "project": assigned[port],
                    "process": in_use[port],
                }
            )
        else:
            hold = hold_port(conn, port, in_use[port])
            results.append(
                {"port": port, "status": "held", "project": None, "process": hold["process"]}
            )
    return results


def find_next_available_port(conn: sqlite3.Connection) -> int | None:
    """Return the lowest port that is unassigned, unheld and actually free.

    Candidates found to be in use by some other process are held as a side effect.
    """
    port_min, port_max = get_port_range(conn)
    purge_expired_holds(conn)
    used = {
        row["port"]
        for row in conn.execute(
            "SELECT port FROM assignments UNION SELECT port FROM holds"
        ).fetchall()
    }
    for port in range(port_min, port_max + 1):
        if port in used:
            continue
        if scanner.is_port_in_use(port):
            _hold_in_use_port(conn, port)
            continue
        return port
    return None


def assign_port(
    conn: sqlite3.Connection,
    project: str,
    allocation_type: str = "persistent",
    lan_exposed: bool = False,
    description: str = "",
    preferred_port: int | None = None,
) -> dict:
    """Assign a port to a project. Returns existing assignment if project already has one."""
    now = time.time()

    # Check if project already has an assignment
    existing = conn.execute("SELECT * FROM assignments WHERE project = ?", (project,)).fetchone()
    if existing:
        conn.execute(
            "UPDATE assignments SET last_seen_at = ? WHERE project = ?",
            (now, project),
        )
        conn.commit()
        return dict(existing)

    # Try preferred port first
    if preferred_port is not None:
        conflict = conn.execute(
            "SELECT project FROM assignments WHERE port = ?", (preferred_port,)
        ).fetchone()
        if conflict:
            raise PortConflictError(
                f"Port {preferred_port} already assigned to '{conflict['project']}'"
            )
        if scanner.is_port_in_use(preferred_port):
            hold = _hold_in_use_port(conn, preferred_port)
            owner = f" ({hold['process']})" if hold["process"] else ""
            raise PortConflictError(f"Port {preferred_port} is in use by another process{owner}")
        # A hold whose port is free again yields to an explicit request for it
        release_hold(conn, preferred_port)
        port: int = preferred_port
    else:
        next_port = find_next_available_port(conn)
        if next_port is None:
            raise NoPortAvailableError("No ports available in configured range")
        port = next_port

    conn.execute(
        """INSERT INTO assignments (project, port, allocation_type, lan_exposed, description, created_at, last_seen_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (project, port, allocation_type, int(lan_exposed), description, now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM assignments WHERE project = ?", (project,)).fetchone()
    return dict(row)


def release_port(conn: sqlite3.Connection, project: str) -> bool:
    cursor = conn.execute("DELETE FROM assignments WHERE project = ?", (project,))
    conn.commit()
    return cursor.rowcount > 0


def list_assignments(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM assignments ORDER BY port ASC").fetchall()
    return [dict(r) for r in rows]


def get_assignment(conn: sqlite3.Connection, project: str) -> dict | None:
    row = conn.execute("SELECT * FROM assignments WHERE project = ?", (project,)).fetchone()
    return dict(row) if row else None


def get_assignment_by_port(conn: sqlite3.Connection, port: int) -> dict | None:
    row = conn.execute("SELECT * FROM assignments WHERE port = ?", (port,)).fetchone()
    return dict(row) if row else None


class PortConflictError(Exception):
    pass


class NoPortAvailableError(Exception):
    pass
