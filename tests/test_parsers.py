from pathlib import Path

from routedoctor.engine import diagnose_destination
from routedoctor.parsers import parse_ios, parse_ios6

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
    assert [(r.next_hop, r.admin_distance) for r in ospf] == [("192.0.2.2", 110), ("192.0.2.4", 110)]
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
