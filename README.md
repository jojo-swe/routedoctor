# RouteDoctor

RouteDoctor explains **why a routing table selects a path** and highlights common forwarding failures before they become long troubleshooting sessions.

It operates on offline JSON snapshots, so it is safe to use in CI, labs, incident reviews, and sanitized production exports.

## What it diagnoses

- longest-prefix match
- administrative-distance and metric tie-breaking
- recursive next-hop resolution
- unresolved next hops
- recursive routing loops
- inactive and missing routes
- routes with no usable next hop or exit interface
- less-specific routes shadowed by a more-specific prefix

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

routedoctor examples/campus-routing.json 10.20.5.9
```

Example output:

```text
RouteDoctor diagnosis for 10.20.5.9
====================================================
Selected: 10.20.0.0/16 via 192.0.2.3 [static]
+ Selected 10.20.0.0/16 by longest-prefix match (/16)
+ Next hop 192.0.2.3 resolves through 192.0.2.0/24
+ Recursive resolution terminates on GigabitEthernet0/0
+ 2 less-specific route(s) were ignored, including 10.0.0.0/8
```

Machine-readable output:

```bash
routedoctor examples/campus-routing.json 10.20.5.9 --json
```

Exit codes:

- `0`: route resolves successfully
- `1`: routing or forwarding problem detected
- `2`: invalid input or command usage

## Snapshot format

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

## Python API

```python
from routedoctor import diagnose_destination, parse_routes

routes = parse_routes([
    {"prefix": "0.0.0.0/0", "next_hop": "192.0.2.1"},
    {"prefix": "192.0.2.0/24", "interface": "GigabitEthernet0/0"},
])

result = diagnose_destination(routes, "8.8.8.8")
print(result.to_dict())
```

## Development

```bash
pip install -e ".[dev]"
ruff check .
pytest
```

## Portfolio value

RouteDoctor demonstrates practical networking knowledge through deterministic software: forwarding decisions, route preference, recursive resolution, failure explanation, structured output, tests, and CI—without requiring access to a live router.

## License

Apache License 2.0.
