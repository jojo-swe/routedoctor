from pathlib import Path

import pytest

from routedoctor import diagnose_destination, parse_routes, parse_table


def test_prefers_longest_prefix_then_admin_distance_and_metric() -> None:
    routes = parse_routes(
        [
            {"prefix": "0.0.0.0/0", "next_hop": "192.0.2.1", "admin_distance": 1},
            {"prefix": "198.51.100.0/24", "next_hop": "192.0.2.2", "admin_distance": 110},
            {"prefix": "198.51.100.8/29", "next_hop": "192.0.2.3", "admin_distance": 20},
            {"prefix": "192.0.2.0/24", "interface": "GigabitEthernet0/0"},
        ]
    )

    result = diagnose_destination(routes, "198.51.100.9")

    assert result.ok
    assert result.selected is not None
    assert result.selected.prefix == "198.51.100.8/29"
    assert result.recursive_chain == ["192.0.2.3"]


def test_reports_unresolved_next_hop() -> None:
    routes = parse_routes([{"prefix": "203.0.113.0/24", "next_hop": "198.51.100.1"}])

    result = diagnose_destination(routes, "203.0.113.9")

    assert not result.ok
    assert "ERROR next hop 198.51.100.1 is unresolved" in result.findings


def test_reports_missing_route() -> None:
    result = diagnose_destination([], "8.8.8.8")

    assert not result.ok
    assert result.selected is None
    assert result.findings == ["ERROR no matching active route; traffic is dropped"]


def test_reports_equal_cost_paths() -> None:
    routes = parse_routes(
        [
            {"prefix": "198.51.100.0/24", "protocol": "ospf", "next_hop": "192.0.2.1",
             "admin_distance": 110, "metric": 20},
            {"prefix": "198.51.100.0/24", "protocol": "ospf", "next_hop": "192.0.2.2",
             "admin_distance": 110, "metric": 20},
            {"prefix": "198.51.100.0/24", "protocol": "ospf", "next_hop": "192.0.2.9",
             "admin_distance": 110, "metric": 30},
            {"prefix": "192.0.2.0/24", "interface": "GigabitEthernet0/0"},
        ]
    )

    result = diagnose_destination(routes, "198.51.100.9")

    assert result.ok
    assert [route.next_hop for route in result.equal_cost] == ["192.0.2.1", "192.0.2.2"]
    assert "2 equal-cost paths via 192.0.2.1, 192.0.2.2; showing the first" in result.findings
    assert not any(finding.startswith("Tie broken") for finding in result.findings)
    assert len(result.to_dict()["equal_cost"]) == 2


def test_reports_tie_break_when_costs_differ() -> None:
    routes = parse_routes(
        [
            {"prefix": "198.51.100.0/24", "protocol": "ospf", "next_hop": "192.0.2.1",
             "admin_distance": 110, "metric": 20},
            {"prefix": "198.51.100.0/24", "protocol": "static", "next_hop": "192.0.2.2"},
            {"prefix": "192.0.2.0/24", "interface": "GigabitEthernet0/0"},
        ]
    )

    result = diagnose_destination(routes, "198.51.100.9")

    assert result.equal_cost == []
    assert "Tie broken by administrative distance 1 and metric 0" in result.findings


def test_reports_skipped_inactive_routes() -> None:
    routes = parse_routes(
        [
            {"prefix": "198.51.100.0/24", "next_hop": "192.0.2.1", "active": False},
            {"prefix": "198.51.100.8/29", "next_hop": "192.0.2.2", "active": False},
            {"prefix": "203.0.113.0/24", "next_hop": "192.0.2.3", "active": False},
        ]
    )

    result = diagnose_destination(routes, "198.51.100.9")

    assert not result.ok
    assert result.findings == [
        "ERROR no matching active route; traffic is dropped",
        "2 inactive route(s) for this destination were skipped, including 198.51.100.0/24",
    ]


