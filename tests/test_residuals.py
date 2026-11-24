"""Residual findings from the re-review: exit interfaces, linkdown, local delivery, RFC 5549."""

import json

import pytest

from routedoctor import diagnose_destination, parse_routes, parse_snapshot, parse_table, trace
from routedoctor.web import run

# --- 1. A route with a next hop and an interface leaves through that interface -------------


def _no_recursion(findings: list[str]) -> bool:
    return not any("resolves through" in f or "loop" in f for f in findings)


def test_two_linux_onlink_routes_to_the_same_gateway_are_not_a_loop() -> None:
    table = parse_table(
        "default via 203.0.113.1 dev eth0 onlink\n"
        "198.51.100.0/24 via 203.0.113.1 dev eth0 onlink\n"
    )
    result = diagnose_destination(table.routes, "198.51.100.9")
    assert result.ok, result.findings
    assert result.findings[1] == "Next hop 203.0.113.1 is reached through eth0"
    assert _no_recursion(result.findings)
    assert result.recursive_chain == ["203.0.113.1"]


def test_two_ios_fully_specified_statics_are_not_a_loop() -> None:
    table = parse_table(
        "S*   0.0.0.0/0 [1/0] via 192.0.2.1, GigabitEthernet0/0\n"
        "S    198.51.100.0/24 [1/0] via 192.0.2.1, GigabitEthernet0/0\n"
    )
    result = diagnose_destination(table.routes, "198.51.100.9")
    assert result.ok, result.findings
    assert "Next hop 192.0.2.1 is reached through GigabitEthernet0/0" in result.findings


H_TABLE = (
    "default via 192.0.2.1 dev eth0 proto dhcp metric 100\n"
    "192.0.2.0/24 dev eth0 proto kernel scope link src 192.0.2.10\n"
    "198.51.100.0/24 via 203.0.113.1 dev tun0 onlink\n"
)


def test_onlink_route_leaves_through_its_own_device_not_the_default() -> None:
    result = diagnose_destination(parse_table(H_TABLE).routes, "198.51.100.9")
    assert result.ok
    assert result.findings[1] == "Next hop 203.0.113.1 is reached through tun0"
    assert _no_recursion(result.findings)


def test_trace_follows_an_onlink_gateway_on_another_device() -> None:
    devices = parse_snapshot(
        {
            "devices": [
                {"name": "h", "table": H_TABLE, "addresses": ["192.0.2.10"]},
                {
                    "name": "isp",
                    "routes": [{"prefix": "0.0.0.0/0", "next_hop": "192.0.2.10", "interface": "e0"}],
                    "addresses": ["192.0.2.1"],
                },
                {
                    "name": "peer",
                    "routes": [
                        {"prefix": "198.51.100.0/24", "protocol": "connected", "interface": "e1"}
                    ],
                    "addresses": ["203.0.113.1"],
                },
            ]
        }
    )
    result = trace(devices, "h", "198.51.100.9")
    assert (result.outcome, result.detail) == ("delivered", "peer")
    assert [hop.device for hop in result.hops] == ["h", "peer"]


def test_json_route_with_both_fields_is_not_resolved_recursively() -> None:
    routes = parse_routes(
        [
            {"prefix": "198.51.100.0/24", "next_hop": "192.0.2.1", "interface": "eth0"},
            {"prefix": "192.0.2.0/24", "interface": "eth0", "protocol": "connected"},
        ]
    )
    result = diagnose_destination(routes, "198.51.100.9")
    assert result.findings[1:] == ["Next hop 192.0.2.1 is reached through eth0"]


def test_recursion_stops_at_a_route_that_names_an_interface() -> None:
    routes = parse_routes(
        [
            {"prefix": "203.0.113.0/24", "next_hop": "198.51.100.1"},
            {"prefix": "198.51.100.0/24", "next_hop": "192.0.2.2", "interface": "Gi0/0"},
            {"prefix": "192.0.2.0/24", "interface": "Gi0/1", "protocol": "connected"},
        ]
    )
    result = diagnose_destination(routes, "203.0.113.9")
    assert result.ok
    assert result.findings[1:] == [
        "Next hop 198.51.100.1 resolves through 198.51.100.0/24",
        "Next hop 192.0.2.2 is reached through Gi0/0",
    ]
    assert result.recursive_chain == ["198.51.100.1", "192.0.2.2"]


def test_interface_less_recursive_loop_is_still_detected() -> None:
    routes = parse_routes(
        [
            {"prefix": "203.0.113.0/24", "next_hop": "192.0.2.1"},
            {"prefix": "192.0.2.1/32", "next_hop": "198.51.100.1"},
            {"prefix": "198.51.100.1/32", "next_hop": "192.0.2.1"},
        ]
    )
    result = diagnose_destination(routes, "203.0.113.9")
    assert result.findings[-1] == "ERROR recursive routing loop while resolving 192.0.2.1"


# --- 2. linkdown keeps the route selected and drops the traffic ----------------------------

LINKDOWN_ERROR = "ERROR exit interface {} has no carrier (linkdown); traffic is dropped"


def test_linkdown_route_wins_and_drops() -> None:
    table = parse_table(
        "default via 192.0.2.1 dev eth0\n"
        "192.0.2.0/24 dev eth0 proto kernel scope link\n"
        "198.51.100.0/24 dev eth1 proto kernel scope link src 198.51.100.1 linkdown\n"
    )
    result = diagnose_destination(table.routes, "198.51.100.9")
    assert not result.ok
    assert result.selected.prefix == "198.51.100.0/24"
    assert LINKDOWN_ERROR.format("eth1") in result.findings


