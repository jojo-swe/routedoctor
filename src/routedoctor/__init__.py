"""RouteDoctor routing diagnostics."""

from __future__ import annotations


def diagnose(routes: list[dict]) -> list[str]:
    findings: list[str] = []
    for route in routes:
        prefix = route.get("prefix", "unknown")
        if not route.get("next_hop"):
            findings.append(f"{prefix}: missing next hop")
        if route.get("age_seconds", 0) > 86_400:
            findings.append(f"{prefix}: stale route")
    return findings


__all__ = ["diagnose"]
