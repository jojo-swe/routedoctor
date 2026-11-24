"""Parsers that turn pasted router output into routes (standard library only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from ipaddress import ip_address, ip_network

from .engine import Route, parse_routes


@dataclass(frozen=True, slots=True)
class ParsedTable:
    format: str  # "ios" | "ios6" | "linux" | "linux6" | "json"
    routes: list[Route]
    addresses: list[str]  # addresses the device itself owns


# --- Cisco IOS -------------------------------------------------------------------------

_IOS_PROTOCOLS = {
    "C": "connected",
    "L": "local",
    "S": "static",
    "O": "ospf",
    "D": "eigrp",
    "B": "bgp",
    "R": "rip",
    "i": "isis",
}
# `show ipv6 route` prints one multi-letter code per route instead of sub-codes.
_IOS6_PROTOCOLS = {
    **{code: name for code, name in _IOS_PROTOCOLS.items() if code != "i"},
    "LC": "local",
    "OI": "ospf",
    "OE1": "ospf",
    "OE2": "ospf",
    "ON1": "ospf",
    "ON2": "ospf",
    "EX": "eigrp",
    "I1": "isis",
    "I2": "isis",
    "IA": "isis",
    "IS": "isis",
}

# Route lines start in column 0: a code (plus optional IPv4 sub-code), then the prefix.
_IOS_ROUTE_RE = re.compile(
    r"^(?P<code>[A-Za-z][A-Za-z0-9*+%]*)(?:\s+[A-Za-z][A-Za-z0-9]*)?"
    r"\s+(?P<prefix>\d+\.\d+\.\d+\.\d+(?:/\d+)?)(?P<rest>.*)$"
)
_IOS6_ROUTE_RE = re.compile(
    r"^(?P<code>[A-Za-z][A-Za-z0-9*+%]*)\s+(?P<prefix>[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*/\d+)"
    r"(?P<rest>.*)$"
)
# `203.0.113.0/26 is subnetted, 2 subnets`: children then omit their own /len.
_SUBNETTED_RE = re.compile(r"^\s+\d+\.\d+\.\d+\.\d+/(?P<length>\d+) is (?P<variably>variably )?subnetted")
_CODE_RE = re.compile(r"[A-Za-z]+[0-9]?")
_DISTANCE_RE = re.compile(r"\[(\d+)/(\d+)\]")
_VIA_RE = re.compile(r"\bvia\s+(?P<target>\S+?)(?:,\s*(?P<tail>.*))?$")
_CONNECTED_RE = re.compile(r"directly connected,\s*(?P<interface>\S+)")
_AGE_RE = re.compile(r"\d+:\d+:\d+|\d+[wdhms]\d*[wdhms]*")
_NOT_INTERFACES = {"directly connected", "receive"}


def parse_ios(text: str) -> ParsedTable:
    """Parse `show ip route`."""
    return _parse_ios_text(text, "ios", _IOS_ROUTE_RE, _IOS_PROTOCOLS)


def parse_ios6(text: str) -> ParsedTable:
    """Parse `show ipv6 route`."""
    return _parse_ios_text(text, "ios6", _IOS6_ROUTE_RE, _IOS6_PROTOCOLS)


def _parse_ios_text(
    text: str, table_format: str, route_re: re.Pattern[str], protocols: dict[str, str]
) -> ParsedTable:
    items: list[dict[str, object]] = []
    addresses: list[str] = []
    current: dict[str, object] | None = None  # route header that "via" lines attach to

    def add_path(text_after_prefix: str) -> None:
        if current is None or current["protocol"] == "local":
            return
        path = _ios_path(text_after_prefix)
        if path is None:
            return
        next_hop, interface = path
        distance = _DISTANCE_RE.search(text_after_prefix)
        item = {**current, "next_hop": next_hop, "interface": interface}
        if distance:
            item["admin_distance"], item["metric"] = int(distance[1]), int(distance[2])
        items.append(item)

    inherited_length: str | None = None  # prefix length from an "is subnetted" header

    for line in text.splitlines():
        header = _SUBNETTED_RE.match(line)
        if header:
            inherited_length = None if header["variably"] else header["length"]
            current = None
            continue
        match = route_re.match(line)
        if match:
            prefix = match["prefix"]
            if "/" in prefix:
                inherited_length = None
            elif inherited_length is not None:
                prefix = f"{prefix}/{inherited_length}"
            else:
                current = None
                continue
            code = _CODE_RE.match(match["code"].rstrip("*"))
            protocol = protocols.get(code[0] if code else "", "other")
            network = ip_network(prefix, strict=False)
            rest = match["rest"]
            if protocol == "local":
                if network.prefixlen == network.max_prefixlen:
                    addresses.append(str(network.network_address))
                current = {"protocol": protocol}
                continue
            current = {"prefix": str(network), "protocol": protocol}
            if protocol == "connected":
                current["admin_distance"] = 0
            distance = _DISTANCE_RE.search(rest)
            if distance:
                current["admin_distance"], current["metric"] = int(distance[1]), int(distance[2])
            add_path(rest)
            continue
        stripped = line.strip()
        if stripped.startswith(("[", "via ")):
            add_path(stripped)
        else:
            current = None
    return ParsedTable(format=table_format, routes=parse_routes(items), addresses=addresses)


def _ios_path(text: str) -> tuple[str | None, str | None] | None:
    """Return (next_hop, interface) from `via ...` or `is directly connected, ...` text."""
    via = _VIA_RE.search(text)
    if via:
        target = via["target"]
        fields = [f.strip() for f in (via["tail"] or "").split(",") if f.strip()]
        names = [f for f in fields if f not in _NOT_INTERFACES and not _AGE_RE.fullmatch(f)]
        try:
            hop = ip_address(target)
        except ValueError:
            return None, target  # `via GigabitEthernet0/0, directly connected`
        interface = names[-1] if names else None
        # A link-local next hop is only meaningful on its interface and cannot be
        # resolved recursively, so keep the interface and drop the hop.
        if hop.version == 6 and hop.is_link_local and interface:
            return None, interface
        return str(hop), interface
    connected = _CONNECTED_RE.search(text)
    if connected:
        return None, connected["interface"]
    return None
