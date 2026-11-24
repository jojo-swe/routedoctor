import pytest

from routedoctor.cli import main


def test_cli_diagnoses_pasted_ios_text() -> None:
    assert main(["tests/fixtures/ios-show-ip-route.txt", "198.51.100.9"]) == 0


def test_cli_traces_a_snapshot() -> None:
    assert main(["examples/loop-snapshot.json", "203.0.113.9", "--trace-from", "r1"]) == 1


def test_cli_trace_json_output(capsys: pytest.CaptureFixture[str]) -> None:
    main(["examples/loop-snapshot.json", "203.0.113.9", "--trace-from", "r1", "--json"])
    assert '"outcome": "loop"' in capsys.readouterr().out


def test_cli_rejects_unparseable_input() -> None:
    assert main(["pyproject.toml", "192.0.2.1"]) == 2


def test_cli_rejects_format_with_trace() -> None:
    with pytest.raises(SystemExit) as info:
        main(["examples/loop-snapshot.json", "203.0.113.9", "--trace-from", "r1", "--format", "ios"])
    assert info.value.code == 2


def test_cli_forced_format() -> None:
    assert main(["tests/fixtures/ios-show-ip-route.txt", "198.51.100.9", "--format", "ios"]) == 0
