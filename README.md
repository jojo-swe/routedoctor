<p align="center"><img src=".github/assets/logo.svg" alt="routedoctor logo" width="128"></p>

# RouteDoctor

[![CI](https://github.com/jojo-swe/routedoctor/actions/workflows/ci.yml/badge.svg)](https://github.com/jojo-swe/routedoctor/actions/workflows/ci.yml)

RouteDoctor explains **why a routing table selects a path** and highlights common forwarding failures before they become long troubleshooting sessions.

It works on offline data: JSON snapshots, or text pasted from `show ip route`, `show ipv6 route`, `ip route` and `ip -6 route`. It never connects to a device, so it is safe to use in CI, labs, incident reviews, and sanitized production exports. It handles IPv4 and IPv6, and can follow a destination hop by hop across several devices.

A browser demo is planned at https://johnjohansson.com/lab/routedoctor/. It is not live yet.

## What it diagnoses

- longest-prefix match
- administrative-distance and metric tie-breaking
- equal-cost paths (ECMP) sharing the best prefix, distance, and metric
- recursive next-hop resolution
- unresolved next hops
- recursive routing loops
- missing routes, and inactive routes that were skipped
- routes with no usable next hop or exit interface
- less-specific routes shadowed by a more-specific prefix
- forwarding across several devices: delivery, black holes, loops, and next hops no device owns

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

routedoctor examples/campus-routing.json 198.51.100.9
# or: python -m routedoctor examples/campus-routing.json 198.51.100.9
```

Example output:

```text
RouteDoctor diagnosis for 198.51.100.9
====================================================
Selected: 198.51.100.8/29 via 192.0.2.3 [static]
+ Selected 198.51.100.8/29 by longest-prefix match (/29)
+ Next hop 192.0.2.3 resolves through 192.0.2.0/24
+ Recursive resolution terminates on GigabitEthernet0/0
+ 2 less-specific route(s) were ignored, including 198.51.100.0/24
```

When something is wrong, findings are marked `!` and the command exits `1`:

```bash
routedoctor examples/unresolved-next-hop.json 203.0.113.9
```

```text
RouteDoctor diagnosis for 203.0.113.9
====================================================
Selected: 203.0.113.0/24 via 198.51.100.1 [static]
+ Selected 203.0.113.0/24 by longest-prefix match (/24)
! ERROR next hop 198.51.100.1 is unresolved
+ 1 inactive route(s) for this destination were skipped, including 0.0.0.0/0
```

## Input formats

RouteDoctor reads four kinds of input. By default it detects which one it was given. `--format`
forces one parser:

| `--format` | Input |
|------------|-------|
| `json` | a JSON snapshot (see below) |
| `ios` | Cisco IOS `show ip route` |
| `ios6` | Cisco IOS `show ipv6 route` |
| `linux` | Linux `ip route` |
| `linux6` | Linux `ip -6 route` |
| `auto` | detect from the content (default) |

IOS and Linux are the only text formats. Pasted text may be indented as a block; RouteDoctor removes
the common indentation. Input is limited to 200,000 characters.

```bash
routedoctor tests/fixtures/ios-show-ip-route.txt 198.51.100.9
```

```text
RouteDoctor diagnosis for 198.51.100.9
====================================================
Selected: 198.51.100.8/29 via 192.0.2.3 [static]
+ Selected 198.51.100.8/29 by longest-prefix match (/29)
+ Next hop 192.0.2.3 resolves through 192.0.2.0/24
+ Recursive resolution terminates on GigabitEthernet0/0
+ 3 less-specific route(s) were ignored, including 198.51.100.0/24
```

Destinations can be IPv6. This is `show ipv6 route` output:

```bash
routedoctor tests/fixtures/ios-show-ipv6-route.txt 2001:db8:1:9::1
```

```text
RouteDoctor diagnosis for 2001:db8:1:9::1
====================================================
Selected: 2001:db8:1:8::/61 via 2001:db8::3 [static]
+ Selected 2001:db8:1:8::/61 by longest-prefix match (/61)
+ Next hop 2001:db8::3 resolves through 2001:db8::/64
+ Recursive resolution terminates on GigabitEthernet0/0
+ 3 less-specific route(s) were ignored, including 2001:db8:1::/48
```

Linux output works the same way. This one is forced with `--format`, which is only needed when
detection picks the wrong parser:

```bash
routedoctor tests/fixtures/linux-ip-route.txt 198.51.100.9 --format linux
```

```text
RouteDoctor diagnosis for 198.51.100.9
====================================================
Selected: 198.51.100.0/24 via 192.0.2.4 [static]
+ Selected 198.51.100.0/24 by longest-prefix match (/24)
+ Next hop 192.0.2.4 resolves through 192.0.2.0/24
+ Recursive resolution terminates on eth0
+ 1 less-specific route(s) were ignored, including 0.0.0.0/0
```

## Trace across devices

`--trace-from DEVICE` follows a destination from one device to the next. At each device it picks
the route, takes the last address of the recursive next-hop chain, finds the device that owns that
address, and continues there. It stops when the destination is delivered, when a device has no
route, when no device owns the next hop, when it returns to a device it already visited, or after
32 hops.

```bash
routedoctor examples/campus-snapshot.json 198.51.100.1 --trace-from edge
```

```text
RouteDoctor trace from edge to 198.51.100.1
[1] edge: 0.0.0.0/0 via 192.0.2.2
[2] core: 198.51.100.0/24 via 192.0.2.6
[3] dist: 198.51.100.0/24 via GigabitEthernet0/1
+ delivered at dist
```

A routing loop is reported and the command exits `1`:

```bash
routedoctor examples/loop-snapshot.json 203.0.113.9 --trace-from r1
```

```text
RouteDoctor trace from r1 to 203.0.113.9
[1] r1: 203.0.113.0/24 via 192.0.2.2
[2] r2: 203.0.113.0/24 via 192.0.2.1
! loop: r1 -> r2 -> r1
```

The outcome is one of `delivered`, `blackhole`, `loop`, `unknown_next_hop` and `hop_limit`. Only
`delivered` exits `0`. With `--trace-from`, the first argument is a devices snapshot and `--format`
cannot be used.

### Devices snapshot

This is `examples/loop-snapshot.json`:

```json
{
  "devices": [
    {
      "name": "r1",
      "addresses": ["192.0.2.1"],
      "routes": [
        {"prefix": "192.0.2.0/30", "protocol": "connected", "interface": "GigabitEthernet0/0", "admin_distance": 0},
        {"prefix": "203.0.113.0/24", "protocol": "static", "next_hop": "192.0.2.2", "admin_distance": 1}
      ]
    },
    {
      "name": "r2",
      "addresses": ["192.0.2.2"],
      "routes": [
        {"prefix": "192.0.2.0/30", "protocol": "connected", "interface": "GigabitEthernet0/0", "admin_distance": 0},
        {"prefix": "203.0.113.0/24", "protocol": "static", "next_hop": "192.0.2.1", "admin_distance": 1}
      ]
    }
  ]
}
```

Each device has a unique `name` (1 to 64 printable characters) and exactly one of:

- `routes`: a list of routes, as in the snapshot format below
- `table`: a string with pasted `show ip route`, `show ipv6 route` or `ip route` output (format
  detected automatically)

`addresses` lists the addresses the device owns. Trace needs them to turn a next hop into the
next device, so every device must end up with at least one, and no address may belong to two
devices.

- From IOS text, the addresses come from the `L` (local) routes with a host prefix. Include them
  in the paste.
- Linux `ip route` output has no addresses. Give them in `addresses`.
- For `routes` devices, `addresses` is required.

## Machine-readable output

```bash
routedoctor examples/campus-routing.json 198.51.100.9 --json
```

The same flag works with `--trace-from`.

## Exit codes

- `0`: the route resolves, or the trace is delivered
- `1`: routing or forwarding problem detected
- `2`: invalid input or command usage (unreadable file, no routes recognised, bad address,
  unknown device, malformed snapshot)

## JSON snapshot format

```json
{
  "routes": [
    {
      "prefix": "10.20.0.0/16",
      "protocol": "static",
      "next_hop": "192.0.2.3",
      "admin_distance": 1,
      "metric": 0,
      "active": true
    },
    {
      "prefix": "192.0.2.0/24",
      "protocol": "connected",
      "interface": "GigabitEthernet0/0",
      "admin_distance": 0
    }
  ]
}
```

A bare JSON array of routes (without the `routes` key) is also accepted. `prefix` is required.
`protocol` defaults to `static`, `admin_distance` to `1`, `metric` to `0` and `active` to `true`.
A route needs a `next_hop` or an `interface`, otherwise the diagnosis reports an error. A next hop
must be in the same address family as its prefix. IPv4 and IPv6 routes can be mixed in one file.

## Limitations

- VRFs are not supported. A table is one routing instance.
- IOS and Linux are the only text formats. Other vendors and other commands are not parsed.
- Trace needs each device's own addresses: IOS `L` routes supply them, Linux needs them in the JSON.
- A link-local IPv6 next hop (`fe80::/10`) is treated as directly attached through its interface.
  It is not resolved recursively, so a trace cannot follow it to another device.
- Equal-cost paths are reported, but the forwarding walk and the trace follow only the first one.
- One destination per run.

## Python API

```python
from routedoctor import (
    diagnose_destination, parse_snapshot, parse_table, render_diagnosis, render_trace, trace,
)

table = parse_table("""
S    203.0.113.0/24 [1/0] via 192.0.2.1
C    192.0.2.0/24 is directly connected, GigabitEthernet0/0
L    192.0.2.10/32 is directly connected, GigabitEthernet0/0
""")
print(table.format, table.addresses)          # ios ['192.0.2.10']

diagnosis = diagnose_destination(table.routes, "203.0.113.9")
print(diagnosis.ok)                           # True
print(render_diagnosis(diagnosis))            # the text the CLI prints
print(diagnosis.to_dict())                    # the CLI's --json output

# Trace: `snapshot` is a dict like the devices snapshot above.
result = trace(parse_snapshot(snapshot), "r1", "203.0.113.9")
print(result.outcome, result.ok)              # loop False
print(render_trace(result))
```

- `parse_table(text, format="auto")` returns a `ParsedTable` with `format`, `routes` and
  `addresses`. It raises `ValueError` for an unknown format or when no routes are recognised.
- `parse_routes(items)` builds routes from a list of dicts, as in the JSON snapshot.
- `diagnose_destination(routes, destination)` returns a `Diagnosis`. It raises `ValueError` for an
  invalid address.
- `parse_snapshot(payload)` and `trace(devices, start, destination, max_hops=32)` handle several
  devices. `trace` raises `ValueError` for an unknown start device, a duplicate name, a device
  without addresses, or an address owned by two devices.
- `render_diagnosis` and `render_trace` produce the CLI text.

The library uses only the Python standard library.

## Browser entry point

`routedoctor.web.run(request_json)` takes one JSON string and returns one JSON string. It never
raises; failures come back as `{"ok": false, "error": "..."}`. It is the entry point the browser
demo uses, so the demo can run the same code as the CLI. The request is limited to 400,000
characters.

Two actions exist. `diagnose` takes `table`, `destination` and an optional `format`. `trace` takes
`snapshot`, `from` and `destination`.

```python
import json
from routedoctor.web import run

request = {
    "action": "diagnose",
    "destination": "203.0.113.9",
    "table": "S 203.0.113.0/24 [1/0] via 192.0.2.1\nC 192.0.2.0/24 is directly connected, GigabitEthernet0/0\n",
}
response = json.loads(run(json.dumps(request)))
print(json.dumps({k: v for k, v in response.items() if k != "result"}, indent=2))
print(sorted(response["result"]))
```

```text
{
  "action": "diagnose",
  "ok": true,
  "passed": true,
  "text": "RouteDoctor diagnosis for 203.0.113.9\n====================================================\nSelected: 203.0.113.0/24 via 192.0.2.1 [static]\n+ Selected 203.0.113.0/24 by longest-prefix match (/24)\n+ Next hop 192.0.2.1 resolves through 192.0.2.0/24\n+ Recursive resolution terminates on GigabitEthernet0/0"
}
['candidates', 'destination', 'equal_cost', 'findings', 'ok', 'recursive_chain', 'selected']
```

`ok` says the request was handled. `passed` says whether the route resolved. `result` holds the
same data as `--json`; it is left out of the print above to keep it short.
`demo/manifest.json` holds ready-made request and response pairs; `python scripts/build_demo.py`
rebuilds it and `--check` fails when it is out of date.

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

## Portfolio value

RouteDoctor demonstrates practical networking knowledge through deterministic software: forwarding decisions, route preference, recursive resolution, failure explanation, structured output, tests, and CI, without requiring access to a live router.

See [CHANGELOG.md](CHANGELOG.md) for the release history.

## License

Apache License 2.0.
