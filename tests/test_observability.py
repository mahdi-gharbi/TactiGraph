import json

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from tactigraph.api.app import create_app
from tactigraph.config import Settings
from tactigraph.observability import RequestTelemetryMiddleware, Telemetry, logger, record_operation


def test_request_logs_are_correlated_bounded_and_exclude_request_data(database, monkeypatch):
    engine, _ = database
    app = create_app(Settings(_env_file=None, mode="local"), engine, include_secondary_league=False)
    logs = []
    monkeypatch.setattr(logger, "info", lambda value: logs.append(json.loads(value)))

    @app.post("/operational-test/{item}", include_in_schema=False)
    def synthetic_operation(item: str, request: Request):
        record_operation(request, provider="test", fallback=True, outcome="abstained")
        record_operation(request, prompt="secret", provider="bad\nlabel", generation_ms=-5)
        return {"ok": True}

    with TestClient(app) as client:
        response = client.post(
            "/operational-test/private-item?api_key=secret",
            json={"question": "private question"},
            headers={"Authorization": "Bearer secret", "X-Request-ID": "untrusted"},
        )
        assert len(response.headers["x-request-id"]) == 32
        entry = logs[-1]
        assert entry["request_id"] == response.headers["x-request-id"]
        assert entry["route"] == "/operational-test/{item}"
        assert entry["provider"] == "test" and entry["fallback"]
        serialized = json.dumps(logs)
        for excluded in ("secret", "private-item", "private question", "untrusted", "bad"):
            assert excluded not in serialized
        assert client.get("/api/v1/matches").status_code == 200
        assert logs[-1]["db_queries"] > 0 and logs[-1]["db_ms"] >= 0
        snapshot = client.get("/api/v1/operations").json()
        row = next(r for r in snapshot["routes"] if "operational-test" in r["route"])
        assert row["fallbacks"] == row["requests"] == 1


def test_errors_are_recorded_without_exception_messages_and_public_metrics_hidden(
    database, monkeypatch
):
    engine, _ = database
    app = create_app(Settings(_env_file=None, mode="public"), engine)
    logs = []
    monkeypatch.setattr(logger, "info", lambda value: logs.append(json.loads(value)))

    @app.get("/operational-error", include_in_schema=False)
    def failure():
        raise RuntimeError("sensitive provider response")

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/api/v1/operations").status_code == 404
        assert client.get("/operational-error").status_code == 500
        assert logs[-1]["status"] == 500
        assert "sensitive" not in json.dumps(logs)
        assert client.get("/not-a-route/private").status_code == 404
        assert logs[-1]["route"] == "unmatched"


def test_mounted_league_has_one_correlated_log_and_prefixed_route(monkeypatch):
    telemetry = Telemetry()
    parent, league = FastAPI(), FastAPI()
    for app in (parent, league):
        app.add_middleware(RequestTelemetryMiddleware, telemetry=telemetry)
    logs = []
    monkeypatch.setattr(logger, "info", lambda value: logs.append(json.loads(value)))

    @league.get("/api/v1/example/{item}")
    def example(item: str, request: Request):
        record_operation(request, provider="mock", outcome="answered")
        return {"request_id": request.state.request_id}

    parent.mount("/leagues/premier-league", league)
    with TestClient(parent) as client:
        response = client.get("/leagues/premier-league/api/v1/example/123")
    assert len(response.headers.get_list("x-request-id")) == len(logs) == 1
    assert response.headers["x-request-id"] == response.json()["request_id"]
    assert logs[0]["request_id"] == response.json()["request_id"]
    assert logs[0]["provider"] == "mock"
    assert logs[0]["route"] == "/leagues/premier-league/api/v1/example/{item}"
    assert telemetry.snapshot()["routes"][0]["requests"] == 1