def test_linkdown_default_with_lower_metric_still_wins() -> None:
    table = parse_table(
        "default via 192.0.2.1 dev eth0 metric 100 linkdown\n"
        "default via 192.0.2.129 dev eth1 metric 200\n"
    )
    result = diagnose_destination(table.routes, "203.0.113.1")
    assert (result.selected.next_hop, result.selected.linkdown) == ("192.0.2.1", True)
    assert LINKDOWN_ERROR.format("eth0") in result.findings


def test_dead_multipath_nexthop_is_skipped_when_another_is_alive() -> None:
    table = parse_table(
        "default proto static metric 100\n"
        "\tnexthop via 192.0.2.1 dev eth0 weight 1 dead linkdown\n"
        "\tnexthop via 198.51.100.1 dev eth1 weight 1\n"
        "192.0.2.0/24 dev eth0 proto kernel scope link linkdown\n"
        "198.51.100.0/24 dev eth1 proto kernel scope link\n"
    )
    result = diagnose_destination(table.routes, "203.0.113.9")
    assert result.ok, result.findings
    assert result.selected.next_hop == "198.51.100.1"
    assert "1 inactive route(s) for this destination were skipped, including 0.0.0.0/0" in (
        result.findings
    )


def test_multipath_route_with_every_nexthop_down_drops() -> None:
    table = parse_table(
        "default proto static metric 100\n"
        "\tnexthop via 192.0.2.1 dev eth0 weight 1 dead linkdown\n"
        "\tnexthop via 192.0.2.2 dev eth1 weight 1 linkdown\n"
    )
    result = diagnose_destination(table.routes, "203.0.113.9")
    assert not result.ok
    assert LINKDOWN_ERROR.format("eth0") in result.findings


def test_json_linkdown_flag() -> None:
    routes = parse_routes([{"prefix": "0.0.0.0/0", "interface": "eth0", "linkdown": True}])
    assert diagnose_destination(routes, "203.0.113.1").findings[-1] == LINKDOWN_ERROR.format(
        "eth0"
    )
    with pytest.raises(ValueError, match="linkdown must be true or false"):
        parse_routes([{"prefix": "0.0.0.0/0", "interface": "eth0", "linkdown": "yes"}])


# --- 3. local delivers only for a host prefix ----------------------------------------------


@pytest.mark.parametrize(
    ("prefix", "outcome"),
    [("198.51.100.0/24", "unknown_next_hop"), ("198.51.100.9/32", "delivered")],
)
def test_local_route_delivers_only_for_a_host_prefix(prefix: str, outcome: str) -> None:
    devices = parse_snapshot(
        {
            "devices": [
                {
                    "name": "a",
                    "routes": [{"prefix": prefix, "protocol": "local", "interface": "e0"}],
                    "addresses": ["192.0.2.1"],
                }
            ]
        }
    )
    assert trace(devices, "a", "198.51.100.9").outcome == outcome


def test_local_ipv6_host_route_delivers() -> None:
    devices = parse_snapshot(
        {
            "devices": [
                {
                    "name": "a",
                    "routes": [{"prefix": "2001:db8::9/128", "protocol": "local", "interface": "e0"}],
                    "addresses": ["2001:db8::1"],
                }
            ]
        }
    )
    assert trace(devices, "a", "2001:db8::9").outcome == "delivered"


# --- 4. RFC 5549: an IPv4 route via an IPv6 gateway ----------------------------------------

RFC5549 = "198.51.100.0/24 via inet6 2001:db8::1 dev eth0 proto bgp"


def test_ipv4_route_via_ipv6_gateway_names_the_line() -> None:
    text = f"{RFC5549}\n192.0.2.0/24 dev eth0 proto kernel scope link\n"
    with pytest.raises(ValueError) as info:
        parse_table(text)
    assert str(info.value) == f"IPv4 route via an IPv6 gateway is not supported: {RFC5549}"


def test_ipv4_default_via_ipv6_link_local_gateway_is_refused() -> None:
    with pytest.raises(ValueError, match="^IPv4 route via an IPv6 gateway is not supported: "):
        parse_table("default via inet6 fe80::1 dev eth0 proto bgp\n192.0.2.0/24 dev eth0\n")


def test_rfc5549_multipath_nexthop_is_refused() -> None:
    text = "198.51.100.0/24 proto bgp metric 20\n\tnexthop via inet6 2001:db8::1 dev eth0 weight 1\n"
    with pytest.raises(ValueError, match="^IPv4 route via an IPv6 gateway is not supported: "):
        parse_table(text)


def test_rfc5549_error_line_is_cut_to_120_characters() -> None:
    line = RFC5549 + " " + "x" * 300
    with pytest.raises(ValueError) as info:
        parse_table(line + "\n")
    assert str(info.value) == f"IPv4 route via an IPv6 gateway is not supported: {line[:120]}"


def test_rfc5549_error_through_the_web_entry_point() -> None:
    out = json.loads(
        run(json.dumps({"action": "diagnose", "table": RFC5549 + "\n", "destination": "198.51.100.1"}))
    )
    assert out == {"ok": False, "error": f"IPv4 route via an IPv6 gateway is not supported: {RFC5549}"}
