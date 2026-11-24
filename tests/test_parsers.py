from pathlib import Path

import pytest

from routedoctor.engine import diagnose_destination
from routedoctor.parsers import parse_ios, parse_ios6, parse_ip_addr, parse_linux, parse_table

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_ios_show_ip_route() -> None:
    table = parse_ios(FIXTURES.joinpath("ios-show-ip-route.txt").read_text())
    assert table.format == "ios"
    assert table.addresses == ["192.0.2.10"]
    by_prefix = {(r.prefix, r.next_hop): r for r in table.routes}
    assert by_prefix[("0.0.0.0/0", "192.0.2.1")].protocol == "static"
    assert by_prefix[("198.51.100.0/24", "192.0.2.4")].metric == 20
    assert by_prefix[("192.0.2.0/24", None)].interface == "GigabitEthernet0/0"
    assert len(table.routes) == 5


def test_ios_fixture_reproduces_the_readme_diagnosis() -> None:
    table = parse_ios(FIXTURES.joinpath("ios-show-ip-route.txt").read_text())
    assert diagnose_destination(table.routes, "198.51.100.9").selected.prefix == "198.51.100.8/29"


def test_ios_distances_and_connected_distance_zero() -> None:
    table = parse_ios(FIXTURES.joinpath("ios-show-ip-route.txt").read_text())
    ospf = [r for r in table.routes if r.protocol == "ospf"]
    assert [(r.next_hop, r.admin_distance) for r in ospf] == [
        ("192.0.2.2", 110),
        ("192.0.2.4", 110),
    ]
    connected = next(r for r in table.routes if r.protocol == "connected")
    assert connected.admin_distance == 0


def test_parses_ios_show_ipv6_route_with_link_local_next_hop() -> None:
    table = parse_ios6(FIXTURES.joinpath("ios-show-ipv6-route.txt").read_text())
    ospf = next(r for r in table.routes if r.protocol == "ospf")
    assert (ospf.next_hop, ospf.interface) == (None, "GigabitEthernet0/0")


def test_ios6_prefixes_are_canonical_and_locals_become_addresses() -> None:
    table = parse_ios6(FIXTURES.joinpath("ios-show-ipv6-route.txt").read_text())
    assert table.format == "ios6"
    assert table.addresses == ["2001:db8::a"]
    assert sorted(r.prefix for r in table.routes) == [
        "2001:db8:1:8::/61",
        "2001:db8:1::/48",
        "2001:db8:1::/48",
        "2001:db8::/64",
        "::/0",
    ]
    default = next(r for r in table.routes if r.prefix == "::/0")
    assert (default.protocol, default.next_hop) == ("static", "2001:db8::1")
    assert diagnose_destination(table.routes, "2001:db8:1:8::5").selected.prefix == (
        "2001:db8:1:8::/61"
    )


def test_parses_mask_less_children_of_a_subnetted_header() -> None:
    table = parse_ios(FIXTURES.joinpath("ios-show-ip-route-subnetted.txt").read_text())
    by_prefix = {r.prefix: r for r in table.routes}
    assert sorted(by_prefix) == [
        "192.0.2.0/24",
        "198.51.100.0/24",
        "203.0.113.0/26",
        "203.0.113.64/26",
    ]
    connected = by_prefix["203.0.113.0/26"]
    assert (connected.protocol, connected.next_hop, connected.interface) == (
        "connected",
        None,
        "GigabitEthernet0/1",
    )
    ospf = by_prefix["203.0.113.64/26"]
    assert (ospf.protocol, ospf.next_hop, ospf.interface, ospf.metric) == (
        "ospf",
        "192.0.2.2",
        "GigabitEthernet0/0",
        20,
    )
    assert by_prefix["198.51.100.0/24"].next_hop == "192.0.2.3"
    assert table.addresses == ["192.0.2.10"]


def test_parses_linux_ip_route() -> None:
    table = parse_linux(FIXTURES.joinpath("linux-ip-route.txt").read_text())
    assert table.format == "linux"
    default = next(r for r in table.routes if r.prefix == "0.0.0.0/0")
    assert (default.next_hop, default.interface, default.metric) == ("192.0.2.1", "eth0", 100)
    assert (default.protocol, default.admin_distance) == ("dhcp", 1)
    assert any(r.protocol == "connected" and r.admin_distance == 0 for r in table.routes)
    assert [r.discard for r in table.routes if r.discard] == ["unreachable"]
    assert all(r.active for r in table.routes)
    assert table.addresses == []


