"""HTTP API server for port-authority."""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from port_authority import db

_conn = None

# Seconds between background scans of the managed range; 0 disables. Set by `pa serve`.
scan_interval = 60

log = logging.getLogger("port_authority")


def get_conn():
    global _conn
    if _conn is None:
        _conn = db.get_connection()
    return _conn


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _conn
    _conn = db.get_connection()
    task = asyncio.create_task(_scan_loop()) if scan_interval > 0 else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    if _conn:
        _conn.close()
        _conn = None


# Seconds between background scans of the managed range; 0 disables. Set by `pa serve`.
scan_interval = 60

log = logging.getLogger("port_authority")


async def _scan_loop():
    while True:
        try:
            await asyncio.to_thread(db.scan_ports, get_conn())
        except Exception:
            log.exception("Port scan failed")
        await asyncio.sleep(scan_interval)


app = FastAPI(
    title="Port Authority",
    description="Local port assignment manager for development services",
    version="0.1.0",
    lifespan=lifespan,
)


class AssignRequest(BaseModel):
    project: str
    allocation_type: str = "persistent"
    lan_exposed: bool = False
    description: str = ""
    preferred_port: int | None = None


class AssignResponse(BaseModel):
    project: str
    port: int
    allocation_type: str
    lan_exposed: bool
    description: str
    created_at: float
    last_seen_at: float


class HoldResponse(BaseModel):
    port: int
    process: str
    created_at: float
    last_seen_at: float
    expires_at: float


class ScanEntry(BaseModel):
    port: int
    status: str
    project: str | None
    process: str


class HoldTtlRequest(BaseModel):
    hold_ttl: int


class PortRangeRequest(BaseModel):
    port_min: int
    port_max: int


def _row_to_response(row: dict) -> AssignResponse:
    return AssignResponse(
        project=row["project"],
        port=row["port"],
        allocation_type=row["allocation_type"],
        lan_exposed=bool(row["lan_exposed"]),
        description=row["description"],
        created_at=row["created_at"],
        last_seen_at=row["last_seen_at"],
    )


@app.post("/assign", response_model=AssignResponse)
def assign_port(req: AssignRequest):
    """Request a port assignment for a project. Returns existing assignment if one exists."""
    try:
        row = db.assign_port(
            get_conn(),
            project=req.project,
            allocation_type=req.allocation_type,
            lan_exposed=req.lan_exposed,
            description=req.description,
            preferred_port=req.preferred_port,
        )
        return _row_to_response(row)
    except db.PortConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    except db.NoPortAvailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from None


@app.delete("/release/{project}")
def release_port(project: str):
    """Release a project's port assignment."""
    released = db.release_port(get_conn(), project)
    if not released:
        raise HTTPException(status_code=404, detail=f"No assignment found for '{project}'")
    return {"status": "released", "project": project}


@app.get("/assignments", response_model=list[AssignResponse])
def list_assignments():
    """List all current port assignments."""
    rows = db.list_assignments(get_conn())
    return [_row_to_response(r) for r in rows]


@app.get("/lookup/{project}", response_model=AssignResponse)
def lookup_project(project: str):
    """Look up the port assignment for a specific project."""
    row = db.get_assignment(get_conn(), project)
    if not row:
        raise HTTPException(status_code=404, detail=f"No assignment for '{project}'")
    return _row_to_response(row)


@app.get("/port/{port}", response_model=AssignResponse)
def lookup_port(port: int):
    """Check what project is assigned to a specific port."""
    row = db.get_assignment_by_port(get_conn(), port)
    if not row:
        hold = db.get_hold(get_conn(), port)
        if hold:
            owner = f" by {hold['process']}" if hold["process"] else ""
            raise HTTPException(
                status_code=404, detail=f"Port {port} is not assigned (held: in use{owner})"
            )
        raise HTTPException(status_code=404, detail=f"Port {port} is not assigned")
    return _row_to_response(row)


@app.get("/next-available")
def next_available():
    """Get the next available port without assigning it."""
    port = db.find_next_available_port(get_conn())
    if port is None:
        raise HTTPException(status_code=503, detail="No ports available")
    return {"port": port}


@app.get("/range")
def get_range():
    """Get the configured port range."""
    port_min, port_max = db.get_port_range(get_conn())
    return {"port_min": port_min, "port_max": port_max}


@app.put("/range")
def set_range(req: PortRangeRequest):
    """Update the managed port range."""
    if req.port_min >= req.port_max:
        raise HTTPException(status_code=400, detail="port_min must be less than port_max")
    if req.port_min < 1024:
        raise HTTPException(status_code=400, detail="port_min must be >= 1024 (non-privileged)")
    db.set_port_range(get_conn(), req.port_min, req.port_max)
    return {"port_min": req.port_min, "port_max": req.port_max}


@app.post("/scan", response_model=list[ScanEntry])
def scan():
    """Scan the managed range and hold any in-use ports that aren't assigned."""
    return db.scan_ports(get_conn())


@app.get("/holds", response_model=list[HoldResponse])
def list_holds():
    """List temporary holds on ports found in use outside port-authority."""
    return db.list_holds(get_conn())


@app.delete("/holds/{port}")
def release_hold(port: int):
    """Drop a temporary hold. It will come back on the next scan if the port is still in use."""
    if not db.release_hold(get_conn(), port):
        raise HTTPException(status_code=404, detail=f"No hold on port {port}")
    return {"status": "released", "port": port}


@app.get("/hold-ttl")
def get_hold_ttl():
    """Get how long (seconds) a hold lasts after its port was last seen in use."""
    return {"hold_ttl": db.get_hold_ttl(get_conn())}


@app.put("/hold-ttl")
def set_hold_ttl(req: HoldTtlRequest):
    """Update the hold TTL (seconds)."""
    if req.hold_ttl <= 0:
        raise HTTPException(status_code=400, detail="hold_ttl must be positive")
    db.set_hold_ttl(get_conn(), req.hold_ttl)
    return {"hold_ttl": req.hold_ttl}


@app.get("/health")
def health():
    return {"status": "ok"}
