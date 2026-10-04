import asyncio
import json
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from tactigraph.analyst import query_evaluation as evaluation
from tactigraph.retrieval.v2 import VERSION, corpus


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def synthetic_review(path):
    """Only synthetic pytest temporary files receive fabricated fixture identities."""
    value = evaluation.read_json(path)
    value.update(
        reviewer="Synthetic pytest reviewer",
        independent_of_authors=True,
        reviewed_at_iso=datetime.now(timezone.utc).isoformat(),
        corpus_approved=True,
        protocol_approved=True,
    )
    for scenario in value["scenarios"]:
        scenario.update(
            expectations_approved=True, translation_approved=True, relevance_labels_approved=True
        )
    save(path, value)
    return value


def test_dataset_has_100_grouped_bilingual_scenarios_and_balanced_contract():
    _, rows, hashes = evaluation.load_package()
    assert len(rows) == 100
    assert sum(row["partition"] == "development" for row in rows) == 60
    assert set(row["league"] for row in rows) == {"wsl", "premier-league"}
    assert hashes["corpus_version"] == VERSION
    assert all(set(row["questions"]) == {"en", "fr"} for row in rows)


def test_schema_export_is_blank_and_preserves_entered_rating(tmp_path):
    packet, ratings = evaluation.prepare_review(tmp_path)
    values = evaluation.read_json(ratings)
    assert values["reviewer"] == ""
    assert all(row["expectations_approved"] is None for row in values["scenarios"])
    values["scenarios"][0]["notes"] = "Existing reviewer note must survive."
    save(ratings, values)
    evaluation.prepare_review(tmp_path)
    assert evaluation.read_json(ratings) == values
    assert len(evaluation.read_json(packet)["scenarios"]) == 100


def test_unreviewed_freeze_and_live_execution_stop_before_runner(tmp_path):
    _, ratings = evaluation.prepare_review(tmp_path)
    with pytest.raises(ValueError, match="reviewer"):
        evaluation.freeze(ratings, tmp_path / "freeze.json", candidate={"model": "mock"})
    calls = []
    with pytest.raises(ValueError, match="review"):
        asyncio.run(
            evaluation.evaluate(
                lambda *args: calls.append(args), context_resolver=lambda _: {}, phase="final"
            )
        )
    assert calls == []
    with pytest.raises(ValueError, match="mocked"):
        asyncio.run(
            evaluation.evaluate(
                lambda *args: calls.append(args), context_resolver=lambda _: {}, runner_kind="live"
            )
        )
    assert calls == []


def test_review_cannot_approve_changed_scenarios_or_incomplete_decisions(tmp_path):
    _, ratings = evaluation.prepare_review(tmp_path)
    value = synthetic_review(ratings)
    evaluation.validate_review(ratings)
    value["scenarios"][0]["translation_approved"] = None
    save(ratings, value)
    with pytest.raises(ValueError, match="unapproved"):
        evaluation.validate_review(ratings)
    value["scenarios"][0]["translation_approved"] = True
    value["scenarios"][0]["scenario_sha256"] = "0" * 64
    save(ratings, value)
    with pytest.raises(ValueError, match="changed"):
        evaluation.validate_review(ratings)


@pytest.mark.parametrize(
    "change",
    [
        {"independent_of_authors": False},
        {"reviewer": "Codex"},
        {"reviewer": "mahdi-gharbi"},
        {"reviewer": "Mahdi Elgharbi"},
        {"reviewed_at_iso": "yesterday"},
        {"reviewed_at_iso": "2000-01-01T12:00:00"},
        {"reviewed_at_iso": "2999-01-01T12:00:00Z"},
    ],
)
def test_review_requires_independent_identity_and_dated_attestation(tmp_path, change):
    _, ratings = evaluation.prepare_review(tmp_path)
    value = synthetic_review(ratings)
    value.update(change)
    save(ratings, value)
    with pytest.raises(ValueError):
        evaluation.validate_review(ratings)


def test_freeze_is_immutable_and_detects_code_changes(tmp_path, monkeypatch):
    _, ratings = evaluation.prepare_review(tmp_path)
    synthetic_review(ratings)
    lock = tmp_path / "freeze.json"
    evaluation.freeze(ratings, lock, candidate={"model": "synthetic-model"})
    evaluation.require_frozen(ratings, lock)
    with pytest.raises(FileExistsError):
        evaluation.freeze(ratings, lock, candidate={"model": "synthetic-model"})
    monkeypatch.setattr(evaluation, "code_fingerprints", lambda: {"changed": "a"})
    with pytest.raises(ValueError, match="code changed"):
        evaluation.require_frozen(ratings, lock)


