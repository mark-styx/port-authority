# Port Authority

[![CI](https://github.com/mark-styx/port-authority/workflows/CI/badge.svg)](https://github.com/mark-styx/port-authority/actions)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

Local port assignment manager for development services. Prevents port collisions across multiple projects, supports persistent assignments for LAN-exposed services, and ephemeral assignments for temporary testing.

## Install

```bash
pip install port-authority

# With process names in scan results (installs psutil)
pip install port-authority[scan]

# Or with dev dependencies
pip install port-authority[dev]
```

## Quick Start

```bash
# Start the server (optional - CLI works offline too)
pa serve

# Assign a persistent port to a project
pa assign my-web-app --lan -d "Main web dashboard"

# Assign an ephemeral port for testing
pa assign temp-test -t ephemeral

# Look up a project's port
pa lookup my-web-app

# List all assignments
pa ls

# Release a port
pa release temp-test

# Check next available port
pa next

# Find ports already in use by other tools and hold them
pa scan
pa holds
```

## How It Works

- **Persistent assignments**: Same port every time for a given project name. Use for services you access regularly or expose on LAN.
- **Ephemeral assignments**: Temporary ports for testing. Release when done.
- **Idempotent**: Requesting a port for an already-assigned project returns the existing assignment.
- **Offline mode**: CLI falls back to direct SQLite access when the server is not running.
- **Holds on in-use ports**: port-authority won't hand out a port that something else is already listening on (see below).

### Holds: ports in use by other tools

Not every tool asks port-authority for a port. Some hardcode one, and some pick
different ports from run to run. To stay authoritative, port-authority checks
what's actually in use and places a temporary **hold** on any in-use port that
has no assignment:

- **On every allocation**, each candidate port is probed before it's handed out.
  If it's busy, it's held and the next port is tried. A `preferred_port` that is
  busy is rejected with `409` and the owning process named where possible.
- **`pa scan`** (or `POST /scan`) checks the whole managed range at once.
- **`pa serve`** rescans in the background every 60 seconds
  (`--scan-interval N` to change, `0` to disable).

Holds are temporary. Each time a scan sees the port still in use, the hold is
refreshed. It expires once the port has not been seen in use for the hold TTL
(default 1 hour, `PUT /hold-ttl`). This rides out tools that start and stop
without leaving ports locked forever. An explicit `preferred_port` request for a
held port that has since gone free claims the port and drops the hold.

A port that is in use by its own assigned project shows as `assigned` in scan
results and is not held. Process names need `psutil` (`pip install
port-authority[scan]`). Without it, ports are detected by test-binding them and
show as "unknown process".

## API

Server runs on `http://127.0.0.1:7600` by default.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/assign` | Request a port assignment |
| DELETE | `/release/{project}` | Release an assignment |
| GET | `/assignments` | List all assignments |
| GET | `/lookup/{project}` | Look up a project's port |
| GET | `/port/{port}` | Check what's on a port |
| GET | `/next-available` | Peek at next free port (holds any busy ports it skips) |
| POST | `/scan` | Scan the range and hold in-use, unassigned ports |
| GET | `/holds` | List active holds |
| DELETE | `/holds/{port}` | Drop a hold (returns on next scan if still in use) |
| GET | `/hold-ttl` | Get hold TTL in seconds |
| PUT | `/hold-ttl` | Update hold TTL |
| GET | `/range` | Get configured port range |
| PUT | `/range` | Update port range |

### Example: Assign via API

```bash
curl -X POST http://127.0.0.1:7600/assign \
  -H "Content-Type: application/json" \
  -d '{"project": "my-app", "lan_exposed": true}'
```

## Configuration

- **Port range**: Default 8000-9999, configurable via `pa` CLI or API
- **Database**: `~/.config/port-authority/ports.db`
- **Server URL**: Set `PORT_AUTHORITY_URL` env var or use `--server` flag

## Integrating Other Projects

Every project that needs a port should request one from port-authority at startup rather than hardcoding a port number. This prevents collisions when running multiple services simultaneously.

### Design Principles

1. **Use a stable project name** - the same name always returns the same port (idempotent)
2. **Request at startup, not at install** - ports are assigned on first request and remembered
3. **Prefer the HTTP API** when the server is running, fall back to CLI
4. **Release ephemeral ports** when done, leave persistent ones alone

### Shell Scripts / Makefiles

Parse the port number from CLI output or use the API with `jq`:

```bash
# Via CLI (works offline, no server needed)
PORT=$(pa assign my-project | grep -oE 'port [0-9]+' | grep -oE '[0-9]+')

# Via API (requires server running)
PORT=$(curl -sf http://127.0.0.1:7600/assign \
  -H "Content-Type: application/json" \
  -d '{"project": "my-project"}' | jq -r .port)

# Use it
echo "Starting on port $PORT"
exec my-server --port "$PORT"
```

For a Makefile:

```makefile
PORT := $(shell pa assign my-project | grep -oE 'port [0-9]+' | grep -oE '[0-9]+')

serve:
	my-server --port $(PORT)
```

### Python Projects

```python
import httpx

PA_URL = "http://127.0.0.1:7600"

def get_port(project: str, lan_exposed: bool = False) -> int:
    """Request a port from port-authority."""
    resp = httpx.post(f"{PA_URL}/assign", json={
        "project": project,
        "lan_exposed": lan_exposed,
    })
    resp.raise_for_status()
    return resp.json()["port"]

# Usage
port = get_port("my-web-app", lan_exposed=True)
uvicorn.run(app, port=port)
```

If you want CLI fallback when the server is not running:

```python
import subprocess, re

def get_port_cli(project: str) -> int:
    """Fallback: use the pa CLI directly."""
    result = subprocess.run(
        ["pa", "assign", project],
        capture_output=True, text=True, check=True,
    )
    match = re.search(r"port (\d+)", result.stdout)
    return int(match.group(1))
```

### Node.js Projects

```javascript
async function getPort(project, { lanExposed = false } = {}) {
  const resp = await fetch("http://127.0.0.1:7600/assign", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project, lan_exposed: lanExposed }),
  });
  if (!resp.ok) throw new Error(`port-authority: ${resp.statusText}`);
  const data = await resp.json();
  return data.port;
}