def test_detects_recursive_loop() -> None:
    routes = parse_routes(
        [
            {"prefix": "203.0.113.0/24", "next_hop": "192.0.2.1"},
            {"prefix": "192.0.2.1/32", "next_hop": "198.51.100.1"},
            {"prefix": "198.51.100.1/32", "next_hop": "192.0.2.1"},
        ]
    )

    result = diagnose_destination(routes, "203.0.113.9")

    assert not result.ok
    assert any("recursive routing loop" in finding for finding in result.findings)


def test_diagnoses_ipv6_longest_prefix() -> None:
    routes = parse_routes(
        [
            {"prefix": "::/0", "next_hop": "2001:db8:ffff::1"},
            {
                "prefix": "2001:db8:1::/48",
                "next_hop": "2001:db8:ffff::2",
                "protocol": "ospf",
                "admin_distance": 110,
                "metric": 10,
            },
            {
                "prefix": "2001:db8:ffff::/64",
                "interface": "GigabitEthernet0/0",
                "protocol": "connected",
                "admin_distance": 0,
            },
        ]
    )
    result = diagnose_destination(routes, "2001:db8:1::9")
    assert result.ok
    assert result.selected.prefix == "2001:db8:1::/48"
    assert result.recursive_chain == ["2001:db8:ffff::2"]


def test_other_ip_version_is_a_missing_route_not_an_error() -> None:
    routes = parse_routes([{"prefix": "0.0.0.0/0", "interface": "eth0"}])
    result = diagnose_destination(routes, "2001:db8::1")
    assert not result.ok
    assert result.findings == ["ERROR no matching active route; traffic is dropped"]


def test_rejects_next_hop_of_other_version() -> None:
    with pytest.raises(ValueError, match="invalid route at index 0"):
        parse_routes([{"prefix": "2001:db8::/32", "next_hop": "192.0.2.1"}])


@pytest.mark.parametrize(
    "bad",
    [
        {"prefix": "0.0.0.0/0", "next_hop": 0, "interface": "eth0"},
        {"prefix": "0.0.0.0/0", "next_hop": "", "interface": "eth0"},
        {"prefix": "0.0.0.0/0", "interface": ""},
        {"prefix": "0.0.0.0/0", "interface": 5},
        {"prefix": 5},
        {"prefix": "0.0.0.0/0", "protocol": 7},
        {"prefix": "0.0.0.0/0", "interface": "eth0", "admin_distance": 1e999},
        {"prefix": "0.0.0.0/0", "interface": "eth0", "metric": 1e999},
        {"prefix": "0.0.0.0/0", "interface": "eth0", "admin_distance": True},
        {"prefix": "0.0.0.0/0", "interface": "eth0", "metric": 1.5},
        {"prefix": "0.0.0.0/0", "interface": "eth0", "metric": -1},
        {"prefix": "0.0.0.0/0", "interface": "eth0", "metric": 4294967296},
    ],
)
def test_parse_routes_rejects_malformed_routes_with_value_error(bad: dict) -> None:
    with pytest.raises(ValueError, match="invalid route at index 0"):
        parse_routes([bad])


def test_less_specific_routes_are_counted_once_per_prefix() -> None:
    routes = parse_routes(
        [
            {"prefix": "0.0.0.0/0", "next_hop": "192.0.2.1", "admin_distance": 1},
            {"prefix": "198.51.100.0/24", "next_hop": "192.0.2.2", "admin_distance": 110, "metric": 20},
            {"prefix": "198.51.100.0/24", "next_hop": "192.0.2.4", "admin_distance": 110, "metric": 20},
            {"prefix": "198.51.100.8/29", "next_hop": "192.0.2.3", "admin_distance": 1},
            {"prefix": "192.0.2.0/24", "interface": "GigabitEthernet0/0"},
        ]
    )

    result = diagnose_destination(routes, "198.51.100.9")

    assert (
        "2 less-specific route(s) were ignored, including 198.51.100.0/24" in result.findings
    )


