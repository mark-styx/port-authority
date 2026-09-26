"""Detect which local TCP ports are actually in use.

Two strategies are used:

- ``psutil`` (optional, ``pip install port-authority[scan]``): lists listening
  sockets and the owning process name where the OS permits it.
- Bind probing (always available): try to bind the port; if the OS refuses
  with ``EADDRINUSE`` something else owns it.
"""

import errno
import socket
import sys


def is_port_in_use(port: int) -> bool:
    """Return True if binding ``port`` on all interfaces would fail."""
    candidates = [(socket.AF_INET, "0.0.0.0")]
    if socket.has_ipv6:
        candidates.append((socket.AF_INET6, "::"))

    for family, addr in candidates:
        try:
            sock = socket.socket(family, socket.SOCK_STREAM)
        except OSError:
            continue
        with sock:
            # On Linux SO_REUSEADDR only skips TIME_WAIT leftovers; it still
            # fails against a live listener. BSD/macOS semantics are looser,
            # so only enable it on Linux.
            if sys.platform.startswith("linux"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if family == socket.AF_INET6:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            try:
                sock.bind((addr, port))
            except OSError as e:
                if e.errno in (errno.EADDRINUSE, errno.EACCES):
                    return True
                # e.g. EADDRNOTAVAIL when IPv6 is disabled - not a conflict
    return False


def _listening_ports_psutil(port_min: int, port_max: int) -> dict[int, str] | None:
    try:
        import psutil
    except ImportError:
        return None
    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError):
        return None

    found: dict[int, str] = {}
    for c in conns:
        if c.status != psutil.CONN_LISTEN or not c.laddr:
            continue
        port = c.laddr.port
        if not port_min <= port <= port_max:
            continue
        name = ""
        if c.pid:
            try:
                name = f"{psutil.Process(c.pid).name()} (pid {c.pid})"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                name = f"pid {c.pid}"
        if name or port not in found:
            found[port] = name
    return found


def _listening_ports_probe(port_min: int, port_max: int) -> dict[int, str]:
    return {p: "" for p in range(port_min, port_max + 1) if is_port_in_use(p)}


def listening_ports(port_min: int, port_max: int) -> dict[int, str]:
    """Return ``{port: process_description}`` for in-use ports in the range.

    The description is empty when the owning process can't be determined.
    """
    found = _listening_ports_psutil(port_min, port_max)
    if found is None:
        return _listening_ports_probe(port_min, port_max)
    return found