def test_linux_static_and_unreachable_routes() -> None:
    table = parse_linux(FIXTURES.joinpath("linux-ip-route.txt").read_text())
    by_prefix = {r.prefix: r for r in table.routes}
    static = by_prefix["198.51.100.0/24"]
    assert (static.protocol, static.next_hop, static.metric, static.active) == (
        "static",
        "192.0.2.4",
        20,
        True,
    )
    blocked = by_prefix["203.0.113.128/25"]
    assert (blocked.active, blocked.discard, blocked.next_hop, blocked.interface) == (
        True,
        "unreachable",
        None,
        None,
    )


def test_parses_linux_ip_6_route() -> None:
    table = parse_linux(FIXTURES.joinpath("linux-ip-6-route.txt").read_text())
    assert table.format == "linux6"
    by_prefix = {r.prefix: r for r in table.routes}
    default = by_prefix["::/0"]
    assert (default.next_hop, default.interface, default.protocol) == (
        "2001:db8:ffff::1",
        "eth0",
        "ra",
    )
    assert by_prefix["fe80::/64"].protocol == "connected"
    dead = by_prefix["2001:db8:dead::/48"]
    assert (dead.active, dead.discard, dead.interface) == (True, "unreachable", "lo")
    assert len(table.routes) == 5


def test_linux_multipath_nexthops_become_equal_cost_routes() -> None:
    text = (
        "default proto static metric 100\n"
        "\tnexthop via 192.0.2.1 dev eth0 weight 1\n"
        "\tnexthop via 192.0.2.2 dev eth1 weight 1\n"
    )
    table = parse_linux(text)
    assert [(r.prefix, r.next_hop, r.interface, r.metric) for r in table.routes] == [
        ("0.0.0.0/0", "192.0.2.1", "eth0", 100),
        ("0.0.0.0/0", "192.0.2.2", "eth1", 100),
    ]


def test_linux_skips_lines_it_cannot_read() -> None:
    text = "default via not-an-address dev eth0\n192.0.2.0/24 dev eth0 metric abc\n"
    assert parse_linux(text).routes == []


def test_parse_ip_addr_skips_link_local() -> None:
    assert parse_ip_addr(FIXTURES.joinpath("linux-ip-addr.txt").read_text()) == [
        "192.0.2.10",
        "2001:db8:ffff::10",
    ]


@pytest.mark.parametrize(
    "name,expected",
    [
        ("ios-show-ip-route.txt", "ios"),
        ("ios-show-ip-route-subnetted.txt", "ios"),
        ("ios-show-ipv6-route.txt", "ios6"),
        ("linux-ip-route.txt", "linux"),
        ("linux-ip-6-route.txt", "linux6"),
    ],
)
def test_auto_detects_format(name: str, expected: str) -> None:
    table = parse_table(FIXTURES.joinpath(name).read_text())
    assert table.format == expected
    assert table.routes


def test_auto_accepts_json() -> None:
    table = parse_table(Path("examples/campus-routing.json").read_text())
    assert table.format == "json"
    assert table.routes
    assert table.addresses == []


def test_auto_accepts_json_object_with_routes() -> None:
    table = parse_table('{"routes": [{"prefix": "192.0.2.0/24", "interface": "eth0"}]}')
    assert (table.format, [r.prefix for r in table.routes]) == ("json", ["192.0.2.0/24"])


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello world",
        "<html><body>x</body></html>",
        '{"a": 1}',
        "[]",
        '{"routes": []}',
        '{"routes": 5}',
        "null",
        "[1,2]",
        '["a"]',
        "[" * 100_000,
        "Please add a route for 192.0.2.0/24 via the gateway.",
        "Gateway of last resort is 192.0.2.1 to network 0.0.0.0",
        "Hello 192.0.2.1 is up",
        "S 192.0.2.1 is the router",
        "default via the gateway",
        "default dev",
        "192.0.2.0/24 devices are listed below",
        "ip route shows 2001:db8::/32 dev eth0 here",
    ],
)
def test_unrecognised_text_is_a_value_error(text: str) -> None:
    with pytest.raises(ValueError, match="no routes recognised"):
        parse_table(text)


def test_oversized_text_is_refused() -> None:
    with pytest.raises(ValueError, match="larger than 200000"):
        parse_table("x" * 200_001)
    with pytest.raises(ValueError, match="larger than 200000"):
        parse_table("x" * 200_001, format="linux")


def test_invalid_json_routes_report_the_bad_route() -> None:
    with pytest.raises(ValueError, match="invalid route at index 0"):
        parse_table('[{"prefix": "not-a-prefix"}]')


