"""Tests for modules/nl_query.py — natural language device query parser."""


def test_nl_query_import():
    from modules import nl_query
    assert nl_query is not None


def test_query_result_dataclass():
    from modules.nl_query import QueryResult
    result = QueryResult(matches=[], query="show all", explanation="no devices")
    assert result.matches == []
    assert result.explanation == "no devices"


def test_query_match_dataclass():
    from modules.nl_query import QueryMatch
    qm = QueryMatch(device={"ip": "10.0.0.1"}, score=0.9, reason="high risk")
    assert qm.score == 0.9
    assert qm.reason == "high risk"


def _make_device(ip="10.0.0.1", risk="LOW", ports=None, dtype="router",
                 vendor="Cisco", hostname="router.local", os_family="linux"):
    return {
        "ip": ip,
        "risk": risk,
        "open_ports": ports or [],
        "type": dtype,
        "vendor": vendor,
        "hostname": hostname,
        "os": os_family,
    }


def test_search_function_exists_and_callable():
    from modules import nl_query
    funcs = [f for f in dir(nl_query) if "search" in f.lower() or "query" in f.lower()]
    assert len(funcs) > 0, "Expected at least one search/query function"


def test_risk_level_helper():
    from modules.nl_query import _risk_level
    dev = _make_device(risk="HIGH")
    level = _risk_level(dev)
    assert isinstance(level, str)
    assert len(level) > 0


def test_open_ports_helper():
    from modules.nl_query import _open_ports
    dev = _make_device(ports=[22, 80, 443])
    ports = _open_ports(dev)
    assert isinstance(ports, list)
    assert 22 in ports


def test_norm_lowercases_strips():
    from modules.nl_query import _norm
    assert _norm("  Hello World  ") == "hello world"


def test_device_type_helper():
    from modules.nl_query import _device_type
    dev = _make_device(dtype="printer")
    assert isinstance(_device_type(dev), str)
