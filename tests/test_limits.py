"""Runtime bounds for inputs inside the size limits (finding 7)."""

import json
import time
from ipaddress import ip_address

import pytest

from routedoctor import diagnose_destination, parse_routes, parse_table
from routedoctor.parsers import _IOS6_ROUTE_RE, _IOS_ROUTE_RE
from routedoctor.web import run


def _elapsed(func, *args):
    start = time.perf_counter()
    value = func(*args)
    return time.perf_counter() - start, value


def test_long_colon_line_is_rejected_quickly() -> None:
    elapsed, raw = _elapsed(
        run, json.dumps({"action": "diagnose", "table": "S " + ":" * 80_000, "destination": "::1"})
    )
    assert elapsed < 1
    assert "no routes recognised" in json.loads(raw)["error"]


@pytest.mark.parametrize("pattern", [_IOS_ROUTE_RE, _IOS6_ROUTE_RE])
def test_ios_route_patterns_are_linear(pattern) -> None:
    elapsed, match = _elapsed(pattern.match, "S " + ":" * 80_000)
    assert elapsed < 1
    assert match is None


def test_lines_longer_than_2000_characters_are_skipped() -> None:
    long_line = "S    198.51.100.0/24 [1/0] via 192.0.2.1, " + "x" * 2000
    table = parse_table(f"{long_line}\nS    203.0.113.0/24 [1/0] via 192.0.2.1\n")
    assert [route.prefix for route in table.routes] == ["203.0.113.0/24"]
    with pytest.raises(ValueError, match="no routes recognised"):
        parse_table("192.0.2.0/24 dev eth0 " + "x" * 2000 + "\n")


def test_json_input_is_not_cut_by_the_line_limit() -> None:
    routes = [{"prefix": f"198.51.100.{k}/32", "interface": "eth0"} for k in range(100)]
    text = json.dumps(routes)
    assert len(text) > 2000
    assert len(parse_table(text).routes) == 100


def _chain(levels: int) -> list[dict]:
    """A default route whose next hop needs `levels` recursive lookups to reach an interface."""
    base = int(ip_address("192.0.0.0"))
    routes = [{"prefix": "0.0.0.0/0", "next_hop": str(ip_address(base))}]
    for k in range(levels - 1):
        hop, following = ip_address(base + k), ip_address(base + k + 1)
        routes.append({"prefix": f"{hop}/32", "next_hop": str(following)})
    routes.append({"prefix": f"{ip_address(base + levels - 1)}/32", "interface": "eth0"})
    return routes


def test_resolution_of_64_levels_succeeds() -> None:
    result = diagnose_destination(parse_routes(_chain(64)), "203.0.113.1")
    assert result.ok, result.findings[-3:]
    assert len(result.recursive_chain) == 64


def test_resolution_deeper_than_64_levels_is_an_error() -> None:
    result = diagnose_destination(parse_routes(_chain(65)), "203.0.113.1")
    assert not result.ok
    assert result.findings[-1] == "ERROR next-hop resolution exceeds 64 levels"
    assert len(result.recursive_chain) == 64


def test_a_5000_route_chain_finishes_in_under_a_second() -> None:
    # Too large for the 200,000-character text limit, so this goes through the Python API.
    items = _chain(5000)
    start = time.perf_counter()
    result = diagnose_destination(parse_routes(items), "203.0.113.1")
    assert time.perf_counter() - start < 1
    assert result.findings[-1] == "ERROR next-hop resolution exceeds 64 levels"


def test_a_long_chain_through_the_web_entry_point_is_bounded() -> None:
    table = json.dumps(_chain(3000), separators=(",", ":"))
    assert len(table) < 200_000
    request = json.dumps({"action": "diagnose", "table": table, "destination": "203.0.113.1"})
    elapsed, raw = _elapsed(run, request)
    assert elapsed < 1
    response = json.loads(raw)
    assert response["ok"] and not response["passed"]
    assert response["result"]["findings"][-1] == "ERROR next-hop resolution exceeds 64 levels"


def test_route_network_is_parsed_once() -> None:
    (route,) = parse_routes([{"prefix": "192.0.2.0/24", "interface": "eth0"}])
    assert route.network is route.network
