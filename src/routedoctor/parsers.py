"""Parsers that turn pasted router output into routes (standard library only)."""

from __future__ import annotations

import json
import re
import textwrap
from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from typing import Any

from .engine import _MAX_NUMBER, Route, parse_routes


@dataclass(frozen=True, slots=True)
class ParsedTable:
    format: str  # "ios" | "ios6" | "ios+ios6" | "linux" | "linux6" | "json"
    routes: list[Route]
    addresses: list[str]  # addresses the device itself owns


# Text lines longer than this are skipped: no real route line comes close, and it bounds the
# work every pattern does per line.
MAX_LINE_LENGTH = 2000


def _lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if len(line) <= MAX_LINE_LENGTH]


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
# The lookahead requires a colon without the quadratic backtracking of `[..]*:[..]*`.
_IOS6_ROUTE_RE = re.compile(
    r"^(?P<code>[A-Za-z][A-Za-z0-9*+%]*)\s+(?P<prefix>(?=[0-9A-Fa-f.]*:)[0-9A-Fa-f:.]+/\d+)"
    r"(?P<rest>.*)$"
)
# `203.0.113.0/26 is subnetted, 2 subnets`: children then omit their own /len.
_SUBNETTED_RE = re.compile(
    r"^\s+\d+\.\d+\.\d+\.\d+/(?P<length>\d+) is (?P<variably>variably )?subnetted"
)
_CODE_RE = re.compile(r"[A-Za-z]+[0-9]?")
_DISTANCE_RE = re.compile(r"\[(\d+)/(\d+)\]")
_VIA_RE = re.compile(r"\bvia\s+(?P<target>\S+?)(?:,\s*(?P<tail>.*))?$")
_CONNECTED_RE = re.compile(r"directly connected,\s*(?P<interface>\S+)")
# `D  203.0.113.192/26 is a summary, 00:12:01, Null0`: an EIGRP summary's discard route.
_SUMMARY_RE = re.compile(r"\bis a summary,(?P<tail>.*)$")
_NULL_SPACE_RE = re.compile(r"\bNull\s+0\b", re.IGNORECASE)
_EIGRP_SUMMARY_DISTANCE = 5
_AGE_RE = re.compile(r"\d+:\d+:\d+|\d+[wdhms]\d*[wdhms]*")
_IPV4_LIKE_RE = re.compile(r"\d+\.\d+\.\d+\.\d+")
_IPV6_LIKE_RE = re.compile(r"[0-9A-Fa-f:.]+")
# FRR and Quagga mark the selected route with ">" right after the code: `K>* 0.0.0.0/0 ...`.
_FRR_ROUTE_RE = re.compile(r"^[A-Za-z]{1,2}\s*>[*=]?\s*[0-9A-Fa-f:.]+/\d+")
_FRR_MESSAGE = "this looks like FRR or Quagga output, which is not supported"
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
    _reject_frr(text)
    items: list[dict[str, object]] = []
    addresses: list[str] = []
    current: dict[str, object] | None = None  # route header that "via" lines attach to

    def add_path(text_after_prefix: str) -> bool:
        """Append a route for the current header; True when its line may wrap."""
        if current is None or current["protocol"] == "local":
            return False
        path = _ios_path(text_after_prefix)
        distance = _ios_distance(text_after_prefix)
        if path is None or distance is False:
            return False
        next_hop, interface = path
        item = {**current, "next_hop": next_hop, "interface": interface}
        if distance:
            item["admin_distance"], item["metric"] = distance
        items.append(item)
        # `via 192.0.2.2, 00:10:21,` wraps: the interface is alone on the next line.
        return interface is None and text_after_prefix.endswith(",")

    inherited_length: str | None = None  # prefix length from an "is subnetted" header

    wrapped = False  # the previous path line ended in "," with no interface yet

    for line in _lines(text):
        line = line.rstrip()
        was_wrapped, wrapped = wrapped, False
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
            try:
                network = ip_network(prefix, strict=False)
            except ValueError:
                current = None  # not a valid prefix: skip the line
                continue
            rest = match["rest"]
            if protocol == "local":
                if network.prefixlen == network.max_prefixlen:
                    addresses.append(str(network.network_address))
                current = {"protocol": protocol}
                continue
            current = {"prefix": str(network), "protocol": protocol}
            if protocol == "connected":
                current["admin_distance"] = 0
            elif protocol == "eigrp" and _SUMMARY_RE.search(rest):
                current["admin_distance"] = _EIGRP_SUMMARY_DISTANCE
            distance = _ios_distance(rest)
            if distance is False:
                current = None  # an out-of-range [distance/metric]: skip the line
                continue
            if distance:
                current["admin_distance"], current["metric"] = distance
            wrapped = add_path(rest)
            continue
        stripped = line.strip()
        if stripped.startswith(("[", "via ")):
            wrapped = add_path(stripped)
        elif was_wrapped and stripped and " " not in stripped:
            items[-1]["interface"] = stripped
        else:
            current = None
    return ParsedTable(format=table_format, routes=parse_routes(items), addresses=addresses)


