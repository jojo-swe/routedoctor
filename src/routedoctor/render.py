"""Plain-text rendering of a diagnosis, shared by the CLI and the web entry point."""

from __future__ import annotations

from .engine import Diagnosis


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
