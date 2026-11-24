import json
from pathlib import Path

import pytest

from routedoctor.web import run

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def call(request: object) -> dict:
    return json.loads(run(json.dumps(request)))


def test_run_diagnoses_ios_text() -> None:
    out = call(
        {
            "action": "diagnose",
            "format": "auto",
            "destination": "198.51.100.9",
            "table": FIXTURES.joinpath("ios-show-ip-route.txt").read_text(),
        }
    )
    assert out["ok"] and out["passed"]
    assert out["text"].startswith("RouteDoctor diagnosis for 198.51.100.9")
    assert out["result"]["selected"]["prefix"] == "198.51.100.8/29"


def test_run_format_defaults_to_auto() -> None:
    out = call(
        {
            "action": "diagnose",
            "destination": "198.51.100.9",
            "table": FIXTURES.joinpath("ios-show-ip-route.txt").read_text(),
        }
    )
    assert out["ok"]


def test_run_traces_a_snapshot() -> None:
    snapshot = json.loads(EXAMPLES.joinpath("loop-snapshot.json").read_text())
    out = call({"action": "trace", "snapshot": snapshot, "from": "r1", "destination": "203.0.113.9"})
    assert out["ok"] and not out["passed"]
    assert out["result"]["outcome"] == "loop"
    assert out["text"]


def test_run_output_is_sorted_json() -> None:
    raw = run(json.dumps({"action": "nope"}))
    assert raw == json.dumps(json.loads(raw), sort_keys=True)


@pytest.mark.parametrize(
    "raw,error",
    [
        ("not json", "request is not valid JSON"),
        ("[]", "request must be a JSON object"),
        ('{"action": "nope"}', "unknown action: nope"),
        (
            '{"action": "diagnose", "table": "hello", "destination": "192.0.2.1"}',
            "no routes recognised",
        ),
        (
            '{"action": "diagnose", "table": "[{\\"prefix\\": \\"0.0.0.0/0\\", '
            '\\"interface\\": \\"eth0\\"}]", "destination": "not-an-ip"}',
            "does not appear to be an IPv4 or IPv6 address",
        ),
        ("x" * 400_001, "request is larger than 400000 characters"),
        ('{"action": "diagnose", "table": 5, "destination": "192.0.2.1"}', "table must be a string"),
        ('{"action": "diagnose", "table": "x", "destination": 7}', "destination must be a string"),
        ('{"action": "trace", "snapshot": 3}', "snapshot must be an object"),
        (
            '{"action": "trace", "snapshot": {}, "from": 1, "destination": "192.0.2.1"}',
            "from must be a string",
        ),
        (
            '{"action": "diagnose", "table": "x", "destination": "192.0.2.1", "format": "bogus"}',
            "unknown format: bogus",
        ),
    ],
)
def test_run_reports_errors_without_raising(raw: str, error: str) -> None:
    out = json.loads(run(raw))
    assert out["ok"] is False
    assert error in out["error"] and "\n" not in out["error"]


def test_run_never_raises_on_unexpected_types() -> None:
    for raw in [
        '{"action": "diagnose", "table": 5, "destination": 7}',
        '{"action": "trace", "snapshot": 3}',
        "null",
    ]:
        assert json.loads(run(raw))["ok"] is False


def test_run_survives_deep_nesting_and_caps_error_length() -> None:
    out = json.loads(run("[" * 100_000))
    assert out["ok"] is False and "\n" not in out["error"]
    long = json.loads(run(json.dumps({"action": "x" * 5000})))
    assert len(long["error"]) <= 300 and "\n" not in long["error"]
    multi = json.loads(run(json.dumps({"action": "a\n\tb\r\nc"})))
    assert multi["error"] == "unknown action: a b c"