def test_methodology_citation_verifier_rejects_forged_text_wrong_language_and_duplicates():
    chunk = next(item.model_dump() for item in corpus() if item.language == "en")
    assert evaluation.verify_methodology_citations([chunk], "en")
    assert not evaluation.verify_methodology_citations([chunk], "fr")
    assert not evaluation.verify_methodology_citations([chunk, chunk], "en")
    assert not evaluation.verify_methodology_citations([{**chunk, "text": "invented"}], "en")


def test_smoke_keeps_final_unexecuted_and_provider_outages_out_of_abstention_success():
    _, scenarios, _ = evaluation.load_package()
    by_question = {question: row for row in scenarios for question in row["questions"].values()}
    chunks = {chunk.chunk_id: chunk.model_dump() for chunk in corpus()}
    visited = []
    outage_case = next(
        row
        for row in scenarios
        if row["category"] == "unsupported" and row["partition"] == "development"
    )

    def runner(request, league):
        row = by_question[request["question"]]
        assert row["partition"] == "development"
        assert row["league"] == league
        visited.append(row["scenario_id"])
        expected = row["expected"]
        # Deliberately expected-output fixtures test the evaluator, never model quality.
        return {
            "status": expected["status"],
            "plan": expected,
            "report": {"fixture": True} if expected["intent"] else None,
            "methodology": [
                chunks[f"{VERSION}:{topic}:{request['language']}"]
                for topic in expected["relevant_topics"]
            ],
            "metadata": {
                "provider_success": expected["status"] == "answered",
                "attempts": int(expected["status"] == "answered"),
                "input_tokens": 10,
                "output_tokens": 2,
                "latency_ms": 1,
                "fallback_reason": "timeout" if row == outage_case else None,
                "repairs": 1 if row == outage_case else 0,
                "provider_errors": 1 if row == outage_case else 0,
                "usage_complete": row != outage_case,
            },
        }

    result = asyncio.run(
        evaluation.evaluate(
            runner,
            context_resolver=lambda _: {"match_id": 1, "team_id": 10},
            verify_all_claims=lambda _: {"all_claims_verified": True},
        )
    )
    assert len(visited) == 120 and len(set(visited)) == 60
    assert not result["metrics_are_model_evidence"]
    assert result["acceptance"]["status"] == "not_assessed_mock"
    summary = result["summary"]
    assert summary["supported_cases"] == 96
    assert summary["ambiguous_cases"] == 12 and summary["unsupported_cases"] == 12
    assert summary["supported_task_success_rate"] == 1
    assert summary["correct_unsupported_abstention_rate"] == pytest.approx(10 / 12)
    assert summary["fallbacks"] == 2
    assert summary["provider_success_rate_among_attempts"] == 1
    assert summary["independent_retrieval_cases"] == 36
    assert summary["repairs"] == 2 and summary["provider_errors"] == 2
    assert summary["usage_incomplete_cases"] == 2
    assert not summary["usage_complete"]
    assert summary["token_totals_status"] == "observed_lower_bound"
    assert summary["input_tokens"] == 1200 and summary["output_tokens"] == 240


def paired_fixture():
    rows = []
    for league in ("wsl", "premier-league"):
        for intent in ("period_comparison", "chance_creation", "network_concentration"):
            for language in ("en", "fr"):
                report = {
                    "claims": [{"text": "Synthetic fixture, not actual match evidence"}],
                    "qualifications": [],
                    "evidence": {"fixture": True},
                    "mode": "private-provider-label",
                }
                rows.append(
                    {
                        "case_id": f"{league}:{intent}:{language}",
                        "league": league,
                        "intent": intent,
                        "language": language,
                        "question": "Fixture?",
                        "guided": report,
                        "query": {"report": report, "metadata": {"model": "private"}},
                    }
                )
    return rows


def test_blinded_export_hashes_exact_outputs_hides_provider_and_preserves_ratings(tmp_path):
    rows = paired_fixture()
    packet, ratings, key = evaluation.prepare_blind_pairs(rows, tmp_path)
    payload = evaluation.read_json(packet)
    assert "private-provider-label" not in packet.read_text(encoding="utf-8")
    assert "metadata" not in packet.read_text(encoding="utf-8")
    assert len(payload["pairs"]) == 12 and key.exists()
    values = evaluation.read_json(ratings)
    assert values["reviewer"] == "" and all(row["preferred"] is None for row in values["pairs"])
    values["pairs"][0]["A"]["notes"] = "Keep this original note"
    save(ratings, values)
    evaluation.prepare_blind_pairs(rows, tmp_path)
    assert evaluation.read_json(ratings) == values
    changed = deepcopy(rows)
    changed[0]["question"] = "Changed question"
    with pytest.raises(ValueError, match="changed"):
        evaluation.prepare_blind_pairs(changed, tmp_path)
    with pytest.raises(ValueError, match="reviewer"):
        evaluation.validate_pair_ratings(packet, ratings)


