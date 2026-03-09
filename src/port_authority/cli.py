"""CLI for port-authority - both server management and client operations."""

import json
import sys
from datetime import datetime, timezone

import click
import httpx

from port_authority import db

DEFAULT_SERVER_URL = "http://127.0.0.1:7600"


def _format_time(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def _client(server_url: str) -> httpx.Client:
    return httpx.Client(base_url=server_url, timeout=5.0)


@click.group()
@click.option("--server", default=DEFAULT_SERVER_URL, envvar="PORT_AUTHORITY_URL",
              help="Server URL (default: http://127.0.0.1:7600)")
@click.pass_context
def cli(ctx, server):
    ctx.ensure_object(dict)
    ctx.obj["server"] = server


@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind address")
@click.option("--port", default=7600, help="Server port (default: 7600)")
def serve(host, port):
    """Start the port-authority server."""
    import uvicorn
    from port_authority.server import app

    click.echo(f"Port Authority listening on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


@cli.command()
@click.argument("project")
@click.option("-t", "--type", "alloc_type", type=click.Choice(["persistent", "ephemeral"]),
              default="persistent", help="Allocation type")
@click.option("--lan", is_flag=True, help="Mark as LAN-exposed")
@click.option("-d", "--description", default="", help="Project description")
@click.option("-p", "--port", "preferred_port", type=int, default=None,
              help="Request a specific port")
@click.pass_context
def assign(ctx, project, alloc_type, lan, description, preferred_port):
    """Request a port for PROJECT. Returns existing assignment if one exists."""
    try:
        with _client(ctx.obj["server"]) as client:
            resp = client.post("/assign", json={
                "project": project,
                "allocation_type": alloc_type,
                "lan_exposed": lan,
                "description": description,
                "preferred_port": preferred_port,
            })
            resp.raise_for_status()
            data = resp.json()
            click.echo(f"{data['project']}: port {data['port']} ({data['allocation_type']})"
                       f"{' [LAN]' if data['lan_exposed'] else ''}")
    except httpx.ConnectError:
        _offline_assign(project, alloc_type, lan, description, preferred_port)
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: {e.response.json().get('detail', str(e))}", err=True)
        sys.exit(1)


def _offline_assign(project, alloc_type, lan, description, preferred_port):
    """Direct DB access when server is not running."""
    conn = db.get_connection()
    try:
        row = db.assign_port(conn, project, alloc_type, lan, description, preferred_port)
        click.echo(f"{row['project']}: port {row['port']} ({row['allocation_type']})"
                    f"{' [LAN]' if row['lan_exposed'] else ''}"
                    " (offline mode)")
    except (db.PortConflictError, db.NoPortAvailableError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    finally:
        conn.close()


@cli.command()
@click.argument("project")
@click.pass_context
def release(ctx, project):
    """Release a project's port assignment."""
    try:
        with _client(ctx.obj["server"]) as client:
            resp = client.delete(f"/release/{project}")
            resp.raise_for_status()
            click.echo(f"Released port for '{project}'")
    except httpx.ConnectError:
        conn = db.get_connection()
        if db.release_port(conn, project):
            click.echo(f"Released port for '{project}' (offline mode)")
        else:
            click.echo(f"No assignment found for '{project}'", err=True)
            sys.exit(1)
        conn.close()
    except httpx.HTTPStatusError as e:
        click.echo(f"Error: {e.response.json().get('detail', str(e))}", err=True)
        sys.exit(1)


@cli.command("ls")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def list_ports(ctx, as_json):
    """List all port assignments."""
    try:
        with _client(ctx.obj["server"]) as client:
            resp = client.get("/assignments")
            resp.raise_for_status()
            assignments = resp.json()
    except httpx.ConnectError:
        conn = db.get_connection()
        assignments = db.list_assignments(conn)
        conn.close()

    if as_json:
        click.echo(json.dumps(assignments, indent=2))
        return

    if not assignments:
        click.echo("No port assignments.")
        return

    click.echo(f"{'PORT':<7} {'PROJECT':<25} {'TYPE':<12} {'LAN':<5} {'DESCRIPTION'}")
    click.echo("-" * 75)
    for a in assignments:
        lan_flag = "yes" if a.get("lan_exposed") else ""
        click.echo(
            f"{a['port']:<7} {a['project']:<25} {a['allocation_type']:<12} "
            f"{lan_flag:<5} {a.get('description', '')}"
        )


@cli.command()
@click.argument("project")
@click.pass_context
def lookup(ctx, project):
    """Look up the port for a project."""
    try:
        with _client(ctx.obj["server"]) as client:
            resp = client.get(f"/lookup/{project}")
            resp.raise_for_status()
            data = resp.json()
    except httpx.ConnectError:
        conn = db.get_connection()
        data = db.get_assignment(conn, project)
        conn.close()
        if not data:
            click.echo(f"No assignment for '{project}'", err=True)
            sys.exit(1)
    except httpx.HTTPStatusError:
        click.echo(f"No assignment for '{project}'", err=True)
        sys.exit(1)

    click.echo(f"{data['project']}: port {data['port']} ({data['allocation_type']})"
               f"{' [LAN]' if data.get('lan_exposed') else ''}")


@cli.command()
@click.pass_context
def next(ctx):
    """Show the next available port."""
    try:
        with _client(ctx.obj["server"]) as client:
            resp = client.get("/next-available")
            resp.raise_for_status()
            click.echo(resp.json()["port"])
    except httpx.ConnectError:
        conn = db.get_connection()
        port = db.find_next_available_port(conn)
        conn.close()
        if port is None:
            click.echo("No ports available", err=True)
            sys.exit(1)
        click.echo(port)


@cli.command()
@click.pass_context
def status(ctx):
    """Check if the port-authority server is running."""
    try:
        with _client(ctx.obj["server"]) as client:
            resp = client.get("/health")
            resp.raise_for_status()
            click.echo(f"Server is running at {ctx.obj['server']}")
    except httpx.ConnectError:
        click.echo(f"Server is NOT running at {ctx.obj['server']}")
        click.echo("CLI commands still work in offline mode (direct DB access).")
        sys.exit(1)


if __name__ == "__main__":
    cli()
