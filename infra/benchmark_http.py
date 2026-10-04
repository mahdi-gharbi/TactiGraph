"""Closed-loop HTTP benchmark: actual sockets, fixed workload, disclosed synthetic scope."""

import argparse
import asyncio
import json
import math
import os
import platform
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

WORKLOAD = (
    ("GET", "/api/v1/matches/900001/summary", None),
    ("GET", "/api/v1/matches/900001/shots", None),
    (
        "POST",
        "/api/v1/analyst/report",
        {"match_id": 900001, "team_id": 10, "intent": "chance_creation"},
    ),
    ("GET", "/api/v1/evidence/shots-900001-0-0-0-0-0", None),
)


def percentile(values, p):
    ordered = sorted(values)
    return round(ordered[max(0, math.ceil(len(ordered) * p) - 1)], 3) if ordered else None


async def measure(base_url, users, per_user, timeout):
    results = []
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        trust_env=False,
        limits=httpx.Limits(max_connections=users, max_keepalive_connections=users),
    ) as client:
        # Warm all four routes through the same HTTP stack, excluded from measurement.
        for method, path, payload in WORKLOAD:
            response = await client.request(method, path, json=payload)
            response.raise_for_status()

        async def worker(worker_id):
            for i in range(per_user):
                method, path, payload = WORKLOAD[(i + worker_id) % len(WORKLOAD)]
                start = time.perf_counter()
                try:
                    response = await client.request(method, path, json=payload)
                    status = response.status_code
                    outcome = "ok" if status == 200 else f"http_{status}"
                except httpx.TimeoutException:
                    outcome = "timeout"
                except httpx.HTTPError:
                    outcome = "transport_error"
                results.append((method + " " + path, outcome, 1000 * (time.perf_counter() - start)))

        start = time.perf_counter()
        await asyncio.gather(*(worker(i) for i in range(users)))
        elapsed = time.perf_counter() - start
    durations = [r[2] for r in results]
    errors = Counter(r[1] for r in results if r[1] != "ok")
    routes = []
    for route in sorted({r[0] for r in results}):
        subset = [r for r in results if r[0] == route]
        times = [r[2] for r in subset]
        routes.append(
            {
                "route": route,
                "requests": len(subset),
                "errors": sum(r[1] != "ok" for r in subset),
                "p50_ms": percentile(times, 0.50),
                "p95_ms": percentile(times, 0.95),
                "p99_ms": percentile(times, 0.99),
            }
        )
    return {
        "concurrent_users": users,
        "requests": len(results),
        "duration_seconds": round(elapsed, 3),
        "requests_per_second": round(len(results) / elapsed, 3),
        "errors": dict(errors),
        "error_rate": sum(errors.values()) / len(results),
        "p50_ms": percentile(durations, 0.5),
        "p95_ms": percentile(durations, 0.95),
        "p99_ms": percentile(durations, 0.99),
        "routes": routes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    parser.add_argument("--users", type=int, nargs="+", default=[1, 5, 10])
    parser.add_argument("--requests-per-user", type=int, default=40)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument(
        "--output", type=Path, default=Path("output/benchmarks/synthetic-http.json")
    )
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("Use a service URL without credentials, query or fragment")
    if not all(1 <= u <= 100 for u in args.users) or not 4 <= args.requests_per_user <= 10000:
        parser.error("Use 1–100 users and 4–10000 requests per user")
    with httpx.Client(base_url=args.base_url, timeout=5, trust_env=False) as client:
        summary = client.get("/api/v1/matches/900001/summary").json()
        if summary.get("model", {}).get("model_version") != "synthetic-ci-v1":
            parser.error("This workload requires the disposable synthetic server")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Invented 88-event SQLite match; one local uvicorn process; actual HTTP sockets; "
        "no real LLM or upstream data. Not a production capacity claim.",
        "method": "Closed-loop concurrent clients without think time; 4 warmup calls per scenario; "
        "nearest-rank percentiles include failures; client and server share host "
        "when using default URL.",
        "client": {
            "python": platform.python_version(),
            "os": platform.system(),
            "os_release": platform.release(),
            "machine": platform.machine(),
            "logical_cpus": os.cpu_count(),
            "httpx": httpx.__version__,
        },
        "requests_per_user": args.requests_per_user,
        "timeout_seconds": args.timeout,
        "scenarios": [
            asyncio.run(measure(args.base_url, u, args.requests_per_user, args.timeout))
            for u in args.users
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if any(s["error_rate"] for s in report["scenarios"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
