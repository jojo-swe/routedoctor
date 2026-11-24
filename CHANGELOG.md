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
- Discard routes: Linux `blackhole`, `unreachable` and `prohibit` routes and Cisco `Null0` routes
  (including EIGRP `is a summary` routes) win longest-prefix match like any route and make the
  diagnosis fail with "traffic is dropped". JSON routes take an optional `discard` field, and every
  route in the output has one.
- A route with both a next hop and an interface (Linux `via X dev Y`, with or without `onlink`;
  IOS `via X, <age>, <interface>` and fully specified statics; JSON with both fields) leaves
  through that interface without a recursive lookup: "Next hop <hop> is reached through
  <interface>". Only interface-less next hops are resolved recursively.
- Linux `linkdown` routes still win the lookup and report "exit interface <dev> has no carrier
  (linkdown); traffic is dropped"; JSON routes take an optional `linkdown` boolean.
- Linux IPv4 routes via an IPv6 gateway (RFC 5549) are refused with an error naming the line.
- An auto-detected paste of `show ip route` plus `show ipv6 route` is read as one table, format
  `ios+ios6`.
- In a devices snapshot, `addresses` may be the pasted output of `ip addr`.
- `--json` works with `--trace-from` and prints the trace result.
- Next-hop resolution stops after 64 levels with an error.

### Changed

- Route fields are validated more strictly (non-empty text, integer distance and metric), and
  invalid device names in a devices snapshot are rejected. Both exit with code `2`.
- The "less-specific route(s) were ignored" count now counts each prefix once, not each
  equal-cost path.
- Trace delivers only at a device that owns the destination or on a connected route. A route that
  leaves through an interface toward an unknown device ends the trace with `unknown_next_hop`.
- A table with no routes of the destination's IP version says so instead of "no matching route".
- FRR and Quagga output is refused instead of being misread as IOS.
- Linux `dead` multipath next hops are skipped while another next hop works; if none works, the
  route drops traffic like a `linkdown` route.
- Trace delivers on a `local` route only for a host prefix (`/32`, `/128`).
- `active` in a JSON route must be a boolean; `protocol` and `interface` must be 1 to 64 printable
  characters. A leading byte order mark is ignored. Text lines over 2,000 characters are skipped.

## [0.1.0]

- Initial version: longest-prefix match, administrative distance and metric tie-breaking,
  equal-cost paths, recursive next-hop resolution, and detection of unresolved next hops and
  routing loops, for IPv4 JSON snapshots.
