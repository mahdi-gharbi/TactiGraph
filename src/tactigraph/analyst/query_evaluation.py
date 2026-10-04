"""Draft contracts, human review gates and separately labelled query-v2 evaluation.

No provider is imported here. A runner is injected explicitly; live execution and
final evaluation require a reviewed, unchanged frozen package.
"""

import hashlib
import inspect
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from tactigraph.retrieval.v2 import VERSION, corpus, fingerprint, search

PROTOCOL = Path("configs/analyst-query-v2.json")
SCENARIOS = Path("configs/analyst-query-scenarios-v2.json")


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def create_json(path, value):
    """Never erase an existing worksheet, rating, result or freeze marker."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def load_package(protocol_path=PROTOCOL, scenarios_path=SCENARIOS):
    protocol, payload = read_json(protocol_path), read_json(scenarios_path)
    rows = payload["scenarios"]
    if protocol["version"] != "analyst-query-v2" or payload["version"] != protocol["version"]:
        raise ValueError("Unexpected query evaluation version")
    if len(rows) != 100 or len({row["scenario_id"] for row in rows}) != 100:
        raise ValueError("Expected exactly 100 unique semantic scenarios")
    if Counter(row["partition"] for row in rows) != {"development": 60, "final": 40}:
        raise ValueError("Expected 60 development and 40 final semantic scenarios")
    groups = Counter(row["category"] for row in rows)
    if (
        groups.get("analytic") != 50
        or groups.get("methodology", 0) + groups.get("mixed", 0) != 30
        or groups.get("ambiguous", 0) + groups.get("unsupported", 0) != 20
    ):
        raise ValueError("Unexpected scenario category counts")
    families = {}
    known = {chunk.topic for chunk in corpus()}
    for row in rows:
        if set(row["questions"]) != {"en", "fr"} or any(
            not isinstance(question, str) or not 0 < len(question) <= 500
            for question in row["questions"].values()
        ):
            raise ValueError("Every semantic scenario needs bounded EN and FR translations")
        if row["league"] not in {"wsl", "premier-league"}:
            raise ValueError("Unexpected league")
        previous = families.setdefault(row["family"], row["partition"])
        if previous != row["partition"]:
            raise ValueError("A scenario family crosses the development/final split")
        if not set(row["expected"]["relevant_topics"]) <= known:
            raise ValueError("Unknown methodology relevance label")
    hashes = {
        "protocol_sha256": digest(protocol),
        "scenarios_sha256": digest(payload),
        "corpus_sha256": fingerprint(),
        "corpus_version": VERSION,
    }
    return protocol, rows, hashes


def prepare_review(destination, *, protocol_path=PROTOCOL, scenarios_path=SCENARIOS):
    protocol, rows, hashes = load_package(protocol_path, scenarios_path)
    destination = Path(destination)
    packet = {
        "version": protocol["version"],
        "status": "awaiting_independent_review",
        "hashes": hashes,
        "protocol": protocol,
        "methodology": [chunk.model_dump() for chunk in corpus()],
        "scenarios": rows,
    }
    packet_path, ratings_path = destination / "packet.json", destination / "ratings.json"
    if packet_path.exists() and read_json(packet_path) != packet:
        raise ValueError("Review inputs changed; use a new destination and preserve old ratings")
    if not packet_path.exists():
        create_json(packet_path, packet)
    if ratings_path.exists():
        if read_json(ratings_path).get("hashes") != hashes:
            raise ValueError("Existing ratings refer to different inputs; do not overwrite them")
        return packet_path, ratings_path
    create_json(
        ratings_path,
        {
            "version": protocol["version"],
            "hashes": hashes,
            "reviewer": "",
            "reviewed_at_iso": "",
            "independent_of_authors": None,
            "corpus_approved": None,
            "protocol_approved": None,
            "scenarios": [
                {
                    "scenario_id": row["scenario_id"],
                    "scenario_sha256": digest(row),
                    "expectations_approved": None,
                    "translation_approved": None,
                    "relevance_labels_approved": None,
                    "notes": "",
                }
                for row in rows
            ],
        },
    )
    return packet_path, ratings_path


def validate_identity(review, authors=()):
    reviewer = review.get("reviewer", "").strip()
    if len(reviewer) < 3 or reviewer.casefold() in {name.casefold() for name in authors}:
        raise ValueError("A named independent human reviewer is required")
    if review.get("independent_of_authors") is not True:
        raise ValueError("Reviewer independence must be explicitly attested")
    try:
        reviewed = datetime.fromisoformat(review["reviewed_at_iso"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("A valid ISO review timestamp is required") from error
    if reviewed.tzinfo is None or reviewed > datetime.now(timezone.utc):
        raise ValueError("Review timestamp needs a timezone and cannot be in the future")


def validate_review(review_path, *, protocol_path=PROTOCOL, scenarios_path=SCENARIOS):
    protocol, rows, hashes = load_package(protocol_path, scenarios_path)
    review = read_json(review_path)
    validate_identity(review, protocol["authors"])
    if review.get("hashes") != hashes:
        raise ValueError("Review hashes do not match current scenario, protocol and corpus")
    if review.get("corpus_approved") is not True or review.get("protocol_approved") is not True:
        raise ValueError("The methodology corpus and protocol require independent approval")
    ratings = review.get("scenarios", [])
    if len(ratings) != len(rows) or len({row["scenario_id"] for row in ratings}) != len(rows):
        raise ValueError("Every semantic scenario requires exactly one review")
    by_id = {row["scenario_id"]: row for row in ratings}
    for scenario in rows:
        rating = by_id.get(scenario["scenario_id"], {})
        if rating.get("scenario_sha256") != digest(scenario) or not all(
            rating.get(field) is True
            for field in (
                "expectations_approved",
                "translation_approved",
                "relevance_labels_approved",
            )
        ):
            raise ValueError(f"Scenario {scenario['scenario_id']} is unapproved or changed")
    return {**hashes, "review_sha256": digest(review), "reviewer": review["reviewer"]}


def code_fingerprints():
    directory = Path(__file__).parent
    paths = [
        directory / name
        for name in (
            "query.py",
            "query_contracts.py",
            "query_evaluation.py",
            "verification.py",
            "workflow.py",
            "rendering.py",
        )
    ] + [directory.parent / "retrieval" / "v2.py"]
    return {
        str(path.relative_to(directory.parent)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    } | {
        "scripts/query_workbench.py": hashlib.sha256(
            Path("scripts/query_workbench.py").read_bytes()
        ).hexdigest()
    }


def freeze(
    review_path, destination, *, candidate, protocol_path=PROTOCOL, scenarios_path=SCENARIOS
):
    """Explicit freeze, never called automatically by evaluation or review export."""
    reviewed = validate_review(
        review_path, protocol_path=protocol_path, scenarios_path=scenarios_path
    )
    if not candidate or not candidate.get("model"):
        raise ValueError("A concrete model candidate is required before freezing")
    lock = {
        "version": "analyst-query-v2",
        "reviewed": reviewed,
        "candidate": candidate,
        "code": code_fingerprints(),
        "frozen_at": datetime.now(timezone.utc).isoformat(),
    }
    create_json(destination, lock)
    return lock


def require_frozen(review_path, freeze_path, *, protocol_path=PROTOCOL, scenarios_path=SCENARIOS):
    if not review_path or not freeze_path:
        raise ValueError("Independent review and an explicit freeze are required")
    reviewed = validate_review(
        review_path, protocol_path=protocol_path, scenarios_path=scenarios_path
    )
    lock = read_json(freeze_path)
    if lock.get("reviewed") != reviewed or lock.get("code") != code_fingerprints():
        raise ValueError("Frozen review or code changed; prepare a new version")
    return lock


def as_dict(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def retrieval_scores(ranking, relevant):
    if not relevant:
        return None, None
    ids = list(dict.fromkeys(ranking[:5]))
    return len(set(ids) & set(relevant)) / len(set(relevant)), next(
        (1 / rank for rank, chunk_id in enumerate(ids, 1) if chunk_id in relevant), 0.0
    )


def percentile(values, quantile):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * quantile
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def verify_methodology_citations(chunks, language):
    """Resolve every displayed citation to exact frozen text and language/version."""
    approved = {chunk.chunk_id: chunk.model_dump() for chunk in corpus()}
    seen = set()
    for item in chunks:
        chunk = as_dict(item)
        expected = approved.get(chunk.get("chunk_id"))
        if expected is None or chunk["chunk_id"] in seen or chunk.get("language") != language:
            return False
        seen.add(chunk["chunk_id"])
        if any(
            chunk.get(field) != expected[field]
            for field in ("document_id", "version", "section", "topic", "language", "text")
        ):
            return False
        if not isinstance(chunk.get("score"), (float, int)) or not math.isfinite(chunk["score"]):
            return False
    return True


async def evaluate(
    runner,
    *,
    context_resolver,
    phase="dev_smoke",
    runner_kind="mock",
    verify_all_claims=None,
    review_path=None,
    freeze_path=None,
    protocol_path=PROTOCOL,
    scenarios_path=SCENARIOS,
):
    """runner(request, league) and context_resolver(scenario) are supplied by the caller.

    dev_smoke permits mocked providers only. It tests execution contracts and emits
    no final/generalization claim. Real providers require approved frozen inputs.
    """
    if phase not in {"dev_smoke", "development", "final"} or runner_kind not in {"mock", "live"}:
        raise ValueError("Unknown phase or runner kind")
    if phase == "dev_smoke" and runner_kind != "mock":
        raise ValueError("Draft smoke must use a mocked provider")
    protocol, scenarios, hashes = load_package(protocol_path, scenarios_path)
    lock = None
    if phase != "dev_smoke" or runner_kind == "live":
        lock = require_frozen(
            review_path, freeze_path, protocol_path=protocol_path, scenarios_path=scenarios_path
        )
    partition = "final" if phase == "final" else "development"
    records = []
    for scenario in scenarios:
        if scenario["partition"] != partition:
            continue
        context = context_resolver(scenario)
        for language, question in scenario["questions"].items():
            request = {
                **scenario["context"]["ui_windows"],
                **context,
                "question": question,
                "language": language,
            }
            response = runner(request, scenario["league"])
            if inspect.isawaitable(response):
                response = await response
            payload = as_dict(response)
            metadata, plan = payload.get("metadata", {}), payload.get("plan") or {}
            if (
                lock
                and metadata.get("attempts", 0)
                and metadata.get("model") != lock["candidate"]["model"]
            ):
                raise ValueError("Runner used a model different from the frozen candidate")
            expected = scenario["expected"]
            exact = payload.get("status") == expected["status"]
            if expected["status"] == "answered":
                exact &= plan.get("intent") == expected["intent"]
                for bound in ("before", "after"):
                    if expected[bound] is not None:
                        exact &= plan.get(bound) == expected[bound]
                exact &= set(plan.get("methodology_topics", [])) == set(
                    expected["methodology_topics"]
                )
            report = (
                getattr(response, "report", None)
                if hasattr(response, "report")
                else payload.get("report")
            )
            verified, verification_error = None, None
            if report is not None:
                if verify_all_claims is None:
                    raise ValueError("An all-claim verifier is required for numerical reports")
                try:
                    verification = verify_all_claims(report)
                    verified = verification.get("all_claims_verified") is True
                except ValueError:
                    verified, verification_error = False, "all_claim_verification_failed"
            report_required = expected["status"] == "answered" and expected["intent"] is not None
            relevant = [f"{VERSION}:{topic}:{language}" for topic in expected["relevant_topics"]]
            # Evaluate the retriever independently without using the answer's topic filter.
            independent = search(question, language=language) if relevant else []
            recall, reciprocal = retrieval_scores([c.chunk_id for c in independent], relevant)
            actual_recall, actual_reciprocal = retrieval_scores(
                [chunk["chunk_id"] for chunk in payload.get("methodology", [])], relevant
            )
            citation_valid = verify_methodology_citations(payload.get("methodology", []), language)
            success = (
                exact
                and (not report_required or verified is True)
                and citation_valid
                and not metadata.get("fallback_reason")
            )
            if relevant:
                success &= actual_recall == 1.0
            records.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "language": language,
                    "league": scenario["league"],
                    "category": scenario["category"],
                    "expected_status": expected["status"],
                    "actual_status": payload.get("status"),
                    "task_success": bool(success),
                    "plan_exact_match": bool(exact),
                    "all_claims_verified": verified,
                    "verification_error": verification_error,
                    "provider_success": metadata.get("provider_success") is True,
                    "fallback": bool(metadata.get("fallback_reason")),
                    "abstention": payload.get("status") == "abstained",
                    "clarification": payload.get("status") == "clarification_required",
                    "retrieval_recall_at_5": recall,
                    "retrieval_mrr_at_5": reciprocal,
                    "end_to_end_retrieval_recall_at_5": actual_recall,
                    "end_to_end_retrieval_mrr_at_5": actual_reciprocal,
                    "methodology_citations_valid": citation_valid,
                    "methodology_citations": len(payload.get("methodology", [])),
                    "metadata": metadata,
                    "request_sha256": digest(request),
                    "response_sha256": digest(payload),
                }
            )
    numeric = [row for row in records if row["all_claims_verified"] is not None]
    retrieval = [row for row in records if row["retrieval_recall_at_5"] is not None]
    latencies = [row["metadata"].get("latency_ms", 0) for row in records]
    supported = [row for row in records if row["expected_status"] == "answered"]
    ambiguous = [row for row in records if row["expected_status"] == "clarification_required"]
    unsupported = [row for row in records if row["expected_status"] == "abstained"]
    attempted = [row for row in records if row["metadata"].get("attempts", 0) > 0]
    usage_incomplete_cases = sum(
        row["metadata"].get("usage_complete") is False
        or (
            row["metadata"].get("attempts", 0) > 0
            and row["metadata"].get("usage_complete") is not True
        )
        for row in records
    )

    def rate(subset, field):
        return sum(row[field] for row in subset) / len(subset) if subset else None

    summary = {
        "semantic_scenarios": len(records) // 2,
        "language_variants": len(records),
        "task_successes": sum(row["task_success"] for row in records),
        "provider_successes": sum(row["provider_success"] for row in records),
        "provider_attempted_cases": sum(row["metadata"].get("attempts", 0) > 0 for row in records),
        "provider_success_rate_among_attempts": rate(attempted, "provider_success"),
        "repairs": sum(row["metadata"].get("repairs", 0) for row in records),
        "provider_errors": sum(row["metadata"].get("provider_errors", 0) for row in records),
        "fallbacks": sum(row["fallback"] for row in records),
        "abstentions": sum(row["abstention"] for row in records),
        "numeric_reports": len(numeric),
        "numeric_reports_verified": sum(row["all_claims_verified"] for row in numeric),
        "all_claims_verified_rate": rate(numeric, "all_claims_verified"),
        "supported_cases": len(supported),
        "supported_task_success_rate": rate(supported, "task_success"),
        "ambiguous_cases": len(ambiguous),
        "correct_clarification_rate": rate(ambiguous, "task_success"),
        "unsupported_cases": len(unsupported),
        "correct_unsupported_abstention_rate": rate(unsupported, "task_success"),
        "supported_abstention_rate": rate(supported, "abstention"),
        "fallback_rate_all_cases": rate(records, "fallback"),
        "methodology_citations": sum(row["methodology_citations"] for row in records),
        "reports_with_invalid_methodology_citations": sum(
            not row["methodology_citations_valid"] for row in records
        ),
        "independent_retrieval_cases": len(retrieval),
        "retrieval_recall_at_5": sum(row["retrieval_recall_at_5"] for row in retrieval)
        / len(retrieval)
        if retrieval
        else None,
        "retrieval_mrr_at_5": sum(row["retrieval_mrr_at_5"] for row in retrieval) / len(retrieval)
        if retrieval
        else None,
        "input_tokens": sum(row["metadata"].get("input_tokens", 0) for row in records),
        "output_tokens": sum(row["metadata"].get("output_tokens", 0) for row in records),
        "usage_incomplete_cases": usage_incomplete_cases,
        "usage_complete": usage_incomplete_cases == 0,
        "token_totals_status": "observed_lower_bound"
        if usage_incomplete_cases
        else "reported_usage_complete",
        "token_totals_note": "Only provider-reported input/output tokens are summed. "
        "If usage is incomplete, these sums are observed lower bounds; unreported failed "
        "or interrupted requests are not assumed to consume zero tokens.",
        "latency_p50_ms": percentile(latencies, 0.50),
        "latency_p95_ms": percentile(latencies, 0.95),
    }
    return {
        "version": protocol["version"],
        "phase": phase,
        "runner_kind": runner_kind,
        "partition": partition,
        "hashes": hashes,
        "summary": summary,
        "cases": records,
        "metrics_are_model_evidence": runner_kind == "live",
        "acceptance": {
            "status": "not_assessed_mock"
            if runner_kind == "mock"
            else "machine_metrics_only_human_output_review_pending",
            "proposed_targets": protocol["targets"],
        },
        "human_output_review": "pending",
        "limitations": "Mock smoke is an execution-contract check, not model accuracy. "
        "Translations share semantic scenarios. All-claim verification reconciles tool values; "
        "it does not establish independent human semantic quality. Retrieval is scored "
        "separately without the LLM topic filter. No final accuracy is claimed for draft smoke.",
    }


def visible_content(value):
    value = as_dict(value)
    report = value.get("report") if "report" in value else value
    return {
        "claims": (report or {}).get("claims", []),
        "qualifications": (report or {}).get("qualifications", []),
        "evidence": (report or {}).get("evidence"),
        "methodology": value.get("methodology", []),
    }


def prepare_blind_pairs(records, destination):
    """Export actual supplied outputs, never call a provider or invent report values.

    Input has one record per league/intent/language cell, with case_id, question,
    guided and query outputs. Keep private-key.json away from the reviewers.
    """
    expected_cells = {
        (league, intent, language)
        for league in ("wsl", "premier-league")
        for intent in ("period_comparison", "chance_creation", "network_concentration")
        for language in ("en", "fr")
    }
    cells = {(row["league"], row["intent"], row["language"]) for row in records}
    if (
        len(records) != 12
        or cells != expected_cells
        or len({row["case_id"] for row in records}) != 12
    ):
        raise ValueError(
            "Expected twelve actual paired outputs: two leagues × three intents × two languages"
        )
    pairs, key = [], []
    for row in sorted(records, key=lambda item: item["case_id"]):
        outputs = {name: visible_content(row[name]) for name in ("guided", "query")}
        if any(not output["claims"] for output in outputs.values()):
            raise ValueError("Blinded numerical pairs require actual claims from both outputs")
        pair_hash = digest(
            {"case_id": row["case_id"], "question": row["question"], "outputs": outputs}
        )
        order = ("guided", "query") if int(pair_hash[0], 16) % 2 == 0 else ("query", "guided")
        pair = {
            "pair_id": row["case_id"],
            "question": row["question"],
            "language": row["language"],
            "pair_sha256": pair_hash,
            **{
                label: {"content": outputs[name], "sha256": digest(outputs[name])}
                for label, name in zip(("A", "B"), order, strict=True)
            },
        }
        pairs.append(pair)
        key.append(
            {
                "pair_id": row["case_id"],
                "A": order[0],
                "B": order[1],
                "guided_full_sha256": digest(as_dict(row["guided"])),
                "query_full_sha256": digest(as_dict(row["query"])),
            }
        )
    destination = Path(destination)
    packet = {"version": "analyst-query-v2-blind-pilot", "pairs": pairs}
    packet_hash = digest(packet)
    paths = (
        destination / "blind-packet.json",
        destination / "ratings.json",
        destination / "private-key.json",
    )
    if paths[0].exists():
        if read_json(paths[0]) != packet:
            raise ValueError(
                "Paired outputs changed; preserve prior ratings and use a new destination"
            )
    else:
        create_json(paths[0], packet)
    if not paths[2].exists():
        create_json(paths[2], {"packet_sha256": packet_hash, "pairs": key})
    ratings = {
        "packet_sha256": packet_hash,
        "reviewer": "",
        "reviewed_at_iso": "",
        "independent_of_authors": None,
        "pairs": [
            {
                "pair_id": pair["pair_id"],
                "pair_sha256": pair["pair_sha256"],
                **{
                    label: {
                        "content_sha256": pair[label]["sha256"],
                        "factual_accuracy": None,
                        "source_support": None,
                        "limits_clear": None,
                        "usefulness": None,
                        "critical_error": None,
                        "notes": "",
                    }
                    for label in ("A", "B")
                },
                "preferred": None,
            }
            for pair in pairs
        ],
    }
    if paths[1].exists() and read_json(paths[1]).get("packet_sha256") != packet_hash:
        raise ValueError("Existing ratings refer to different paired content")
    if not paths[1].exists():
        create_json(paths[1], ratings)
    return paths


def validate_pair_ratings(packet_path, ratings_path):
    packet, ratings = read_json(packet_path), read_json(ratings_path)
    validate_identity(ratings, read_json(PROTOCOL)["authors"])
    if ratings.get("packet_sha256") != digest(packet):
        raise ValueError("Paired packet content changed")
    rows = ratings.get("pairs", [])
    if len(rows) != 12 or len({row["pair_id"] for row in rows}) != 12:
        raise ValueError("Exactly twelve complete paired ratings are required")
    by_id = {row["pair_id"]: row for row in rows}
    for pair in packet["pairs"]:
        rating = by_id.get(pair["pair_id"], {})
        if rating.get("pair_sha256") != pair["pair_sha256"] or rating.get("preferred") not in {
            "A",
            "B",
            "tie",
        }:
            raise ValueError("Missing pair decision or changed pair content")
        for label in ("A", "B"):
            scores = rating.get(label, {})
            if scores.get("content_sha256") != digest(pair[label]["content"]):
                raise ValueError("Rated output content changed")
            for dimension in ("factual_accuracy", "source_support", "limits_clear", "usefulness"):
                if type(scores.get(dimension)) is not int or scores[dimension] not in {0, 1, 2}:
                    raise ValueError("Every rating needs integer scores from zero to two")
            if type(scores.get("critical_error")) is not bool:
                raise ValueError("Critical-error judgment is required")
            if (
                scores["critical_error"]
                or any(
                    scores[d] < 2
                    for d in ("factual_accuracy", "source_support", "limits_clear", "usefulness")
                )
            ) and not scores.get("notes", "").strip():
                raise ValueError("Explain every concern or critical error")
    return {"reviewer": ratings["reviewer"], "pairs": 12, "ratings_sha256": digest(ratings)}


async def prepare_pairs_from_result(
    result_path, review_path, freeze_path, destination, *, guided_runner
):
    """Pair fixed final scenarios with actual outputs and recomputed guided reports.

    guided_runner(arguments, league, language) computes a deterministic report only.
    Selection uses scenario IDs before response quality; a missing/failed selected
    response stops export rather than being replaced with an easier case.
    """
    from tactigraph.analyst.contracts import AnalystReport
    from tactigraph.analyst.verification import verify_report

    lock = require_frozen(review_path, freeze_path)
    result = read_json(result_path)
    _, scenarios, hashes = load_package()
    if (
        result.get("phase") != "final"
        or result.get("runner_kind") != "live"
        or result.get("metrics_are_model_evidence") is not True
        or result.get("hashes") != hashes
        or result.get("source_manifests") != lock["candidate"].get("source_manifests")
    ):
        raise ValueError("A recorded live final result matching reviewed frozen inputs is required")
    cases = {(row["scenario_id"], row["language"]): row for row in result["cases"]}
    expected_case_keys = {
        (row["scenario_id"], language)
        for row in scenarios
        if row["partition"] == "final"
        for language in ("en", "fr")
    }
    if set(cases) != expected_case_keys or len(result["cases"]) != len(expected_case_keys):
        raise ValueError("A complete final run is required; do not select only successful cases")
    outputs = {}
    for output in result.get("outputs", []):
        key = (output["league"], digest(output["request"]))
        if key in outputs:
            raise ValueError("Duplicate execution output; preserve one exact result per request")
        outputs[key] = output
    selected = []
    for league in ("wsl", "premier-league"):
        for intent in ("period_comparison", "chance_creation", "network_concentration"):
            candidates = [
                row
                for row in scenarios
                if row["partition"] == "final"
                and row["category"] == "analytic"
                and row["league"] == league
                and row["expected"]["intent"] == intent
            ]
            if not candidates:
                raise ValueError("A required paired-review scenario cell is missing")
            scenario = min(
                candidates,
                key=lambda row: digest(
                    {"protocol": "query-v2-blind-pilot", "scenario_id": row["scenario_id"]}
                ),
            )
            for language in ("en", "fr"):
                selected.append((scenario, language))
    records = []
    for scenario, language in selected:
        case = cases.get((scenario["scenario_id"], language))
        if case is None:
            raise ValueError("Selected case has no recorded final result; do not substitute a case")
        output = outputs.get((scenario["league"], case["request_sha256"]))
        if output is None or digest(output["response"]) != case["response_sha256"]:
            raise ValueError("Selected original query output is missing or changed")
        query = output["response"]
        if query.get("status") != "answered" or not query.get("report"):
            raise ValueError("Selected query failed; record the failure instead of replacing it")
        context = lock["candidate"]["source_manifests"][f"final:{scenario['league']}"]
        request = output["request"]
        if (
            request.get("question") != scenario["questions"][language]
            or request.get("language") != language
            or any(request.get(field) != context[field] for field in ("match_id", "team_id"))
        ):
            raise ValueError("Query request differs from the frozen selected context")
        report = AnalystReport.model_validate(query["report"])
        expected = scenario["expected"]
        if (
            report.arguments.intent != expected["intent"]
            or report.arguments.before.model_dump() != expected["before"]
            or report.arguments.after.model_dump() != expected["after"]
        ):
            raise ValueError(
                "Selected query used different windows or intent; preserve this failure"
            )
        guided = guided_runner(report.arguments.model_dump(), scenario["league"], language)
        if inspect.isawaitable(guided):
            guided = await guided
        if not isinstance(guided, AnalystReport):
            raise ValueError("Guided runner must return a live report with event support")
        if guided.evidence.result_id != report.evidence.result_id:
            raise ValueError("Guided/query evidence differs under the frozen context")
        # Public report serialization omits supporting_event_ids. Reconstruct them
        # from the deterministic execution only after checking exact result identity.
        report.evidence.supporting_event_ids = guided.evidence.supporting_event_ids
        verify_report(report)
        verify_report(guided)
        records.append(
            {
                "case_id": f"{scenario['scenario_id']}:{language}",
                "league": scenario["league"],
                "intent": expected["intent"],
                "language": language,
                "question": scenario["questions"][language],
                "guided": guided,
                "query": query,
            }
        )
    return prepare_blind_pairs(records, destination)
