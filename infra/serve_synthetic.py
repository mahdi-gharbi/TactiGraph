"""Disposable HTTP server for CI/load tests; invented data and an explicit mocked LLM."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
import uvicorn
from pydantic import SecretStr

from tactigraph.api.app import create_app
from tactigraph.config import Settings
from tactigraph.db import initialize, make_engine
from tactigraph.testing import seed_synthetic


def mock_query_provider(request):
    """Exercise the real planner contract without contacting a provider or spending tokens."""
    plan = {
        "status": "ready",
        "intent": "chance_creation",
        "before": None,
        "after": None,
        "methodology_topics": ["shots"],
        "reason": None,
    }
    return httpx.Response(
        200,
        json={
            "id": "synthetic-query",
            "model": "openai/gpt-oss-20b",
            "system_fingerprint": "mock-no-inference",
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(plan)}}],
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8011)
    parser.add_argument("--public", action="store_true")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="tactigraph-synthetic-") as directory:
        settings = Settings(
            _env_file=None,
            database_url=f"sqlite:///{Path(directory).as_posix()}/fixture.db",
            data_dir=Path(directory),
            mode="public" if args.public else "local",
            groq_api_key=SecretStr("synthetic-test-value"),
        )
        engine = make_engine(settings)
        seed_synthetic(initialize(engine))
        app = create_app(settings, engine, include_secondary_league=False)
        app.state.query_transport = httpx.MockTransport(mock_query_provider)
        print(
            "Synthetic fixture only; query interpretation is mocked; no provider call.", flush=True
        )
        uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
