"""RouteDoctor routing diagnostics."""

from .engine import Diagnosis, Route, diagnose_destination, parse_routes
from .parsers import parse_table
from .render import render_diagnosis, render_trace
from .trace import parse_snapshot, trace

__all__ = [
    "Diagnosis",
    "Route",
    "diagnose_destination",
    "parse_routes",
    "parse_table",
    "parse_snapshot",
    "render_diagnosis",
    "render_trace",
    "trace",
]
__version__ = "1.0.0"
