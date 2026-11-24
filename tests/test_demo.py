import json
import re
from pathlib import Path

import routedoctor
from routedoctor.web import run

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "demo" / "manifest.json"


def test_manifest_responses_are_what_run_returns() -> None:
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["schema"] == 1 and manifest["entry"] == "routedoctor.web:run"
    assert [e["id"] for e in manifest["examples"]] == [
        "campus", "ecmp", "unresolved", "ipv6", "linux", "discard", "trace-delivered",
        "trace-loop"]
    for example in manifest["examples"]:
        assert json.loads(run(json.dumps(example["request"]))) == example["response"], example["id"]
        assert example["response"]["ok"] is True


def test_manifest_version_matches_the_package() -> None:
    assert json.loads(MANIFEST.read_text())["version"] == routedoctor.__version__


def test_manifest_is_small_and_titles_are_short() -> None:
    assert MANIFEST.stat().st_size < 100_000
    for example in json.loads(MANIFEST.read_text())["examples"]:
        assert len(example["title"]) <= 40


def test_ids_are_slugs_and_passed_matches_the_diagnosis() -> None:
    failing = {"unresolved", "discard", "trace-loop"}
    for example in json.loads(MANIFEST.read_text())["examples"]:
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", example["id"]), example["id"]
        assert example["response"]["passed"] is (example["id"] not in failing), example["id"]
