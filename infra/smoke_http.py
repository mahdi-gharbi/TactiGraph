"""Verify an actual HTTP process, including the production review gate."""

import argparse
import json
import time
from urllib.parse import urlsplit

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    parser.add_argument("--public", action="store_true")
    parser.add_argument("--wait-seconds", type=float, default=30)
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("Use a service URL without credentials, query or fragment")
    with httpx.Client(base_url=args.base_url, timeout=5, trust_env=False) as client:
        deadline = time.monotonic() + args.wait_seconds
        while True:
            try:
                health = client.get("/api/v1/health")
                if health.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() >= deadline:
                raise SystemExit("HTTP service did not become healthy before the deadline")
            time.sleep(0.25)
        assert health.headers.get("x-request-id"), "Missing request correlation"
        assert client.get("/").status_code == 200
        # A clean or synthetic deployment has no approved human review: readiness stays closed.
        assert client.get("/api/v1/ready").status_code == 503
        for path in ("/.env", "/data/tactigraph.db", "/output/release-review/reports.json"):
            assert client.get(path).status_code == 404
        if args.public:
            assert health.json()["mode"] == "public"
            assert client.get("/api/v1/operations").status_code == 404
            assert client.get("/api/v1/matches/900001/events").status_code == 404
            guided = {"match_id": 900001, "team_id": 10, "intent": "chance_creation"}
            assert client.post("/api/v1/analyst/report", json=guided).status_code == 404
            query = {
                "match_id": 900001,
                "team_id": 10,
                "question": "Compare shots",
                "language": "en",
            }
            assert client.post("/api/v1/analyst/query", json=query).status_code == 404
        else:
            assert client.get("/api/v1/operations").status_code == 200
            assert client.get("/api/v1/matches/900001/shots").json()["total_shots"] == 4
    print(
        json.dumps(
            {
                "http_smoke": "passed",
                "public_mode": args.public,
                "readiness": "503 expected: review pending",
            }
        )
    )


if __name__ == "__main__":
    main()