// Usage
const port = await getPort("my-node-app");
app.listen(port);
```

### Docker Compose

Request the port before starting containers and pass it as an environment variable:

```bash
#!/bin/bash
# start.sh
export APP_PORT=$(curl -sf http://127.0.0.1:7600/assign \
  -H "Content-Type: application/json" \
  -d '{"project": "my-docker-app", "lan_exposed": true}' | jq -r .port)

docker compose up -d
```

```yaml
# docker-compose.yml
services:
  web:
    build: .
    ports:
      - "${APP_PORT}:8080"
```

### CLAUDE.md / AI Agent Integration

Add to your project's `CLAUDE.md` so AI agents know to use port-authority:

```markdown
## Port Assignment
This project uses port-authority for port management.
Before starting any server, request a port:
  pa assign <project-name>
Never hardcode ports. Always check with port-authority first.
Server URL: http://127.0.0.1:7600
```

### API Reference for Integration

**POST /assign** - the primary integration endpoint

Request body:
```json
{
  "project": "my-app",
  "allocation_type": "persistent",
  "lan_exposed": false,
  "description": "My web dashboard",
  "preferred_port": null
}
```

Response (200):
```json
{
  "project": "my-app",
  "port": 8000,
  "allocation_type": "persistent",
  "lan_exposed": false,
  "description": "My web dashboard",
  "created_at": 1741500000.0,
  "last_seen_at": 1741500000.0
}
```

Error responses:
- `409` - preferred port conflicts with an existing assignment or is in use by another process
- `503` - no ports available in the configured range

**GET /lookup/{project}** - check a project's port without side effects

Returns the same response shape as `/assign`, or `404` if not assigned.

**DELETE /release/{project}** - free a port (for ephemeral use)

Returns `200` on success, `404` if no assignment exists.

### Tips

- **Idempotent**: calling `/assign` multiple times with the same project name is safe and returns the same port
- **LAN services**: set `lan_exposed: true` so you can identify which ports are accessible beyond localhost
- **Ephemeral tests**: use `allocation_type: "ephemeral"` and call `/release/{project}` when the test run finishes
- **Preferred port**: set `preferred_port` only if your project truly needs a specific port (e.g., OAuth callback URLs), otherwise let port-authority pick one
- **Environment variable**: set `PORT_AUTHORITY_URL` to override the default server address

## Running Tests

```bash
pytest
```
