"""Tests for in-use port detection against real sockets."""

import socket

import pytest

from port_authority.scanner import (
    _listening_ports_probe,
    _listening_ports_psutil,
    is_port_in_use,
)


@pytest.fixture
def in_use():
    """Override the autouse fake from conftest: these tests hit real sockets."""
    return {}


@pytest.fixture
def listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    yield sock.getsockname()[1]
    sock.close()


def test_listening_port_is_in_use(listener):
    assert is_port_in_use(listener) is True


def test_closed_port_is_free():
    # Grab a port, release it, and confirm it reads as free again
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    assert is_port_in_use(port) is False


def test_probe_finds_listener(listener):
    assert listener in _listening_ports_probe(listener, listener)


def test_psutil_finds_listener(listener):
    pytest.importorskip("psutil")
    found = _listening_ports_psutil(listener, listener)
    if found is None:
        pytest.skip("psutil not permitted to list connections here")
    assert listener in found