# --- Discard routes and where a route leaves the device (findings 1, 2, 3, 6) --------------

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("kind", ["blackhole", "unreachable", "prohibit"])
def test_linux_discard_route_wins_longest_prefix_and_drops(kind: str) -> None:
    table = parse_table(
        "default via 192.0.2.1 dev eth0 proto dhcp metric 100\n"
        "192.0.2.0/24 dev eth0 proto kernel scope link metric 100\n"
        f"{kind} 203.0.113.128/25 metric 200\n"
    )
    result = diagnose_destination(table.routes, "203.0.113.200")
    assert not result.ok
    assert result.selected.prefix == "203.0.113.128/25"
    assert result.selected.discard == kind
    assert f"ERROR 203.0.113.128/25 is a discard route ({kind}); traffic is dropped" in (
        result.findings
    )
    assert result.recursive_chain == []


def test_linux_fixture_unreachable_route_is_not_forwarded_by_the_default() -> None:
    table = parse_table(FIXTURES.joinpath("linux-ip-route.txt").read_text())
    result = diagnose_destination(table.routes, "203.0.113.200")
    assert not result.ok
    assert result.selected.prefix == "203.0.113.128/25"
    assert "1 less-specific route(s) were ignored, including 0.0.0.0/0" in result.findings


def test_destination_outside_the_discard_route_is_still_forwarded() -> None:
    table = parse_table(FIXTURES.joinpath("linux-ip-route.txt").read_text())
    result = diagnose_destination(table.routes, "203.0.113.5")
    assert result.ok
    assert result.selected.prefix == "0.0.0.0/0"


@pytest.mark.parametrize("interface", ["Null0", "null0", "NULL0", "Null 0"])
def test_null0_interface_is_a_discard_route(interface: str) -> None:
    routes = parse_routes(
        [
            {"prefix": "203.0.113.0/24", "interface": interface},
            {"prefix": "0.0.0.0/0", "next_hop": "192.0.2.1"},
            {"prefix": "192.0.2.0/24", "interface": "eth0", "protocol": "connected"},
        ]
    )
    result = diagnose_destination(routes, "203.0.113.9")
    assert not result.ok
    assert result.selected.discard == "Null0"
    assert "ERROR 203.0.113.0/24 is a discard route (Null0); traffic is dropped" in result.findings
    assert not any(f.startswith("Forward directly") for f in result.findings)


def test_ios_static_to_null0_is_dropped_not_forwarded() -> None:
    table = parse_table(
        "S*    0.0.0.0/0 [1/0] via 192.0.2.1\n"
        "C     192.0.2.0/24 is directly connected, GigabitEthernet0/0\n"
        "S     203.0.113.0/24 is directly connected, Null0\n"
    )
    result = diagnose_destination(table.routes, "203.0.113.9")
    assert not result.ok
    assert "ERROR 203.0.113.0/24 is a discard route (Null0); traffic is dropped" in result.findings


def test_ios6_static_via_null0_is_dropped() -> None:
    table = parse_table(
        "S   ::/0 [1/0]\n     via 2001:DB8:FFFF::1\n"
        "C   2001:DB8:FFFF::/64 [0/0]\n     via GigabitEthernet0/0, directly connected\n"
        "S   2001:DB8:4::/48 [1/0]\n     via Null0, directly connected\n"
    )
    result = diagnose_destination(table.routes, "2001:db8:4::1")
    assert not result.ok
    assert "ERROR 2001:db8:4::/48 is a discard route (Null0); traffic is dropped" in (
        result.findings
    )


def test_more_specific_route_beats_a_discard_summary() -> None:
    table = parse_table(
        "C        192.0.2.0/24 is directly connected, GigabitEthernet0/0\n"
        "D        203.0.113.0/24 is a summary, 00:12:01, Null0\n"
        "D        203.0.113.0/26 [90/3072] via 192.0.2.6, 00:00:09, GigabitEthernet0/0\n"
    )
    assert diagnose_destination(table.routes, "203.0.113.5").ok
    dropped = diagnose_destination(table.routes, "203.0.113.200")
    assert (dropped.selected.protocol, dropped.selected.admin_distance) == ("eigrp", 5)
    assert "ERROR 203.0.113.0/24 is a discard route (Null0); traffic is dropped" in (
        dropped.findings
    )


