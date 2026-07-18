"""Command-line interface for RouteDoctor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import diagnose_destination, parse_routes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="routedoctor",
        description="Explain how a routing table forwards a destination.",
    )
    parser.add_argument("snapshot", type=Path, help="JSON file containing a routes array")
    parser.add_argument("destination", help="IPv4 destination to diagnose")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = json.loads(args.snapshot.read_text(encoding="utf-8"))
        items = payload["routes"] if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ValueError("snapshot must be a list or contain a routes list")
        diagnosis = diagnose_destination(parse_routes(items), args.destination)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"routedoctor: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(diagnosis.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"RouteDoctor diagnosis for {diagnosis.destination}")
        print("=" * 52)
        if diagnosis.selected:
            route = diagnosis.selected
            target = route.next_hop or route.interface or "unresolved"
            print(f"Selected: {route.prefix} via {target} [{route.protocol}]")
        else:
            print("Selected: none")
        for finding in diagnosis.findings:
            marker = "!" if finding.startswith("ERROR") else "+"
            print(f"{marker} {finding}")

    return 0 if diagnosis.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
