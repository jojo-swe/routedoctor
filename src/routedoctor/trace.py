"""Follow a destination across several devices (standard library only)."""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any

from .engine import Diagnosis, Route, diagnose_destination, parse_routes
from .parsers import parse_ip_addr, parse_table


@dataclass(frozen=True, slots=True)
class Device:
    name: str
    routes: list[Route]
    addresses: list[str]


@dataclass(slots=True)
class Hop:
    device: str
    diagnosis: Diagnosis


@dataclass(slots=True)
class Trace:
    start: str
    destination: str
    hops: list[Hop]
    outcome: str  # "delivered" | "blackhole" | "loop" | "unknown_next_hop" | "hop_limit"
    detail: str

    @property
    def ok(self) -> bool:
        return self.outcome == "delivered"

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "destination": self.destination,
            "ok": self.ok,
            "outcome": self.outcome,
            "detail": self.detail,
            "hops": [
                {"device": hop.device, "diagnosis": hop.diagnosis.to_dict()} for hop in self.hops
            ],
        }


def _delivers(route: Route) -> bool:
    """A connected network, or a local route for one of the device's own addresses."""
    if route.protocol == "connected":
        return True
    return route.protocol == "local" and route.network.prefixlen == route.network.max_prefixlen


def _canonical(address: str) -> str:
    return str(ip_address(address))


def parse_snapshot(payload: dict[str, Any]) -> list[Device]:
    if not isinstance(payload, dict):
        raise ValueError("snapshot must be a JSON object")
    items = payload.get("devices")
    if not isinstance(items, list):
        raise ValueError("snapshot needs a devices list")
    return [_parse_device(index, item) for index, item in enumerate(items)]


def _parse_device(index: int, item: Any) -> Device:
    name = item.get("name") if isinstance(item, dict) else None
    if not isinstance(name, str) or not 0 < len(name) <= 64 or not name.isprintable():
        raise ValueError(f"device {index} needs a name of 1 to 64 printable characters")
    if "routes" in item and "table" in item:
        raise ValueError(f"device {name} has both routes and table; give one")
    if "routes" not in item and "table" not in item:
        raise ValueError(f"device {name} needs routes or table")

    addresses = _parse_addresses(name, item.get("addresses", []))
    try:
        if "routes" in item:
            if not isinstance(item["routes"], list):
                raise ValueError("routes must be a list")
            routes = parse_routes(item["routes"])
        else:
            if not isinstance(item["table"], str):
                raise ValueError("table must be a string")
            table = parse_table(item["table"])
            routes = table.routes
            for found in map(_canonical, table.addresses):
                if found not in addresses:
                    addresses.append(found)
    except ValueError as exc:
        raise ValueError(f"device {name}: {exc}") from exc
    return Device(name=name, routes=routes, addresses=addresses)


def _parse_addresses(name: str, raw: Any) -> list[str]:
    if isinstance(raw, str):
        # Linux `ip addr` output pasted as is.
        raw = parse_ip_addr(raw)
        if not raw:
            raise ValueError(f"device {name}: addresses text has no inet or inet6 lines")
    if not isinstance(raw, list):
        raise ValueError(f"device {name}: addresses must be a list or 'ip addr' text")
    addresses: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            raise ValueError(f"device {name}: address {entry!r} is not a string")
        try:
            canonical = _canonical(entry)
        except ValueError:
            raise ValueError(f"device {name}: address {entry} is not an IP address") from None
        if canonical not in addresses:
            addresses.append(canonical)
    return addresses


def trace(devices: list[Device], start: str, destination: str, max_hops: int = 32) -> Trace:
    by_name: dict[str, Device] = {}
    owners: dict[str, str] = {}
    for device in devices:
        if device.name in by_name:
            raise ValueError(f"duplicate device name {device.name}")
        by_name[device.name] = device
        if not device.addresses:
            raise ValueError(
                f"device {device.name} has no addresses; trace needs them to find the next device"
            )
        for address in device.addresses:
            canonical = _canonical(address)
            if canonical in owners and owners[canonical] != device.name:
                raise ValueError(
                    f"address {canonical} is owned by both {owners[canonical]} and {device.name}"
                )
            owners[canonical] = device.name
    if start not in by_name:
        raise ValueError(f"unknown start device {start}")
    target = _canonical(destination)

    result = Trace(start=start, destination=destination, hops=[], outcome="", detail="")
    path: list[str] = []
    current = by_name[start]
    while True:
        diagnosis = diagnose_destination(current.routes, destination)
        result.hops.append(Hop(current.name, diagnosis))
        path.append(current.name)

        if owners.get(target) == current.name:
            return _finish(result, "delivered", current.name)
        if not diagnosis.ok:
            error = next(f for f in diagnosis.findings if f.startswith("ERROR"))
            return _finish(result, "blackhole", f"{current.name}: {error.removeprefix('ERROR ')}")

        selected = diagnosis.selected
        if not diagnosis.recursive_chain:
            # The route leaves through an interface with no next-hop address. Only a connected
            # network delivers there; otherwise the device on the far side is unknown.
            if selected is not None and _delivers(selected):
                return _finish(result, "delivered", current.name)
            exit_interface = selected.interface if selected is not None else None
            return _finish(
                result,
                "unknown_next_hop",
                f"{current.name}: leaves via {exit_interface}; next device unknown",
            )
        next_hop = diagnosis.recursive_chain[-1]
        owner = owners.get(_canonical(next_hop))
        if owner is None:
            return _finish(result, "unknown_next_hop", f"{current.name}: no device owns {next_hop}")
        if owner in path:
            cycle = [*path[path.index(owner) :], owner]
            return _finish(result, "loop", " -> ".join(cycle))
        if len(result.hops) >= max_hops:
            return _finish(result, "hop_limit", f"gave up after {max_hops} hops")
        current = by_name[owner]


def _finish(result: Trace, outcome: str, detail: str) -> Trace:
    result.outcome = outcome
    result.detail = detail
    return result