def _ios_distance(text: str) -> tuple[int, int] | None | bool:
    """`[110/20]` as numbers; None when absent, False when a number is out of range."""
    found = _DISTANCE_RE.search(text)
    if not found:
        return None
    if len(found[1]) > 10 or len(found[2]) > 10:
        return False  # also keeps int() far from the interpreter's digit limit
    distance, metric = int(found[1]), int(found[2])
    if distance > _MAX_NUMBER or metric > _MAX_NUMBER:
        return False
    return distance, metric


def _ios_path(text: str) -> tuple[str | None, str | None] | None:
    """Return (next_hop, interface) from `via ...`, `is directly connected, ...` or summary text."""
    text = _NULL_SPACE_RE.sub("Null0", text)
    via = _VIA_RE.search(text)
    if via:
        target = via["target"]
        fields = [f.strip() for f in (via["tail"] or "").split(",") if f.strip()]
        names = [f for f in fields if f not in _NOT_INTERFACES and not _AGE_RE.fullmatch(f)]
        try:
            hop = ip_address(target)
        except ValueError:
            if _looks_like_address(target):
                return None  # an address that does not parse: skip the line
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
    summary = _SUMMARY_RE.search(text)
    if summary:
        fields = [f.strip() for f in summary["tail"].split(",") if f.strip()]
        names = [f for f in fields if not _AGE_RE.fullmatch(f)]
        if names:
            return None, names[-1]
    return None


def _looks_like_address(text: str) -> bool:
    """True for text shaped like an IP address, as opposed to an interface name."""
    if _IPV4_LIKE_RE.fullmatch(text):
        return True
    # `Serial0/0/0:0` has a colon but is an interface: only hex digits, dots and colons count.
    return ":" in text and _IPV6_LIKE_RE.fullmatch(text) is not None


def _reject_frr(text: str) -> None:
    for line in _lines(text):
        if _FRR_ROUTE_RE.match(line):
            raise ValueError(_FRR_MESSAGE)


# --- Linux `ip route` / `ip addr` -------------------------------------------------------

# Route types whose packets the kernel drops; they still win longest-prefix match.
_LINUX_DISCARD_TYPES = {"unreachable", "blackhole", "prohibit"}


def parse_linux(text: str) -> ParsedTable:
    """Parse `ip route` or `ip -6 route`; the format is "linux6" when every route is IPv6."""
    items: list[dict[str, Any]] = []
    # Default routes carry no address family; remember them until the table's family is known.
    families: set[int] = set()
    defaults: list[dict[str, Any]] = []
    header: dict[str, Any] | None = None  # route line that indented `nexthop` lines belong to

    def add(item: dict[str, Any]) -> None:
        family = item.pop("family", None)
        if item["prefix"] == "default":
            if family:
                families.add(family)
            item["family"] = family  # resolved below
            defaults.append(item)
        else:
            families.add(ip_network(item["prefix"], strict=False).version)
        items.append(item)

    for line in _lines(text):
        if not line.strip():
            continue
        tokens = line.split()
        try:
            if line[0].isspace():
                if header is not None and tokens[0] == "nexthop":
                    add({**header, **_linux_path(tokens[1:])})
                continue
            header = _linux_route(tokens)
            if header is None:
                continue
            if header.get("next_hop") or header.get("interface") or header.get("discard"):
                add(header)
        except ValueError:
            header = None  # unreadable address, prefix or number: not a route line
    # A default route with no next hop takes the family of the rest of the table.
    table_default = "::/0" if families == {6} else "0.0.0.0/0"
    for item in defaults:
        family = item.pop("family")
        item["prefix"] = table_default if family is None else ("::/0" if family == 6 else "0.0.0.0/0")
    routes = parse_routes(items)
    all_v6 = bool(routes) and all(route.network.version == 6 for route in routes)
    return ParsedTable(format="linux6" if all_v6 else "linux", routes=routes, addresses=[])


def _linux_route(tokens: list[str]) -> dict[str, Any] | None:
    """Read one column-0 `ip route` line; None when it does not start like a route."""
    discard = None
    if tokens[0] in _LINUX_DISCARD_TYPES:
        discard = tokens[0]
        tokens = tokens[1:]
        if not tokens:
            return None
    prefix = tokens[0]
    if prefix != "default":
        prefix = str(ip_network(prefix, strict=False))  # ValueError: not a route line
    path = _linux_path(tokens[1:])
    protocol = path.pop("proto", None)
    if protocol == "kernel" and discard is None:
        item = {"protocol": "connected", "admin_distance": 0}
    else:
        # A kernel discard route (`unreachable default dev lo proto kernel`) is not a connected
        # network; it competes on metric like the kernel does.
        item = {"protocol": protocol or "static", "admin_distance": 1}
    return {"prefix": prefix, "active": True, "discard": discard, **item, **path}