def test_blind_export_refuses_missing_or_duplicate_cells_and_empty_outputs(tmp_path):
    rows = paired_fixture()
    with pytest.raises(ValueError, match="twelve"):
        evaluation.prepare_blind_pairs(rows[:-1], tmp_path)
    rows[0]["query"] = {"report": None}
    with pytest.raises(ValueError, match="actual claims"):
        evaluation.prepare_blind_pairs(rows, tmp_path)


def test_pair_generation_requires_review_before_any_guided_computation(tmp_path):
    calls = []
    with pytest.raises(ValueError, match="review"):
        asyncio.run(
            evaluation.prepare_pairs_from_result(
                tmp_path / "missing.json",
                None,
                None,
                tmp_path,
                guided_runner=lambda *args: calls.append(args),
            )
        )
    assert calls == []


def test_pair_generation_reconstructs_real_synthetic_support_and_never_replaces_failure(
    database, tmp_path, monkeypatch
):
    from tactigraph.analyst.contracts import AnalystRequest
    from tactigraph.analyst.query import compute
    from tactigraph.analyst.rendering import translate_report
    from tactigraph.analyst.workflow import run
    from tactigraph.testing import MATCH_ID, seed_synthetic

    _, sessions = database
    seed_synthetic(sessions)
    scenarios, cases, outputs = [], [], []
    hashes = {"fixture": "synthetic-in-memory-only"}
    sources = {
        f"final:{league}": {"match_id": MATCH_ID, "team_id": 10}
        for league in ("wsl", "premier-league")
    }
    for league in ("wsl", "premier-league"):
        for intent in ("period_comparison", "chance_creation", "network_concentration"):
            arguments = AnalystRequest(match_id=MATCH_ID, team_id=10, intent=intent)
            scenario = {
                "scenario_id": f"synthetic:{league}:{intent}",
                "partition": "final",
                "category": "analytic",
                "league": league,
                "questions": {"en": f"Synthetic {intent}", "fr": f"Fictif {intent}"},
                "expected": {
                    "intent": intent,
                    "before": arguments.before.model_dump(),
                    "after": arguments.after.model_dump(),
                },
            }
            scenarios.append(scenario)
            for language in ("en", "fr"):
                report = compute(sessions, arguments, language)
                request = {
                    "match_id": MATCH_ID,
                    "team_id": 10,
                    "language": language,
                    "question": scenario["questions"][language],
                }
                response = {"status": "answered", "report": report.model_dump(mode="json")}
                outputs.append({"league": league, "request": request, "response": response})
                cases.append(
                    {
                        "scenario_id": scenario["scenario_id"],
                        "language": language,
                        "request_sha256": evaluation.digest(request),
                        "response_sha256": evaluation.digest(response),
                    }
                )
    # Test-only gate stubs exercise generated outputs without fabricating a real review.
    monkeypatch.setattr(
        evaluation, "require_frozen", lambda *_: {"candidate": {"source_manifests": sources}}
    )
    monkeypatch.setattr(evaluation, "load_package", lambda: ({}, scenarios, hashes))
    result = {
        "phase": "final",
        "runner_kind": "live",
        "metrics_are_model_evidence": True,
        "hashes": hashes,
        "source_manifests": sources,
        "cases": cases,
        "outputs": outputs,
    }
    result_path = tmp_path / "synthetic-result.json"
    save(result_path, result)

    def guided_runner(arguments, league, language):
        with sessions() as session:
            return translate_report(run(session, arguments), language)

    paths = asyncio.run(
        evaluation.prepare_pairs_from_result(
            result_path,
            "synthetic-review",
            "synthetic-freeze",
            tmp_path / "paired",
            guided_runner=guided_runner,
        )
    )
    assert len(evaluation.read_json(paths[0])["pairs"]) == 12
    outputs[0]["response"] = {"status": "abstained", "report": None}
    cases[0]["response_sha256"] = evaluation.digest(outputs[0]["response"])
    save(result_path, result)
    with pytest.raises(ValueError, match="Selected query failed"):
        asyncio.run(
            evaluation.prepare_pairs_from_result(
                result_path,
                "synthetic-review",
                "synthetic-freeze",
                tmp_path / "replaced",
                guided_runner=guided_runner,
            )
        )
    assert not (tmp_path / "replaced").exists()
