"""SQLite persistence layer for port assignments."""

import sqlite3
import time
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path.home() / ".config" / "port-authority" / "ports.db"
DEFAULT_PORT_MIN = 8000
DEFAULT_PORT_MAX = 9999


def get_db_path() -> Path:
    return DEFAULT_DB_PATH


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
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


def find_next_available_port(conn: sqlite3.Connection) -> Optional[int]:
    port_min, port_max = get_port_range(conn)
    used = {
        row["port"]
        for row in conn.execute("SELECT port FROM assignments").fetchall()
    }
    for port in range(port_min, port_max + 1):
        if port not in used:
            return port
    return None


def assign_port(
    conn: sqlite3.Connection,
    project: str,
    allocation_type: str = "persistent",
    lan_exposed: bool = False,
    description: str = "",
    preferred_port: Optional[int] = None,
) -> dict:
    """Assign a port to a project. Returns existing assignment if project already has one."""
    now = time.time()

    # Check if project already has an assignment
    existing = conn.execute(
        "SELECT * FROM assignments WHERE project = ?", (project,)
    ).fetchone()
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
        port = preferred_port
    else:
        port = find_next_available_port(conn)
        if port is None:
            raise NoPortAvailableError("No ports available in configured range")

    conn.execute(
        """INSERT INTO assignments (project, port, allocation_type, lan_exposed, description, created_at, last_seen_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (project, port, allocation_type, int(lan_exposed), description, now, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM assignments WHERE project = ?", (project,)
    ).fetchone()
    return dict(row)


def release_port(conn: sqlite3.Connection, project: str) -> bool:
    cursor = conn.execute("DELETE FROM assignments WHERE project = ?", (project,))
    conn.commit()
    return cursor.rowcount > 0


def list_assignments(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM assignments ORDER BY port ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_assignment(conn: sqlite3.Connection, project: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM assignments WHERE project = ?", (project,)
    ).fetchone()
    return dict(row) if row else None


def get_assignment_by_port(conn: sqlite3.Connection, port: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM assignments WHERE port = ?", (port,)
    ).fetchone()
    return dict(row) if row else None


class PortConflictError(Exception):
    pass


class NoPortAvailableError(Exception):
    pass
