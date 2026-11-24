"""Browser entry point: one JSON request in, one JSON response out. Never raises."""

from __future__ import annotations

import json
from typing import Any

from .engine import diagnose_destination
from .parsers import parse_table
from .render import render_diagnosis, render_trace
from .trace import parse_snapshot, trace

MAX_REQUEST_LENGTH = 400_000
MAX_ERROR_LENGTH = 300


def run(request_json: str) -> str:
    """Handle a request and return a JSON response; failures are `{"ok": false, "error": ...}`."""
    try:
        response = _handle(request_json)
    except (Exception, RecursionError, MemoryError) as exc:
        response = _failure(str(exc) or type(exc).__name__)
    try:
        return json.dumps(response, sort_keys=True)
    except (Exception, RecursionError, MemoryError):
        return json.dumps(_failure("response could not be encoded"), sort_keys=True)


def _failure(message: str) -> dict[str, Any]:
    one_line = " ".join(message.split())
    return {"ok": False, "error": one_line[:MAX_ERROR_LENGTH]}


def _handle(request_json: str) -> dict[str, Any]:
    if not isinstance(request_json, str):
        return _failure("request must be a string")
    if len(request_json) > MAX_REQUEST_LENGTH:
        return _failure(f"request is larger than {MAX_REQUEST_LENGTH} characters")
    try:
        request = json.loads(request_json.removeprefix("\ufeff"))
    except (ValueError, RecursionError):
        return _failure("request is not valid JSON")
    if not isinstance(request, dict):
        return _failure("request must be a JSON object")

    action = request.get("action")
    if action == "diagnose":
        return _diagnose(request)
    if action == "trace":
        return _trace(request)
    return _failure(f"unknown action: {action}")


def _field(request: dict[str, Any], name: str, kind: type, label: str) -> Any:
    value = request.get(name)
    if not isinstance(value, kind):
        raise ValueError(f"{name} must be {label}")
    return value


def _diagnose(request: dict[str, Any]) -> dict[str, Any]:
    table = _field(request, "table", str, "a string")
    destination = _field(request, "destination", str, "a string")
    fmt = request.get("format", "auto")
    if not isinstance(fmt, str):
        raise ValueError("format must be a string")
    parsed = parse_table(table, fmt)
    diagnosis = diagnose_destination(parsed.routes, destination.strip())
    return _success("diagnose", diagnosis.ok, render_diagnosis(diagnosis), diagnosis.to_dict())


def _trace(request: dict[str, Any]) -> dict[str, Any]:
    snapshot = _field(request, "snapshot", dict, "an object")
    start = _field(request, "from", str, "a string")
    destination = _field(request, "destination", str, "a string")
    result = trace(parse_snapshot(snapshot), start, destination.strip())
    return _success("trace", result.ok, render_trace(result), result.to_dict())


def _success(action: str, passed: bool, text: str, result: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "action": action, "passed": passed, "text": text, "result": result}
