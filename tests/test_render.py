import json
from pathlib import Path

from routedoctor import diagnose_destination, parse_routes
from routedoctor.render import render_diagnosis

ROOT = Path(__file__).resolve().parent.parent

EXPECTED = """\
RouteDoctor diagnosis for 198.51.100.9
====================================================
Selected: 198.51.100.8/29 via 192.0.2.3 [static]
+ Selected 198.51.100.8/29 by longest-prefix match (/29)
+ Next hop 192.0.2.3 resolves through 192.0.2.0/24
+ Recursive resolution terminates on GigabitEthernet0/0
+ 2 less-specific route(s) were ignored, including 198.51.100.0/24"""


def test_render_matches_readme_example() -> None:
    payload = json.loads((ROOT / "examples" / "campus-routing.json").read_text(encoding="utf-8"))
    diagnosis = diagnose_destination(parse_routes(payload["routes"]), "198.51.100.9")

    text = render_diagnosis(diagnosis)

    assert text == EXPECTED
    assert EXPECTED in (ROOT / "README.md").read_text(encoding="utf-8")
