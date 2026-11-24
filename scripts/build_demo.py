"""Rebuild demo/manifest.json from demo/examples/ by running every request.

    python scripts/build_demo.py           rewrite the manifest
    python scripts/build_demo.py --check   exit 1 when the file on disk differs
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import routedoctor
from routedoctor.web import run

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "demo" / "examples"
MANIFEST = ROOT / "demo" / "manifest.json"


def build() -> str:
    examples = []
    for path in sorted(EXAMPLES.glob("*.json")):
        source = json.loads(path.read_text(encoding="utf-8"))
        response = json.loads(run(json.dumps(source["request"])))
        examples.append(
            {
                "id": source["id"],
                "title": source["title"],
                "request": source["request"],
                "response": response,
            }
        )
    manifest = {
        "schema": 1,
        "id": "routedoctor",
        "version": routedoctor.__version__,
        "package": "routedoctor",
        "entry": "routedoctor.web:run",
        "examples": examples,
    }
    return json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the manifest is stale")
    args = parser.parse_args()
    text = build()
    if args.check:
        current = MANIFEST.read_text(encoding="utf-8") if MANIFEST.exists() else None
        if current != text:
            print("demo/manifest.json is stale; run python scripts/build_demo.py", file=sys.stderr)
            return 1
        return 0
    MANIFEST.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
