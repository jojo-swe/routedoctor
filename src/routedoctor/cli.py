"""Command-line interface for RouteDoctor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import diagnose_destination
from .parsers import parse_table
from .render import render_diagnosis, render_trace
from .trace import parse_snapshot, trace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="routedoctor",
        description="Explain how a routing table forwards a destination.",
    )
    parser.add_argument(
        "snapshot",
        type=Path,
        help="file with a routing table (JSON, 'show ip route', 'ip route'); "
        "with --trace-from, a devices snapshot (JSON)",
    )
    parser.add_argument("destination", help="IPv4 or IPv6 destination to diagnose")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--format",
        choices=["auto", "json", "ios", "ios6", "linux", "linux6"],
        default="auto",
        help="routing table format (default: auto-detect)",
    )
    parser.add_argument(
        "--trace-from",
        metavar="DEVICE",
        help="trace the destination hop by hop from DEVICE across a devices snapshot",
    )
    return parser


def _load_json(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise
    except ValueError:
        # Python's integer-digit limit; its message suggests changing interpreter settings.
        raise ValueError("a number has too many digits") from None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.trace_from is not None and args.format != "auto":
        parser.error("--format cannot be combined with --trace-from")
    try:
        text = args.snapshot.read_text(encoding="utf-8-sig")
        if args.trace_from is not None:
            result = trace(parse_snapshot(_load_json(text)), args.trace_from, args.destination)
            rendered = render_trace(result)
        else:
            result = diagnose_destination(parse_table(text, args.format).routes, args.destination)
            rendered = render_diagnosis(result)
    except (OSError, ValueError, RecursionError) as exc:
        print(f"routedoctor: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(rendered)

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