def _linux_path(tokens: list[str]) -> dict[str, Any]:
    """Read `via`, `dev`, `proto` and `metric` from the key/value tokens of an `ip route` line."""
    found: dict[str, Any] = {}
    index = 0
    while index < len(tokens):
        key = tokens[index]
        if key in ("via", "dev", "proto", "metric", "priority") and index + 1 < len(tokens):
            value = tokens[index + 1]
            if key == "via" and value in ("inet", "inet6") and index + 2 < len(tokens):
                value = tokens[index + 2]
                index += 1
            index += 2
            if key == "via":
                found["next_hop"] = str(ip_address(value))  # ValueError: not a route line
            elif key == "dev":
                found["interface"] = value
            elif key == "proto":
                found["proto"] = value
            else:
                found["metric"] = int(value)
                if found["metric"] < 0:
                    raise ValueError("negative metric")
        else:
            if key in ("linkdown", "dead"):
                found["active"] = False  # the kernel does not use this path
            index += 1
    hop = found.get("next_hop")
    if hop:
        address = ip_address(hop)
        found["family"] = address.version
        # As in IOS output, a link-local next hop only means "out of this interface".
        if address.version == 6 and address.is_link_local and "interface" in found:
            del found["next_hop"]
    return found


def parse_ip_addr(text: str) -> list[str]:
    """Return the global addresses from `ip addr`, without prefix lengths or link-local ones."""
    addresses: list[str] = []
    for line in _lines(text):
        tokens = line.split()
        if len(tokens) < 2 or tokens[0] not in ("inet", "inet6"):
            continue
        try:
            address = ip_address(tokens[1].partition("/")[0])
        except ValueError:
            continue
        if address.is_link_local or address.is_loopback:
            continue
        if str(address) not in addresses:
            addresses.append(str(address))
    return addresses


# --- Format detection ---------------------------------------------------------------------

MAX_TEXT_LENGTH = 200_000
_NO_ROUTES = "no routes recognised; expected JSON, 'show ip route' or 'ip route' output"
_FORMATS = ("auto", "json", "ios", "ios6", "linux", "linux6")


def parse_table(text: str, format: str = "auto") -> ParsedTable:
    """Parse a pasted routing table. `format` is "auto" or forces one parser."""
    if format not in _FORMATS:
        raise ValueError(f"unknown format: {format}")
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(f"input is larger than {MAX_TEXT_LENGTH} characters")
    # Pastes from code blocks or quoted mail are uniformly indented; keep relative indentation.
    text = textwrap.dedent(text.removeprefix("\ufeff").replace("\r\n", "\n"))
    if format == "auto":
        # Order matters: an IOS line is never a valid Linux line, but not the other way round.
        # A parser only wins by finding routes, so prose that merely contains an address does not.
        table = _parse_json(text)
        if table.routes:
            return table
        _reject_frr(text)
        # `show ip route` and `show ipv6 route` are often pasted together: keep both halves.
        table = _merge_ios(_parse_ios_strict(text), _parse_ios6_strict(text))
        if table.routes:
            return table
        table = parse_linux(text)
        if table.routes:
            return table
    else:
        parsers = {"json": _parse_json, "ios": parse_ios, "ios6": parse_ios6}
        table = parsers.get(format, parse_linux)(text)
        if table.routes:
            return table
    raise ValueError(_NO_ROUTES)


def _parse_json(text: str) -> ParsedTable:
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError):
        return ParsedTable(format="json", routes=[], addresses=[])
    items = payload.get("routes") if isinstance(payload, dict) else payload
    # Only a list of objects is a route list; anything else is some other JSON.
    is_route_list = isinstance(items, list) and all(isinstance(item, dict) for item in items)
    routes = parse_routes(items) if is_route_list else []
    return ParsedTable(format="json", routes=routes, addresses=[])


def _merge_ios(v4: ParsedTable, v6: ParsedTable) -> ParsedTable:
    if not v6.routes:
        return v4
    if not v4.routes:
        return v6
    addresses = list(dict.fromkeys([*v4.addresses, *v6.addresses]))
    return ParsedTable(format="ios+ios6", routes=[*v4.routes, *v6.routes], addresses=addresses)


def _parse_ios_strict(text: str) -> ParsedTable:
    return _ios_if_known_codes(text, _IOS_ROUTE_RE, _IOS_PROTOCOLS, parse_ios)


def _parse_ios6_strict(text: str) -> ParsedTable:
    return _ios_if_known_codes(text, _IOS6_ROUTE_RE, _IOS6_PROTOCOLS, parse_ios6)


def _ios_if_known_codes(
    text: str, route_re: re.Pattern[str], protocols: dict[str, str], parser: Any
) -> ParsedTable:
    """Run an IOS parser only if a line starts with a real route code and a prefix.

    The IOS line patterns alone would accept any word followed by an address ("Hello 192.0.2.1"),
    so auto-detection also requires the word to be a code the parser knows.
    """
    for line in _lines(text):
        match = route_re.match(line)
        if match and match["code"].rstrip("*+%") in protocols:
            return parser(text)  # a genuine error in a real IOS table should surface
    return ParsedTable(format="ios", routes=[], addresses=[])