@pytest.mark.parametrize(
    "name,forced",
    [
        ("ios-show-ip-route.txt", "ios"),
        ("ios-show-ipv6-route.txt", "ios6"),
        ("linux-ip-route.txt", "linux"),
        ("linux-ip-6-route.txt", "linux6"),
    ],
)
def test_forced_format_uses_that_parser(name: str, forced: str) -> None:
    assert parse_table(FIXTURES.joinpath(name).read_text(), format=forced).format == forced


def test_forced_json_format() -> None:
    table = parse_table(Path("examples/campus-routing.json").read_text(), format="json")
    assert table.format == "json"


def test_forced_parser_that_finds_nothing_is_a_value_error() -> None:
    linux_text = FIXTURES.joinpath("linux-ip-route.txt").read_text()
    with pytest.raises(ValueError, match="no routes recognised"):
        parse_table(linux_text, format="ios")
    with pytest.raises(ValueError, match="no routes recognised"):
        parse_table("not json", format="json")


def test_unknown_format_name_is_a_value_error() -> None:
    with pytest.raises(ValueError, match="^unknown format: cisco$"):
        parse_table("default via 192.0.2.1 dev eth0", format="cisco")


def test_ios_keeps_routes_with_trailing_whitespace() -> None:
    text = (
        "S*    0.0.0.0/0 [1/0] via 192.0.2.1   \n"
        "O        198.51.100.0/24 [110/20] via 192.0.2.2   \n"
        "                         [110/20] via 192.0.2.4   \n"
    )
    table = parse_ios(text)
    assert [(r.prefix, r.next_hop) for r in table.routes] == [
        ("0.0.0.0/0", "192.0.2.1"),
        ("198.51.100.0/24", "192.0.2.2"),
        ("198.51.100.0/24", "192.0.2.4"),
    ]


def test_ios_skips_malformed_prefixes_and_next_hops() -> None:
    text = (
        "S        192.0.2.0/99 [1/0] via 192.0.2.1\n"
        "S        999.0.2.0/24 [1/0] via 192.0.2.1\n"
        "S        198.51.100.0/24 [1/0] via 999.0.2.1\n"
        "S        198.51.100.8/29 [1/0] via 192.0.2.3\n"
    )
    assert [(r.prefix, r.next_hop) for r in parse_ios(text).routes] == [
        ("198.51.100.8/29", "192.0.2.3")
    ]
    bad6 = (
        "S   2001:DB8:1::/200 [1/0]\n     via 2001:DB8::1\n"
        "S   2001:DB8:2::/48 [1/0]\n     via 2001:DB8::3\n"
    )
    assert [r.prefix for r in parse_ios6(bad6).routes] == ["2001:db8:2::/48"]


def test_ios_reads_sub_codes_and_other_protocols() -> None:
    text = (
        "O IA     198.51.100.0/24 [110/30] via 192.0.2.2, 00:01:00, GigabitEthernet0/0\n"
        "O E2     203.0.113.0/24 [110/20] via 192.0.2.2, 00:01:00, GigabitEthernet0/0\n"
        "B        192.0.2.64/26 [20/0] via 192.0.2.5, 1d02h\n"
        "D        192.0.2.128/26 [90/3072] via 192.0.2.6, 00:00:09, GigabitEthernet0/1\n"
    )
    got = [(r.protocol, r.admin_distance, r.metric) for r in parse_ios(text).routes]
    assert got == [("ospf", 110, 30), ("ospf", 110, 20), ("bgp", 20, 0), ("eigrp", 90, 3072)]


def test_ios_attaches_interface_from_a_wrapped_line() -> None:
    text = (
        "O        198.51.100.0/24 [110/20] via 192.0.2.2, 00:10:21,\n"
        "         GigabitEthernet0/0\n"
        "S        198.51.100.8/29 [1/0] via 192.0.2.3\n"
    )
    routes = parse_ios(text).routes
    assert [(r.next_hop, r.interface) for r in routes] == [
        ("192.0.2.2", "GigabitEthernet0/0"),
        ("192.0.2.3", None),
    ]


def test_ios_mask_less_line_after_own_length_under_subnetted_header_is_skipped() -> None:
    text = (
        "      203.0.113.0/26 is subnetted, 2 subnets\n"
        "C        203.0.113.0 is directly connected, GigabitEthernet0/1\n"
        "C        198.51.100.0/24 is directly connected, GigabitEthernet0/2\n"
        "C        192.0.2.0 is directly connected, GigabitEthernet0/3\n"
    )
    assert [r.prefix for r in parse_ios(text).routes] == ["203.0.113.0/26", "198.51.100.0/24"]