def test_next_hop_resolving_through_a_discard_route_is_dropped() -> None:
    routes = parse_routes(
        [
            {"prefix": "198.51.100.0/24", "next_hop": "203.0.113.1"},
            {"prefix": "203.0.113.0/24", "discard": "blackhole"},
        ]
    )
    result = diagnose_destination(routes, "198.51.100.9")
    assert not result.ok
    assert result.findings[1:3] == [
        "Next hop 203.0.113.1 resolves through 203.0.113.0/24",
        "ERROR 203.0.113.0/24 is a discard route (blackhole); traffic is dropped",
    ]


def test_json_discard_field_must_be_a_known_kind() -> None:
    (route,) = parse_routes([{"prefix": "203.0.113.0/24", "discard": "unreachable"}])
    assert route.discard == "unreachable"
    assert route.to_dict()["discard"] == "unreachable"
    with pytest.raises(ValueError, match="invalid route at index 0: discard must be one of"):
        parse_routes([{"prefix": "203.0.113.0/24", "discard": "drop"}])


def test_route_dict_keeps_the_old_keys_and_adds_discard() -> None:
    (route,) = parse_routes([{"prefix": "192.0.2.0/24", "interface": "eth0"}])
    assert route.to_dict() == {
        "prefix": "192.0.2.0/24",
        "protocol": "static",
        "next_hop": None,
        "interface": "eth0",
        "admin_distance": 1,
        "metric": 0,
        "active": True,
        "discard": None,
    }


def test_linux_onlink_gateway_terminates_on_its_interface() -> None:
    table = parse_table("default via 203.0.113.1 dev eth0 onlink\n")
    result = diagnose_destination(table.routes, "198.51.100.7")
    assert result.ok, result.findings
    assert "Next hop 203.0.113.1 is on-link through eth0" in result.findings
    assert result.recursive_chain == ["203.0.113.1"]


def test_gateway_with_interface_and_no_covering_route_is_on_link() -> None:
    routes = parse_routes(
        [{"prefix": "198.51.100.0/24", "next_hop": "203.0.113.1", "interface": "Gi0/1"}]
    )
    result = diagnose_destination(routes, "198.51.100.9")
    assert result.ok
    assert result.findings[-1] == "Next hop 203.0.113.1 is on-link through Gi0/1"


def test_gateway_with_interface_still_resolves_through_another_route() -> None:
    routes = parse_routes(
        [
            {"prefix": "198.51.100.0/24", "next_hop": "192.0.2.1", "interface": "eth0"},
            {"prefix": "192.0.2.0/24", "interface": "eth0", "protocol": "connected"},
        ]
    )
    result = diagnose_destination(routes, "198.51.100.9")
    assert result.findings[1:] == [
        "Next hop 192.0.2.1 resolves through 192.0.2.0/24",
        "Recursive resolution terminates on eth0",
    ]


def test_json_link_local_next_hop_with_interface_terminates_on_the_interface() -> None:
    routes = parse_routes([{"prefix": "::/0", "next_hop": "fe80::1", "interface": "eth0"}])
    result = diagnose_destination(routes, "2001:db8::5")
    assert result.ok, result.findings
    assert "Next hop fe80::1 is on-link through eth0" in result.findings


def test_json_link_local_next_hop_without_interface_is_an_error() -> None:
    # A link-local address is only meaningful on one link, so it never resolves through ::/0.
    routes = parse_routes([{"prefix": "::/0", "next_hop": "fe80::1"}])
    result = diagnose_destination(routes, "2001:db8::5")
    assert not result.ok
    assert result.findings[1:] == ["ERROR next hop fe80::1 is link-local and has no exit interface"]


def test_kernel_unreachable_default_does_not_beat_a_real_default() -> None:
    table = parse_table(
        "2001:db8:ffff::/64 dev eth0 proto kernel metric 256 pref medium\n"
        "default via fe80::1 dev eth0 proto ra metric 1024 pref medium\n"
        "unreachable default dev lo proto kernel metric 4294967295 pref medium\n"
    )
    result = diagnose_destination(table.routes, "2001:db8:5::1")
    assert result.ok
    assert result.selected.discard is None
