import importlib
import json
from pathlib import Path

import pytest

from routedoctor.engine import Route, parse_routes
from routedoctor.parsers import ParsedTable
from routedoctor.render import render_trace
from routedoctor.trace import Device, parse_snapshot, trace

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> list[Device]:
    return parse_snapshot(json.loads(Path("examples", name).read_text()))


def test_trace_delivers_across_devices() -> None:
    result = trace(load("campus-snapshot.json"), "edge", "198.51.100.9")
    assert result.outcome == "delivered"
    assert [hop.device for hop in result.hops] == ["edge", "core", "dist"]
    assert result.detail == "dist"
    assert result.ok


def test_trace_detects_loop_between_devices() -> None:
    result = trace(load("loop-snapshot.json"), "r1", "203.0.113.9")
    assert (result.outcome, result.detail) == ("loop", "r1 -> r2 -> r1")
    assert not result.ok


def test_trace_reports_blackhole() -> None:
    devices = [
        Device(
            "solo", parse_routes([{"prefix": "192.0.2.0/24", "interface": "eth0"}]), ["192.0.2.1"]
        )
    ]
    result = trace(devices, "solo", "203.0.113.9")
    assert result.outcome == "blackhole"
    assert result.detail == "solo: no matching active route; traffic is dropped"


def test_trace_reports_unknown_next_hop() -> None:
    devices = [
        Device(
            "solo",
            parse_routes(
                [
                    {"prefix": "0.0.0.0/0", "next_hop": "192.0.2.254"},
                    {"prefix": "192.0.2.0/24", "interface": "eth0"},
                ]
            ),
            ["192.0.2.1"],
        )
    ]
    result = trace(devices, "solo", "203.0.113.9")
    assert result.outcome == "unknown_next_hop"
    assert result.detail == "solo: no device owns 192.0.2.254"


def test_trace_refuses_devices_without_addresses() -> None:
    devices = [Device("solo", parse_routes([{"prefix": "0.0.0.0/0", "interface": "eth0"}]), [])]
    with pytest.raises(ValueError, match="device solo has no addresses"):
        trace(devices, "solo", "203.0.113.9")


def test_trace_delivers_on_a_connected_interface() -> None:
    result = trace(load("campus-snapshot.json"), "edge", "192.0.2.6")
    assert (result.outcome, result.detail) == ("delivered", "core")


def test_trace_delivers_when_destination_is_a_device_address() -> None:
    # The only route is unresolved, so the diagnosis alone would be a blackhole.
    devices = [
        Device(
            "solo",
            parse_routes([{"prefix": "0.0.0.0/0", "next_hop": "192.0.2.254"}]),
            ["203.0.113.1"],
        )
    ]
    result = trace(devices, "solo", "203.0.113.1")
    assert (result.outcome, result.detail) == ("delivered", "solo")


def test_trace_stops_at_hop_limit() -> None:
    result = trace(load("campus-snapshot.json"), "edge", "198.51.100.9", max_hops=2)
    assert (result.outcome, result.detail) == ("hop_limit", "gave up after 2 hops")
    assert [hop.device for hop in result.hops] == ["edge", "core"]


def test_trace_rejects_bad_inputs() -> None:
    devices = load("campus-snapshot.json")
    with pytest.raises(ValueError, match="unknown start device nowhere"):
        trace(devices, "nowhere", "198.51.100.9")
    with pytest.raises(ValueError, match="duplicate device name edge"):
        trace([devices[0], devices[0]], "edge", "198.51.100.9")
    clash = Device("clash", [], ["192.0.2.1"])
    with pytest.raises(ValueError, match="192.0.2.1 is owned by both edge and clash"):
        trace([devices[0], clash], "edge", "198.51.100.9")


def test_trace_across_two_ipv6_devices() -> None:
    devices = [
        Device(
            "a",
            parse_routes(
                [
                    {"prefix": "2001:db8:1::/64", "interface": "eth0"},
                    {"prefix": "::/0", "next_hop": "2001:db8:1::2"},
                ]
            ),
            ["2001:db8:1::1"],
        ),
        Device(
            "b",
            parse_routes([{"prefix": "2001:db8:2::/64", "interface": "eth1"}]),
            ["2001:db8:1::2"],
        ),
    ]
    result = trace(devices, "a", "2001:db8:2::9")
    assert result.outcome == "delivered"
    assert [hop.device for hop in result.hops] == ["a", "b"]


def test_ipv6_ownership_matches_canonical_forms() -> None:
    devices = parse_snapshot(
        {
            "devices": [
                {
                    "name": "a",
                    "addresses": ["2001:DB8:1::1"],
                    "routes": [
                        {"prefix": "2001:db8:1::/64", "interface": "eth0"},
                        {"prefix": "::/0", "next_hop": "2001:db8:1:0::2"},
                    ],
                },
                {"name": "b", "addresses": ["2001:DB8:1::2"], "routes": []},
            ]
        }
    )
    assert devices[1].addresses == ["2001:db8:1::2"]
    result = trace(devices, "a", "2001:db8:9::1")
    assert [hop.device for hop in result.hops] == ["a", "b"]


def test_snapshot_accepts_ios_text_and_reads_local_addresses() -> None:
    text = FIXTURES.joinpath("ios-show-ip-route.txt").read_text()
    (device,) = parse_snapshot({"devices": [{"name": "r1", "table": text}]})
    assert device.addresses == ["192.0.2.10"]


