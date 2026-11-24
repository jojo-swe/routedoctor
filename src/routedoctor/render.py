"""Plain-text rendering of a diagnosis or trace, shared by the CLI and the web entry point."""

from __future__ import annotations

from .engine import Diagnosis
from .trace import Trace


def render_diagnosis(diagnosis: Diagnosis) -> str:
    lines = [f"RouteDoctor diagnosis for {diagnosis.destination}", "=" * 52]
    if diagnosis.selected:
        route = diagnosis.selected
        target = route.next_hop or route.interface or "unresolved"
        lines.append(f"Selected: {route.prefix} via {target} [{route.protocol}]")
    else:
        lines.append("Selected: none")
    for finding in diagnosis.findings:
        marker = "!" if finding.startswith("ERROR") else "+"
        lines.append(f"{marker} {finding}")
    return "\n".join(lines)


def render_trace(result: Trace) -> str:
    lines = [f"RouteDoctor trace from {result.start} to {result.destination}"]
    for number, hop in enumerate(result.hops, start=1):
        route = hop.diagnosis.selected
        if route:
            target = route.next_hop or route.interface or "unresolved"
            lines.append(f"[{number}] {hop.device}: {route.prefix} via {target}")
        else:
            lines.append(f"[{number}] {hop.device}: no matching route")
    if result.ok:
        lines.append(f"+ delivered at {result.detail}")
    else:
        lines.append(f"! {result.outcome}: {result.detail}")
    return "\n".join(lines)
