"""Routing-table analysis for RouteDoctor."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network
from typing import Any


@dataclass(frozen=True, slots=True)
class Route:
    prefix: str
    protocol: str = "static"
    next_hop: str | None = None
    interface: str | None = None
    admin_distance: int = 1
    metric: int = 0
    active: bool = True

    @property
    def network(self) -> IPv4Network | IPv6Network:
        return ip_network(self.prefix, strict=False)


@dataclass(slots=True)
class Diagnosis:
    destination: str
    selected: Route | None
    candidates: list[Route] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    recursive_chain: list[str] = field(default_factory=list)
    equal_cost: list[Route] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.selected is not None and not any(
            finding.startswith("ERROR") for finding in self.findings
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "ok": self.ok,
            "selected": asdict(self.selected) if self.selected else None,
            "candidates": [asdict(route) for route in self.candidates],
            "recursive_chain": self.recursive_chain,
            "equal_cost": [asdict(route) for route in self.equal_cost],
            "findings": self.findings,
        }


_MAX_NUMBER = 4_294_967_295


def parse_routes(items: list[dict[str, Any]]) -> list[Route]:
    routes: list[Route] = []
    for index, item in enumerate(items):
        try:
            route = Route(
                prefix=_text(item, "prefix", required=True),
                protocol=_text(item, "protocol", default="static"),
                next_hop=_text(item, "next_hop", optional=True),
                interface=_text(item, "interface", optional=True),
                admin_distance=_number(item, "admin_distance", 1),
                metric=_number(item, "metric", 0),
                active=bool(item.get("active", True)),
            )
            network = route.network
            if route.next_hop is not None:
                next_hop = ip_address(route.next_hop)
                if next_hop.version != network.version:
                    raise ValueError(
                        f"next hop {route.next_hop} is IPv{next_hop.version} "
                        f"but prefix {route.prefix} is IPv{network.version}"
                    )
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
            raise ValueError(f"invalid route at index {index}: {exc}") from exc
        routes.append(route)
    return routes


def _text(
    item: dict[str, Any],
    key: str,
    *,
    required: bool = False,
    optional: bool = False,
    default: str = "",
) -> Any:
    if key not in item:
        if required:
            raise KeyError(key)
        return None if optional else default
    value = item[key]
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _number(item: dict[str, Any], key: str, default: int) -> int:
    value = item.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_NUMBER:
        raise ValueError(f"{key} must be an integer from 0 to {_MAX_NUMBER}")
    return value


def diagnose_destination(routes: list[Route], destination: str) -> Diagnosis:
    address = ip_address(destination)

    candidates = [route for route in _routes_for(routes, address) if route.active]
    candidates.sort(
        key=lambda route: (-route.network.prefixlen, route.admin_distance, route.metric, route.protocol)
    )
    result = Diagnosis(destination=destination, selected=candidates[0] if candidates else None, candidates=candidates)
    inactive = [route for route in _routes_for(routes, address) if not route.active]
    skipped = [
        f"{len(inactive)} inactive route(s) for this destination were skipped, "
        f"including {inactive[0].prefix}"
    ] if inactive else []

    if not candidates:
        result.findings.append("ERROR no matching active route; traffic is dropped")
        result.findings.extend(skipped)
        return result

    selected = candidates[0]
    result.findings.append(
        f"Selected {selected.prefix} by longest-prefix match (/{selected.network.prefixlen})"
    )
    same_prefix = [route for route in candidates if route.network.prefixlen == selected.network.prefixlen]
    equal_cost = [
        route
        for route in same_prefix
        if (route.admin_distance, route.metric) == (selected.admin_distance, selected.metric)
    ]
    if len(equal_cost) > 1:
        result.equal_cost = equal_cost
        paths = ", ".join(route.next_hop or route.interface or "unresolved" for route in equal_cost)
        result.findings.append(f"{len(equal_cost)} equal-cost paths via {paths}; showing the first")
    elif len(same_prefix) > 1:
        result.findings.append(
            f"Tie broken by administrative distance {selected.admin_distance} and metric {selected.metric}"
        )

    if selected.next_hop:
        _resolve_next_hop(routes, selected.next_hop, result, visited=set())
    elif selected.interface:
        result.findings.append(f"Forward directly through {selected.interface}")
    else:
        result.findings.append("ERROR selected route has neither next hop nor exit interface")

    shadowed = [route for route in candidates[1:] if route.network.prefixlen < selected.network.prefixlen]
    if shadowed:
        result.findings.append(
            f"{len(shadowed)} less-specific route(s) were ignored, including {shadowed[0].prefix}"
        )
    result.findings.extend(skipped)
    return result


def _routes_for(routes: list[Route], address: IPv4Address | IPv6Address) -> list[Route]:
    return [
        route
        for route in routes
        if route.network.version == address.version and address in route.network
    ]


def _resolve_next_hop(
    routes: list[Route], next_hop: str, result: Diagnosis, visited: set[str]
) -> None:
    if next_hop in visited:
        result.findings.append(f"ERROR recursive routing loop while resolving {next_hop}")
        return
    visited.add(next_hop)
    result.recursive_chain.append(next_hop)

    address = ip_address(next_hop)
    matches = [route for route in _routes_for(routes, address) if route.active]
    matches.sort(key=lambda route: (-route.network.prefixlen, route.admin_distance, route.metric))
    if not matches:
        result.findings.append(f"ERROR next hop {next_hop} is unresolved")
        return

    resolution = matches[0]
    result.findings.append(f"Next hop {next_hop} resolves through {resolution.prefix}")
    if resolution.next_hop:
        _resolve_next_hop(routes, resolution.next_hop, result, visited)
    elif resolution.interface:
        result.findings.append(f"Recursive resolution terminates on {resolution.interface}")
    else:
        result.findings.append(
            f"ERROR resolving route {resolution.prefix} has neither next hop nor interface"
        )
