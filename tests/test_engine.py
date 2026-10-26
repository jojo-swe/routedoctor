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


def test_reports_equal_cost_paths() -> None:
    routes = parse_routes(
        [
            {"prefix": "10.0.0.0/8", "protocol": "ospf", "next_hop": "192.0.2.1",
             "admin_distance": 110, "metric": 20},
            {"prefix": "10.0.0.0/8", "protocol": "ospf", "next_hop": "192.0.2.2",
             "admin_distance": 110, "metric": 20},
            {"prefix": "10.0.0.0/8", "protocol": "ospf", "next_hop": "192.0.2.9",
             "admin_distance": 110, "metric": 30},
            {"prefix": "192.0.2.0/24", "interface": "GigabitEthernet0/0"},
        ]
    )

    result = diagnose_destination(routes, "10.1.2.3")

    assert result.ok
    assert [route.next_hop for route in result.equal_cost] == ["192.0.2.1", "192.0.2.2"]
    assert "2 equal-cost paths via 192.0.2.1, 192.0.2.2; showing the first" in result.findings
    assert not any(finding.startswith("Tie broken") for finding in result.findings)
    assert len(result.to_dict()["equal_cost"]) == 2


def test_reports_tie_break_when_costs_differ() -> None:
    routes = parse_routes(
        [
            {"prefix": "10.0.0.0/8", "protocol": "ospf", "next_hop": "192.0.2.1",
             "admin_distance": 110, "metric": 20},
            {"prefix": "10.0.0.0/8", "protocol": "static", "next_hop": "192.0.2.2"},
            {"prefix": "192.0.2.0/24", "interface": "GigabitEthernet0/0"},
        ]
    )

    result = diagnose_destination(routes, "10.1.2.3")

    assert result.equal_cost == []
    assert "Tie broken by administrative distance 1 and metric 0" in result.findings


def test_reports_skipped_inactive_routes() -> None:
    routes = parse_routes(
        [
            {"prefix": "10.0.0.0/8", "next_hop": "192.0.2.1", "active": False},
            {"prefix": "10.1.0.0/16", "next_hop": "192.0.2.2", "active": False},
            {"prefix": "172.16.0.0/12", "next_hop": "192.0.2.3", "active": False},
        ]
    )

    result = diagnose_destination(routes, "10.1.2.3")

    assert not result.ok
    assert result.findings == [
        "ERROR no matching active route; traffic is dropped",
        "2 inactive route(s) for this destination were skipped, including 10.0.0.0/8",
    ]


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
