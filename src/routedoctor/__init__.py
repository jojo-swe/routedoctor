"""RouteDoctor routing diagnostics."""

from .engine import Diagnosis, Route, diagnose_destination, parse_routes


def diagnose(routes: list[dict], destination: str = "0.0.0.0") -> list[str]:
    """Compatibility helper returning findings for one destination."""
    return diagnose_destination(parse_routes(routes), destination).findings


__all__ = ["Diagnosis", "Route", "diagnose", "diagnose_destination", "parse_routes"]
__version__ = "0.1.0"
