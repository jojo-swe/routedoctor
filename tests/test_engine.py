from routedoctor import diagnose_destination, parse_routes


def test_prefers_longest_prefix_then_admin_distance_and_metric() -> None:
    routes = parse_routes(
        [
            {"prefix": "0.0.0.0/0", "next_hop": "192.0.2.1", "admin_distance": 1},
            {"prefix": "10.0.0.0/8", "next_hop": "192.0.2.2", "admin_distance": 110},
            {"prefix": "10.1.0.0/16", "next_hop": "192.0.2.3", "admin_distance": 20},
            {"prefix": "192.0.2.0/24", "interface": "GigabitEthernet0/0"},
        ]
    )

    result = diagnose_destination(routes, "10.1.2.3")

    assert result.ok
    assert result.selected is not None
    assert result.selected.prefix == "10.1.0.0/16"
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


def test_detects_recursive_loop() -> None:
    routes = parse_routes(
        [
            {"prefix": "10.0.0.0/8", "next_hop": "192.0.2.1"},
            {"prefix": "192.0.2.1/32", "next_hop": "198.51.100.1"},
            {"prefix": "198.51.100.1/32", "next_hop": "192.0.2.1"},
        ]
    )

    result = diagnose_destination(routes, "10.10.10.10")

    assert not result.ok
    assert any("recursive routing loop" in finding for finding in result.findings)
