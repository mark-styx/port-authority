# Port Authority

Local port assignment manager for development services. Prevents port collisions across multiple projects, supports persistent assignments for LAN-exposed services, and ephemeral assignments for temporary testing.

## Install

```bash
cd /Users/mark/sentinel/port-authority
pip install -e ".[dev]"
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
```

## How It Works

- **Persistent assignments**: Same port every time for a given project name. Use for services you access regularly or expose on LAN.
- **Ephemeral assignments**: Temporary ports for testing. Release when done.
- **Idempotent**: Requesting a port for an already-assigned project returns the existing assignment.
- **Offline mode**: CLI falls back to direct SQLite access when the server is not running.

## API

Server runs on `http://127.0.0.1:7600` by default.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/assign` | Request a port assignment |
| DELETE | `/release/{project}` | Release an assignment |
| GET | `/assignments` | List all assignments |
| GET | `/lookup/{project}` | Look up a project's port |
| GET | `/port/{port}` | Check what's on a port |
| GET | `/next-available` | Peek at next free port |
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

## Integration with Projects

Add to your project's startup script:

```bash
PORT=$(pa assign my-project -t persistent | grep -oP 'port \K[0-9]+')
# or via API:
PORT=$(curl -s -X POST http://127.0.0.1:7600/assign \
  -H "Content-Type: application/json" \
  -d '{"project": "my-project"}' | jq .port)
```

## Running Tests

```bash
pytest
```