def test_linux_link_local_next_hop_keeps_only_the_interface() -> None:
    table = parse_linux("default via fe80::1 dev eth0 proto ra metric 1024 pref medium\n")
    assert table.format == "linux6"
    (route,) = table.routes
    assert (route.prefix, route.next_hop, route.interface) == ("::/0", None, "eth0")


def test_ios_table_with_one_malformed_line_still_parses() -> None:
    text = FIXTURES.joinpath("ios-show-ip-route.txt").read_text()
    text += "S        198.51.100.256/24 [1/0] via 192.0.2.1\n"
    table = parse_table(text)
    assert table.format == "ios"
    assert len(table.routes) == 5


def _indent(text: str, prefix: str) -> str:
    return "".join(prefix + line if line.strip() else line for line in text.splitlines(True))


@pytest.mark.parametrize(
    "name,prefix,expected",
    [
        ("linux-ip-route.txt", "  ", "linux"),
        ("linux-ip-6-route.txt", "\t", "linux6"),
        ("ios-show-ip-route.txt", "    ", "ios"),
        ("ios-show-ip-route-subnetted.txt", "    ", "ios"),
        ("ios-show-ipv6-route.txt", "    ", "ios6"),
    ],
)
def test_indented_and_crlf_pastes_match_the_plain_table(
    name: str, prefix: str, expected: str
) -> None:
    plain = FIXTURES.joinpath(name).read_text()
    for variant in (_indent(plain, prefix), plain.replace("\n", "\r\n")):
        table = parse_table(variant)
        assert table.format == expected
        assert table.routes == parse_table(plain).routes


def test_indented_linux_multipath_keeps_nexthop_lines() -> None:
    text = (
        "    default proto static metric 100\n"
        "        nexthop via 192.0.2.1 dev eth0 weight 1\n"
        "        nexthop via 192.0.2.2 dev eth1 weight 1\n"
    )
    assert [r.next_hop for r in parse_table(text).routes] == ["192.0.2.1", "192.0.2.2"]


def test_linux_trailing_whitespace_is_ignored() -> None:
    text = "default via 192.0.2.1 dev eth0 metric 100   \t\n192.0.2.0/24 dev eth0 proto kernel \n"
    table = parse_table(text)
    assert [(r.prefix, r.interface) for r in table.routes] == [
        ("0.0.0.0/0", "eth0"),
        ("192.0.2.0/24", "eth0"),
    ]


def test_linux_unreachable_default_is_a_discard_default() -> None:
    text = (
        "2001:db8:ffff::/64 dev eth0 proto kernel metric 256 pref medium\n"
        "unreachable default dev lo metric 4278198272 pref medium\n"
    )
    table = parse_table(text)
    blocked = next(r for r in table.routes if r.prefix == "::/0")
    assert (blocked.active, blocked.discard, blocked.metric) == (True, "unreachable", 4278198272)
    v4 = parse_linux("unreachable default metric 5\n192.0.2.0/24 dev eth0\n")
    assert [(r.prefix, r.discard) for r in v4.routes] == [
        ("0.0.0.0/0", "unreachable"),
        ("192.0.2.0/24", None),
    ]


def test_linux_negative_metric_line_is_skipped() -> None:
    table = parse_linux("192.0.2.0/24 dev eth0 metric -5\n198.51.100.0/24 dev eth1\n")
    assert [r.prefix for r in table.routes] == ["198.51.100.0/24"]


def test_forced_linux_on_ipv6_only_text_reports_linux6() -> None:
    text = FIXTURES.joinpath("linux-ip-6-route.txt").read_text()
    assert parse_table(text, format="linux").format == "linux6"


def test_ios_summary_to_null0_is_parsed_as_a_discard_route() -> None:
    (route,) = parse_ios("D        203.0.113.192/26 is a summary, 00:12:01, Null0\n").routes
    assert (route.prefix, route.protocol, route.interface, route.discard) == (
        "203.0.113.192/26",
        "eigrp",
        "Null0",
        "Null0",
    )
    assert route.admin_distance == 5


def test_ios_null_with_a_space_is_null0() -> None:
    (route,) = parse_ios("S     203.0.113.0/24 is directly connected, Null 0\n").routes
    assert (route.interface, route.discard) == ("Null0", "Null0")


def test_linux_kernel_discard_route_is_not_connected() -> None:
    (route,) = parse_linux("unreachable default dev lo proto kernel metric 4294967295\n").routes
    assert (route.protocol, route.admin_distance, route.discard) == ("kernel", 1, "unreachable")
