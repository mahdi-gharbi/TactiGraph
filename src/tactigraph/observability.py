"""Bounded process-local telemetry. Never record bodies, query strings or SQL text."""

import json
import logging
import re
import time
from collections import defaultdict, deque
from contextvars import ContextVar
from threading import Lock
from uuid import uuid4

from sqlalchemy import event

logger = logging.getLogger("tactigraph.requests")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
logger.propagate = False

_request_stats = ContextVar("tactigraph_request_stats", default=None)
_LABELS = {"model_version", "retrieval_method", "provider", "outcome", "fallback_reason"}
_COUNTS = {"input_tokens", "output_tokens", "attempts", "repairs", "provider_errors"}


def record_operation(request, **fields):
    """Attach only bounded operational labels; never pass prompts or provider errors."""
    details = request.scope.setdefault("state", {}).setdefault("operation", {})
    for key, value in fields.items():
        if key in _LABELS and isinstance(value, str):
            if re.fullmatch(r"[A-Za-z0-9_. /:+-]{1,100}", value):
                details[key] = value
        elif key in {"fallback", "usage_complete"} and isinstance(value, bool):
            details[key] = value
        elif key in _COUNTS and isinstance(value, int) and 0 <= value <= 10_000_000:
            details[key] = value
        elif key == "generation_ms" and isinstance(value, (int, float)) and 0 <= value <= 300_000:
            details[key] = round(value, 3)
        elif key == "stages" and isinstance(value, list) and len(value) <= 8:
            allowed = {
                "validate_context",
                "interpret",
                "retrieve_methodology",
                "compute_and_verify",
                "render",
            }
            safe = []
            for stage in value:
                if (
                    stage.get("name") in allowed
                    and stage.get("status")
                    in {"success", "error", "answered", "abstained", "clarification_required"}
                    and isinstance(stage.get("duration_ms"), (int, float))
                    and 0 <= stage["duration_ms"] <= 300_000
                ):
                    safe.append(
                        {
                            "name": stage["name"],
                            "status": stage["status"],
                            "duration_ms": round(stage["duration_ms"], 3),
                        }
                    )
            details[key] = safe


def instrument_engine(engine):
    """Count database work inside each request without retaining statements/parameters."""
    if getattr(engine, "_tactigraph_instrumented", False):
        return
    engine._tactigraph_instrumented = True

    @event.listens_for(engine, "before_cursor_execute")
    def before(connection, cursor, statement, parameters, context, executemany):
        context._tactigraph_started = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def after(connection, cursor, statement, parameters, context, executemany):
        stats = _request_stats.get()
        if stats is not None:
            stats["db_queries"] += 1
            stats["db_ms"] += (time.perf_counter() - context._tactigraph_started) * 1000


class Telemetry:
    """Counters since process start; latency samples retain only the last 256 calls/route."""

    def __init__(self):
        self.started = time.monotonic()
        self.lock = Lock()
        self.routes = defaultdict(
            lambda: {"requests": 0, "errors": 0, "fallbacks": 0, "latency": deque(maxlen=256)}
        )

    def observe(self, method, route, status, duration, fallback):
        with self.lock:
            row = self.routes[f"{method} {route}"]
            row["requests"] += 1
            row["errors"] += status >= 500
            row["fallbacks"] += bool(fallback)
            row["latency"].append(duration)

    def snapshot(self):
        with self.lock:
            routes = []
            for route, row in sorted(self.routes.items()):
                values = sorted(row["latency"])
                routes.append(
                    {
                        "route": route,
                        "requests": row["requests"],
                        "server_errors": row["errors"],
                        "fallbacks": row["fallbacks"],
                        "latency_sample_size": len(values),
                        "p50_ms": round(values[(len(values) - 1) // 2], 3),
                        "p95_ms": round(values[max(0, (95 * len(values) + 99) // 100 - 1)], 3),
                    }
                )
        return {
            "scope": "single process; counters reset on restart; last 256 latencies per route",
            "uptime_seconds": round(time.monotonic() - self.started, 3),
            "routes": routes,
        }


class RequestTelemetryMiddleware:
    def __init__(self, app, telemetry):
        self.app = app
        self.telemetry = telemetry

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        state = scope.setdefault("state", {})
        if state.get("_tactigraph_telemetry_owner"):
            # Mounted league apps share this request: one ID, one header, one log.
            await self.app(scope, receive, send)
            return
        state["_tactigraph_telemetry_owner"] = True
        started = time.perf_counter()
        request_id = uuid4().hex
        state["request_id"] = request_id
        stats = {"db_queries": 0, "db_ms": 0.0}
        token = _request_stats.set(stats)
        status = 500

        async def response(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", request_id.encode("ascii"))
                ]
            await send(message)

        try:
            await self.app(scope, receive, response)
        finally:
            duration = (time.perf_counter() - started) * 1000
            route = getattr(scope.get("route"), "path", "unmatched")
            if route != "unmatched":
                route = scope.get("root_path", "").rstrip("/") + route
            # The route template, never the concrete path or its query string.
            method = scope.get("method", "UNKNOWN")
            if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
                method = "OTHER"
            operation = state.get("operation", {})
            self.telemetry.observe(method, route, status, duration, operation.get("fallback"))
            logger.info(
                json.dumps(
                    {
                        "event": "http_request",
                        "request_id": request_id,
                        "method": method,
                        "route": route,
                        "status": status,
                        "duration_ms": round(duration, 3),
                        "db_queries": stats["db_queries"],
                        "db_ms": round(stats["db_ms"], 3),
                        **operation,
                    },
                    separators=(",", ":"),
                )
            )
            _request_stats.reset(token)
