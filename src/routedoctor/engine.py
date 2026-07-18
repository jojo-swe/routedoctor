"""Routing-table analysis for RouteDoctor."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from ipaddress import IPv4Address, IPv4Network, ip_address, ip_network
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
    def network(self) -> IPv4Network:
        return ip_network(self.prefix, strict=False)


@dataclass(slots=True)
class Diagnosis:
    destination: str
    selected: Route | None
    candidates: list[Route] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    recursive_chain: list[str] = field(default_factory=list)

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
            "findings": self.findings,
        }


def parse_routes(items: list[dict[str, Any]]) -> list[Route]:
    routes: list[Route] = []
    for index, item in enumerate(items):
        try:
            route = Route(
                prefix=str(item["prefix"]),
                protocol=str(item.get("protocol", "static")),
                next_hop=item.get("next_hop"),
                interface=item.get("interface"),
                admin_distance=int(item.get("admin_distance", 1)),
                metric=int(item.get("metric", 0)),
                active=bool(item.get("active", True)),
            )
            route.network
            if route.next_hop is not None:
                ip_address(route.next_hop)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid route at index {index}: {exc}") from exc
        routes.append(route)
    return routes


def diagnose_destination(routes: list[Route], destination: str) -> Diagnosis:
    address = ip_address(destination)
    if not isinstance(address, IPv4Address):
        raise ValueError("only IPv4 is supported in this release")

    candidates = [route for route in routes if route.active and address in route.network]
    candidates.sort(
        key=lambda route: (-route.network.prefixlen, route.admin_distance, route.metric, route.protocol)
    )
    result = Diagnosis(destination=destination, selected=candidates[0] if candidates else None, candidates=candidates)

    if not candidates:
        result.findings.append("ERROR no matching active route; traffic is dropped")
        return result

    selected = candidates[0]
    result.findings.append(
        f"Selected {selected.prefix} by longest-prefix match (/{selected.network.prefixlen})"
    )
    same_prefix = [route for route in candidates if route.network.prefixlen == selected.network.prefixlen]
    if len(same_prefix) > 1:
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
    return result


def _resolve_next_hop(
    routes: list[Route], next_hop: str, result: Diagnosis, visited: set[str]
) -> None:
    if next_hop in visited:
        result.findings.append(f"ERROR recursive routing loop while resolving {next_hop}")
        return
    visited.add(next_hop)
    result.recursive_chain.append(next_hop)

    address = ip_address(next_hop)
    matches = [route for route in routes if route.active and address in route.network]
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
