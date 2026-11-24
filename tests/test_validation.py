"""Input validation and small robustness rules (finding 8 and the minor findings)."""

import json
from pathlib import Path

import pytest

from routedoctor import parse_routes, parse_snapshot, parse_table, trace
from routedoctor.cli import main
from routedoctor.render import render_trace
from routedoctor.web import run

FIXTURES = Path(__file__).parent / "fixtures"
IP_ADDR = FIXTURES.joinpath("linux-ip-addr.txt").read_text()


def test_snapshot_addresses_accept_ip_addr_text() -> None:
    (device,) = parse_snapshot(
        {
            "devices": [
                {
                    "name": "h",
                    "addresses": IP_ADDR,
                    "table": "default via 192.0.2.1 dev eth0\n192.0.2.0/24 dev eth0 proto kernel\n",
                }
            ]
        }
    )
    assert device.addresses == ["192.0.2.10", "2001:db8:ffff::10"]


def test_ip_addr_text_lets_trace_find_a_linux_device() -> None:
    devices = parse_snapshot(
        {
            "devices": [
                {
                    "name": "r1",
                    "addresses": ["192.0.2.1"],
                    "routes": [{"prefix": "0.0.0.0/0", "next_hop": "192.0.2.10", "interface": "e0"}],
                },
                {
                    "name": "h",
                    "addresses": IP_ADDR,
                    "table": "203.0.113.0/24 dev eth1 proto kernel scope link\n",
                },
            ]
        }
    )
    result = trace(devices, "r1", "203.0.113.7")
    assert (result.outcome, result.detail) == ("delivered", "h")


def test_snapshot_addresses_text_without_inet_lines_is_an_error() -> None:
    with pytest.raises(ValueError, match="device r1: addresses text has no inet or inet6 lines"):
        parse_snapshot({"devices": [{"name": "r1", "routes": [], "addresses": "192.0.2.1"}]})


def test_snapshot_addresses_of_another_type_are_an_error() -> None:
    with pytest.raises(ValueError, match="device r1: addresses must be a list or 'ip addr' text"):
        parse_snapshot({"devices": [{"name": "r1", "routes": [], "addresses": 5}]})


def test_parse_table_strips_a_byte_order_mark() -> None:
    table = parse_table("﻿S    198.51.100.0/24 [1/0] via 192.0.2.1\n")
    assert [route.prefix for route in table.routes] == ["198.51.100.0/24"]


def test_web_run_strips_a_byte_order_mark() -> None:
    request = {"action": "diagnose", "table": "default dev eth0\n", "destination": "192.0.2.1"}
    out = json.loads(run("﻿" + json.dumps(request)))
    assert out["ok"] is True


def test_cli_reads_files_with_a_byte_order_mark(tmp_path: Path) -> None:
    path = tmp_path / "table.json"
    path.write_text('[{"prefix": "0.0.0.0/0", "interface": "eth0"}]', encoding="utf-8-sig")
    assert main([str(path), "192.0.2.1"]) == 0
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(Path("examples/loop-snapshot.json").read_text(), encoding="utf-8-sig")
    assert main([str(snapshot), "203.0.113.9", "--trace-from", "r1"]) == 1


@pytest.mark.parametrize("key", ["interface", "protocol"])
@pytest.mark.parametrize("value", ["e0\n+ fake line", "x" * 65, "e\x000", "e\t0"])
def test_route_text_fields_must_be_short_printable_single_lines(key: str, value: str) -> None:
    route = {"prefix": "192.0.2.0/24", "interface": "eth0", key: value}
    with pytest.raises(ValueError, match=f"invalid route at index 0: {key} must be 1 to 64"):
        parse_routes([route])


def test_route_text_fields_of_64_characters_are_accepted() -> None:
    (route,) = parse_routes([{"prefix": "192.0.2.0/24", "interface": "x" * 64, "protocol": "y"}])
    assert route.interface == "x" * 64


@pytest.mark.parametrize("value", ["false", 0, 1, None, []])
def test_active_must_be_a_boolean(value: object) -> None:
    with pytest.raises(ValueError, match="invalid route at index 0: active must be true or false"):
        parse_routes([{"prefix": "192.0.2.0/24", "interface": "eth0", "active": value}])


def test_missing_prefix_error_names_the_field() -> None:
    with pytest.raises(ValueError, match="^invalid route at index 0: prefix is required$"):
        parse_routes([{"interface": "eth0"}])


def test_non_object_route_error() -> None:
    with pytest.raises(ValueError, match="^invalid route at index 1: route must be an object$"):
        parse_routes([{"prefix": "192.0.2.0/24", "interface": "eth0"}, 5])


def test_snapshot_with_non_object_routes_reports_the_route() -> None:
    with pytest.raises(ValueError, match="device a: invalid route at index 0: route must be an"):
        parse_snapshot({"devices": [{"name": "a", "addresses": ["192.0.2.1"], "routes": [1]}]})


def test_huge_ios_numbers_do_not_leak_the_int_limit_message() -> None:
    table = "S 0.0.0.0/0 [" + "9" * 5000 + "/0] via 192.0.2.1\n"
    out = json.loads(run(json.dumps({"action": "diagnose", "table": table, "destination": "::1"})))
    assert out["ok"] is False
    assert "set_int_max_str_digits" not in out["error"]
    assert "Exceeds the limit" not in out["error"]


def test_huge_ios_distance_skips_the_line() -> None:
    table = parse_table(
        "S    0.0.0.0/0 [99999999999/0] via 192.0.2.1\nS    198.51.100.0/24 [1/0] via 192.0.2.1\n"
    )
    assert [route.prefix for route in table.routes] == ["198.51.100.0/24"]


def test_cli_huge_json_integer_does_not_leak_the_int_limit_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "snapshot.json"
    path.write_text('{"devices": [{"name": "a", "x": ' + "9" * 5000 + "}]}")
    assert main([str(path), "192.0.2.1", "--trace-from", "a"]) == 2
    err = capsys.readouterr().err
    assert "set_int_max_str_digits" not in err
    assert "a number has too many digits" in err


def test_trace_to_a_device_address_without_a_route_shows_ownership() -> None:
    devices = parse_snapshot(
        {
            "devices": [
                {
                    "name": "a",
                    "addresses": ["192.0.2.1"],
                    "routes": [{"prefix": "198.51.100.0/24", "interface": "e0"}],
                }
            ]
        }
    )
    lines = render_trace(trace(devices, "a", "192.0.2.1")).splitlines()
    assert lines[1:] == ["[1] a: owns 192.0.2.1", "+ delivered at a"]
