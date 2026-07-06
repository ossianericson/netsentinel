"""Tests for modules/process_monitor.py — process-to-socket mapping."""
from modules.process_monitor import Connection, _is_private, is_available


def test_import():
    from modules import process_monitor as m
    assert hasattr(m, "snapshot")
    assert hasattr(m, "Connection")
    assert hasattr(m, "is_available")
    assert hasattr(m, "_is_private")


def test_connection_fields():
    c = Connection(
        pid=1234,
        exe_name="python.exe",
        exe_path="C:\\Python311\\python.exe",
        proto="TCP",
        local_addr="127.0.0.1:8080",
        remote_addr="8.8.8.8:443",
        remote_ip="8.8.8.8",
        remote_port=443,
        status="ESTABLISHED",
    )
    assert c.pid == 1234
    assert c.exe_name == "python.exe"
    assert c.status == "ESTABLISHED"
    assert c.remote_ip == "8.8.8.8"


def test_is_private_rfc1918():
    assert _is_private("192.168.1.1") is True
    assert _is_private("10.0.0.1") is True
    assert _is_private("172.16.0.1") is True


def test_is_private_loopback():
    assert _is_private("127.0.0.1") is True


def test_is_not_private_public():
    assert _is_private("8.8.8.8") is False
    assert _is_private("1.1.1.1") is False


def test_is_available_returns_bool():
    assert isinstance(is_available(), bool)


def test_snapshot_returns_list():
    from modules.process_monitor import snapshot
    result = snapshot()
    assert isinstance(result, list)


def test_snapshot_items_are_connections():
    from modules.process_monitor import snapshot
    result = snapshot()
    for item in result[:5]:
        assert isinstance(item, Connection)