def test_snapshot_merges_declared_and_parsed_addresses() -> None:
    text = FIXTURES.joinpath("ios-show-ip-route.txt").read_text()
    (device,) = parse_snapshot(
        {"devices": [{"name": "r1", "table": text, "addresses": ["192.0.2.10", "192.0.2.99"]}]}
    )
    assert device.addresses == ["192.0.2.10", "192.0.2.99"]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "snapshot must be a JSON object"),
        ({}, "snapshot needs a devices list"),
        ({"devices": {}}, "snapshot needs a devices list"),
        ({"devices": [{"routes": []}]}, "device 0 needs a name"),
        ({"devices": [{"name": 5, "routes": []}]}, "device 0 needs a name"),
        ({"devices": [{"name": "r1"}]}, "device r1 needs routes or table"),
        (
            {"devices": [{"name": "r1", "routes": [], "table": "x"}]},
            "device r1 has both routes and table",
        ),
        ({"devices": [{"name": "r1", "routes": {}}]}, "device r1: routes must be a list"),
        ({"devices": [{"name": "r1", "table": 3}]}, "device r1: table must be a string"),
        ({"devices": [{"name": "r1", "table": "nonsense"}]}, "device r1: no routes recognised"),
        (
            {"devices": [{"name": "r1", "routes": [], "addresses": "192.0.2.1"}]},
            "device r1: addresses must be a list",
        ),
        (
            {"devices": [{"name": "r1", "routes": [], "addresses": [7]}]},
            "device r1: address 7 is not a string",
        ),
        (
            {"devices": [{"name": "r1", "routes": [], "addresses": ["not-an-ip"]}]},
            "device r1: address not-an-ip is not an IP address",
        ),
        (
            {"devices": [{"name": "r1", "routes": [{"interface": "eth0"}]}]},
            "device r1: invalid route at index 0",
        ),
    ],
)
def test_snapshot_shape_errors(payload: object, message: str) -> None:
    with pytest.raises(ValueError, match=message) as info:
        parse_snapshot(payload)  # type: ignore[arg-type]
    assert "\n" not in str(info.value)


def test_trace_to_dict_shape() -> None:
    data = trace(load("loop-snapshot.json"), "r1", "203.0.113.9").to_dict()
    assert list(data) == ["start", "destination", "ok", "outcome", "detail", "hops"]
    assert data["ok"] is False
    assert [hop["device"] for hop in data["hops"]] == ["r1", "r2"]
    assert data["hops"][0]["diagnosis"]["selected"]["prefix"] == "203.0.113.0/24"
    json.dumps(data)


def test_render_trace_lists_every_hop_and_the_outcome() -> None:
    text = render_trace(trace(load("loop-snapshot.json"), "r1", "203.0.113.9"))
    assert text.splitlines()[0] == "RouteDoctor trace from r1 to 203.0.113.9"
    assert text.splitlines()[-1] == "! loop: r1 -> r2 -> r1"
    assert "[1] r1: 203.0.113.0/24 via 192.0.2.2" in text


def test_render_trace_delivered() -> None:
    text = render_trace(trace(load("campus-snapshot.json"), "edge", "198.51.100.9"))
    assert text.splitlines()[-1] == "+ delivered at dist"
    assert text.splitlines()[-2] == "[3] dist: 198.51.100.0/24 via GigabitEthernet0/1"


def test_trace_survives_a_route_without_a_usable_chain() -> None:
    # Built by hand, bypassing parse_routes: a falsy next hop leaves the chain empty.
    route = Route("0.0.0.0/0", next_hop="", interface="eth0")
    result = trace([Device("solo", [route], ["192.0.2.1"])], "solo", "203.0.113.9")
    assert result.outcome == "delivered"


def test_trace_reaches_hop_limit_on_a_three_device_chain() -> None:
    lan = {"prefix": "192.0.2.0/24", "interface": "eth0"}
    devices = [
        Device(
            "a",
            parse_routes([lan, {"prefix": "0.0.0.0/0", "next_hop": "192.0.2.2"}]),
            ["192.0.2.1"],
        ),
        Device(
            "b",
            parse_routes([lan, {"prefix": "0.0.0.0/0", "next_hop": "192.0.2.3"}]),
            ["192.0.2.2"],
        ),
        Device("c", parse_routes([{"prefix": "0.0.0.0/0", "interface": "eth0"}]), ["192.0.2.3"]),
    ]
    result = trace(devices, "a", "203.0.113.9", max_hops=1)
    assert (result.outcome, result.detail) == ("hop_limit", "gave up after 1 hops")


@pytest.mark.parametrize("name", ["", "x" * 65, "r1\nr2", "r\x001", "r1\x7f"])
def test_snapshot_rejects_unusable_device_names(name: str) -> None:
    with pytest.raises(ValueError, match="device 0 needs a name") as info:
        parse_snapshot({"devices": [{"name": name, "routes": []}]})
    assert "\n" not in str(info.value)


def test_snapshot_survives_infinite_route_numbers() -> None:
    payload = json.loads(
        '{"devices": [{"name": "r1", "routes": [{"prefix": "0.0.0.0/0", "metric": 1e999}]}]}'
    )
    with pytest.raises(ValueError, match="device r1: invalid route at index 0"):
        parse_snapshot(payload)


def test_snapshot_deduplicates_addresses_within_a_table(monkeypatch: pytest.MonkeyPatch) -> None:
    table = ParsedTable(
        "json", parse_routes([{"prefix": "192.0.2.0/24", "interface": "e"}]), ["192.0.2.1"] * 2
    )
    monkeypatch.setattr(
        importlib.import_module("routedoctor.trace"), "parse_table", lambda _t: table
    )
    (device,) = parse_snapshot({"devices": [{"name": "r1", "table": "ignored"}]})
    assert device.addresses == ["192.0.2.1"]
