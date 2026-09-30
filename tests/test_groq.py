import json

import httpx
import pytest

from tactigraph.analyst.contracts import AnalystReport
from tactigraph.analyst.groq import select_claims
from tactigraph.config import Settings


@pytest.fixture
def report():
    return AnalystReport.model_validate(
        {
            "report_id": "test-report",
            "status": "verified",
            "generated_at": "2026-09-25",
            "arguments": {"match_id": 1, "team_id": 10, "intent": "period_comparison"},
            "claims": [
                {
                    "kind": "measured_fact",
                    "predicate": "compare_metric",
                    "text": "Shots: 1 → 2.",
                    "result_id": "r1",
                    "evidence_ids": ["e1"],
                    "before": 1,
                    "after": 2,
                    "unit": "shots",
                },
                {
                    "kind": "limitation",
                    "predicate": "no_causality",
                    "text": "No causal inference.",
                    "result_id": "r1",
                    "evidence_ids": [],
                },
            ],
            "evidence": {
                "result_id": "r1",
                "tool": "compare_windows",
                "arguments": {"match_id": 1, "team_id": 10, "intent": "period_comparison"},
                "before": [],
                "after": [],
                "source_commit": "synthetic",
                "source_sha256": "a" * 64,
                "metric_version": "test",
                "model_versions": {},
                "quality_warnings": [],
                "supporting_event_ids": {"e1": ["private-event-uuid"]},
            },
            "trace": ["verify_claims", "render_or_abstain"],
            "tool_calls": 1,
            "verification_rejections": 0,
            "qualifications": [],
        }
    )


@pytest.mark.parametrize(
    "outputs,mode,repairs",
    [
        (['{"claim_ids":["c0"]}'], "groq_selection", 0),
        (['{"claim_ids":["invented"]}', '{"claim_ids":["c0"]}'], "groq_selection", 1),
        (['{"claim_ids":["c0"],"statistic":999}'] * 2, "deterministic_fallback", 1),
    ],
)
def test_remote_selection_is_bounded_and_never_sends_raw_evidence(report, outputs, mode, repairs):
    calls = []

    def remote(request):
        body = json.loads(request.content)
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        uses_test_key = request.headers["authorization"] == "Bearer test-secret"
        assert uses_test_key
        assert "tools" not in body
        assert "private-event-uuid" not in request.content.decode()
        assert "source_sha256" not in request.content.decode()
        assert body["response_format"]["json_schema"]["strict"]
        calls.append(body)
        return httpx.Response(
            200,
            json={
                "model": "openai/gpt-oss-20b",
                "id": "req-test",
                "system_fingerprint": "fp-test",
                "choices": [
                    {"finish_reason": "stop", "message": {"content": outputs[len(calls) - 1]}}
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    result = select_claims(
        report, Settings(GROQ_API_KEY="test-secret"), transport=httpx.MockTransport(remote)
    )
    assert result.mode == mode
    assert result.generation.repairs == repairs
    assert result.generation.attempts == len(calls) <= 2
    assert result.generation.provider == "groq"
    assert result.generation.digest is None
    assert result.claims == report.claims
    assert "test-secret" not in result.model_dump_json()


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_provider_failures_never_leak_response_or_retry_indefinitely(report, status):
    calls = []

    def remote(request):
        calls.append(request)
        return httpx.Response(status, text="test-secret provider response")

    result = select_claims(
        report, Settings(GROQ_API_KEY="test-secret"), transport=httpx.MockTransport(remote)
    )
    assert result.mode == "deterministic_fallback"
    assert len(calls) == 1
    assert "test-secret" not in result.model_dump_json()


def test_missing_key_and_public_mode_never_call_provider(report):
    def forbidden(request):
        pytest.fail("No external request is allowed")

    transport = httpx.MockTransport(forbidden)
    assert (
        select_claims(report, Settings(GROQ_API_KEY=""), transport=transport).generation.attempts
        == 0
    )
    with pytest.raises(ValueError, match="public mode"):
        select_claims(report, Settings(mode="public", GROQ_API_KEY="secret"), transport=transport)
    assert "secret" not in repr(Settings(GROQ_API_KEY="secret"))
