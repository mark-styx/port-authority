"""Shared fixtures."""

import pytest

from port_authority import scanner


@pytest.fixture(autouse=True)
def in_use(monkeypatch):
    """Fake the OS view of in-use ports so tests don't depend on the host.

    Tests add entries as ``in_use[port] = "process description"``.
    """
    ports: dict[int, str] = {}
    monkeypatch.setattr(scanner, "is_port_in_use", lambda port: port in ports)
    monkeypatch.setattr(
        scanner,
        "listening_ports",
        lambda lo, hi: {p: name for p, name in ports.items() if lo <= p <= hi},
    )
    return ports
