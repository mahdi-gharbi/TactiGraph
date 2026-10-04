"""Prepare review now; run frozen, real-provider evaluation after independent approval."""

import argparse
import asyncio
from pathlib import Path

from tactigraph.analyst.contracts import AnalystRequest
from tactigraph.analyst.query import compute, run_query
from tactigraph.analyst.query_evaluation import (
    create_json,
    digest,
    evaluate,
    freeze,
    prepare_blind_pairs,
    prepare_pairs_from_result,
    prepare_review,
    read_json,
    require_frozen,
    validate_pair_ratings,
    validate_review,
)
from tactigraph.analyst.rendering import translate_report
from tactigraph.analyst.verification import verify_report
from tactigraph.analyst.workflow import run as guided_workflow
from tactigraph.config import Settings
from tactigraph.db import Match, SourceManifest, initialize, make_engine


def contexts(path):
    payload = read_json(path)
    for partition in ("development", "final"):
        for league in ("wsl", "premier-league"):
            cell = payload[partition][league]
            if set(cell) != {"match_id", "team_id"} or any(
                type(v) is not int or v <= 0 for v in cell.values()
            ):
                raise ValueError("Each context needs positive integer match_id and team_id")
    for league in ("wsl", "premier-league"):
        if payload["development"][league]["match_id"] == payload["final"][league]["match_id"]:
            raise ValueError("Use separate development and final matches")
    return payload


def context_sources(payload, sessions):
    sources = {}
    for partition, leagues in payload.items():
        for league, cell in leagues.items():
            with sessions[league]() as session:
                match = session.get(Match, cell["match_id"])
                source = session.get(SourceManifest, f"data/events/{cell['match_id']}.json")
                if match is None or cell["team_id"] not in {match.home_id, match.away_id}:
                    raise ValueError("Selected context is not available in its league")
                if source is None or source.validation_status != "valid":
                    raise ValueError("A verified source manifest is required")
                sources[f"{partition}:{league}"] = {
                    **cell,
                    "commit": source.commit,
                    "sha256": source.sha256,
                    "fixture": f"{match.home_name} – {match.away_name}",
                }
    return sources


async def run_evaluation(args, selected, settings, sessions, lock):
    partition = "final" if args.phase == "final" else "development"
    if any(config.groq_model != lock["candidate"]["model"] for config in settings.values()):
        raise ValueError("Configured provider model differs from the frozen candidate")
    if lock["candidate"].get("contexts_sha256") != digest(selected):
        raise ValueError("Contexts differ from the frozen candidate")
    sources = context_sources(selected, sessions)
    if sources != lock["candidate"].get("source_manifests"):
        raise ValueError("Context source manifests changed since freezing")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ValueError("Preserve existing results; choose a new result path")
    if args.phase == "final":
        # A failed or interrupted final run still counts as inspection.
        create_json(
            args.freeze.with_suffix(".final-access.json"),
            {
                "freeze_sha256": digest(lock),
                "purpose": "one final evaluation",
            },
        )
    outputs = []

    async def runner(request, league):
        response = await run_query(sessions[league], request, settings[league])
        outputs.append(
            {"league": league, "request": request, "response": response.model_dump(mode="json")}
        )
        return response

    def verify(report):
        # Reconcile against a fresh execution, including provenance and support IDs.
        league = next(
            candidate_league
            for candidate_league in sessions
            if selected[partition][candidate_league]["match_id"] == report.arguments.match_id
        )
        with sessions[league]() as session:
            verdict = verify_report(report, session=session)
        recomputed = compute(sessions[league], report.arguments, "en")
        if recomputed.evidence.result_id != report.evidence.result_id:
            raise ValueError("Tool results changed")
        return verdict

    report = await evaluate(
        runner,
        context_resolver=lambda s: selected[partition][s["league"]],
        phase=args.phase,
        runner_kind="live",
        verify_all_claims=verify,
        review_path=args.review,
        freeze_path=args.freeze,
    )
    report.update(
        {
            "source_manifests": sources,
            "outputs": outputs,
            "monetary_cost": None,
            "pricing_status": "not_calculated",
        }
    )
    create_json(args.output, report)
    return report["summary"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare-review")
    prepare.add_argument("--output", type=Path, default=Path("output/query-review-v2"))
    freeze_parser = sub.add_parser("freeze")
    freeze_parser.add_argument("--contexts", type=Path, required=True)
    freeze_parser.add_argument("--review", type=Path, required=True)
    freeze_parser.add_argument("--output", type=Path, required=True)
    bench = sub.add_parser("evaluate")
    bench.add_argument("--contexts", type=Path, required=True)
    bench.add_argument("--review", type=Path, required=True)
    bench.add_argument("--freeze", type=Path, required=True)
    bench.add_argument("--phase", choices=("development", "final"), required=True)
    bench.add_argument("--output", type=Path, required=True)
    pairs = sub.add_parser("blind-pairs")
    pairs.add_argument("--records", type=Path, required=True)
    pairs.add_argument("--output", type=Path, required=True)
    generate = sub.add_parser("generate-pairs")
    generate.add_argument("--result", type=Path, required=True)
    generate.add_argument("--contexts", type=Path, required=True)
    generate.add_argument("--review", type=Path, required=True)
    generate.add_argument("--freeze", type=Path, required=True)
    generate.add_argument("--output", type=Path, required=True)
    ratings = sub.add_parser("validate-pairs")
    ratings.add_argument("--packet", type=Path, required=True)
    ratings.add_argument("--ratings", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare-review":
        print([str(p) for p in prepare_review(args.output)])
        return
    if args.command == "blind-pairs":
        print([str(p) for p in prepare_blind_pairs(read_json(args.records), args.output)])
        return
    if args.command == "validate-pairs":
        print(validate_pair_ratings(args.packet, args.ratings))
        return
    # Gate before constructing engines or contacting any provider.
    lock = None
    if args.command in {"evaluate", "generate-pairs"}:
        lock = require_frozen(args.review, args.freeze)
    elif args.command == "freeze":
        validate_review(args.review)
    selected = contexts(args.contexts)
    base = Settings()
    settings = {league: base.for_league(league) for league in ("wsl", "premier-league")}
    engines = {league: make_engine(config) for league, config in settings.items()}
    try:
        sessions = {league: initialize(engine) for league, engine in engines.items()}
        if args.command == "freeze":
            print(
                freeze(
                    args.review,
                    args.output,
                    candidate={
                        "provider": "groq",
                        "model": base.groq_model,
                        "contexts_sha256": digest(selected),
                        "source_manifests": context_sources(selected, sessions),
                    },
                )
            )
        elif args.command == "generate-pairs":
            if lock["candidate"].get("contexts_sha256") != digest(selected) or context_sources(
                selected, sessions
            ) != lock["candidate"].get("source_manifests"):
                raise ValueError("Contexts or sources differ from the frozen paired-review input")

            def guided_runner(arguments, league, language):
                with sessions[league]() as session:
                    report = guided_workflow(session, AnalystRequest.model_validate(arguments))
                    report = translate_report(report, language)
                    verify_report(report, session=session)
                    return report

            exported = asyncio.run(
                prepare_pairs_from_result(
                    args.result, args.review, args.freeze, args.output, guided_runner=guided_runner
                )
            )
            print([str(path) for path in exported])
        else:
            print(asyncio.run(run_evaluation(args, selected, settings, sessions, lock)))
    finally:
        for engine in engines.values():
            engine.dispose()


if __name__ == "__main__":
    main()
