# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-11-24

### Added

- IPv6 support: IPv6 prefixes, next hops and destinations. A next hop must be in the same
  address family as its prefix.
- Text parsers for Cisco IOS (`show ip route`, `show ipv6 route`) and Linux (`ip route`,
  `ip -6 route`), with automatic format detection and a `--format` option to force a parser.
- `parse_table` in the Python API, returning the routes and the addresses a device owns.
- Multi-device trace: `--trace-from DEVICE` follows a destination across a devices snapshot and
  reports delivery, black holes, loops, unknown next hops and the hop limit. Python API:
  `parse_snapshot` and `trace`.
- `render_diagnosis` and `render_trace` in the Python API.
- `routedoctor.web.run`, a JSON-in, JSON-out entry point for the browser demo.
- `demo/manifest.json` and `scripts/build_demo.py` to build and check the demo examples.
- CI runs an IOS fixture and the loop trace.

### Changed

- Route fields are validated more strictly (non-empty text, integer distance and metric), and
  invalid device names in a devices snapshot are rejected. Both exit with code `2`.

## [0.1.0]

- Initial version: longest-prefix match, administrative distance and metric tie-breaking,
  equal-cost paths, recursive next-hop resolution, and detection of unresolved next hops and
  routing loops, for IPv4 JSON snapshots.
