import argparse
import json
from pathlib import Path

from tactigraph.config import Settings


def main():
    parser = argparse.ArgumentParser(description="TactiGraph reproducible local workbench")
    parser.add_argument("--league", choices=["wsl", "premier-league"], default="wsl")
    sub = parser.add_subparsers(dest="command", required=True)
    transfer_parser = sub.add_parser(
        "transfer-showcase", help="Copy selected data to an EMPTY configured database"
    )
    transfer_parser.add_argument("--source", required=True)
    showcase = sub.add_parser(
        "showcase", help="Prepare, export or record independent showcase review"
    )
    showcase.add_argument("stage", choices=["prepare", "export", "approve"])
    showcase.add_argument("--output", type=Path, default=Path("output/release-review"))
    showcase.add_argument("--review", type=Path)
    sub.add_parser(
        "develop-styles", help="Fit training-only PCA/K-means and publish style profiles"
    )
    sub.add_parser(
        "publish-analyst", help="Publish completed analyst and retrieval evaluation summaries"
    )
    sub.add_parser("evaluate-retrieval", help="Compare frozen BM25, MiniLM and hybrid retrieval")
    analyst = sub.add_parser(
        "evaluate-analyst", help="Evaluate the frozen match-disjoint tactical cases"
    )
    analyst.add_argument(
        "--local", action="store_true", help="Also benchmark pinned local Qwen3 selection"
    )
    analyst.add_argument("--groq", action="store_true", help="Benchmark configured Groq selection")
    ingest = sub.add_parser("ingest", help="Ingest the selected pinned league; resume-safe")
    ingest.add_argument("--scope", choices=["first", "wsl", "all"], default="first")
    ingest.add_argument("--force", action="store_true", help="Rebuild normalized matches")
    ingest.add_argument("--split-manifest", type=Path, default=Path("configs/splits/wsl-v1.json"))
    sub.add_parser("migrate", help="Upgrade the schema; safely adopt existing M1 databases")
    fetch = sub.add_parser("fetch", help="Download/check the selected league's pinned source files")
    fetch.add_argument("--workers", type=int, default=4)
    sub.add_parser("audit", help="Generate coverage, integrity and training-only EDA report")
    xg = sub.add_parser("xg", help="Offline xG experiment with a locked final-test gate")
    xg.add_argument("stage", choices=["develop", "evaluate", "publish"])
    xg.add_argument("--protocol", type=Path, default=Path("configs/xg-v1.json"))
    xt = sub.add_parser("xt", help="Offline turnover-aware xT experiment")
    xt.add_argument("stage", choices=["develop", "evaluate", "publish"])
    xt.add_argument("--protocol", type=Path, default=Path("configs/xt-v1.json"))
    graph = sub.add_parser("graph", help="Offline third-pass graph experiment")
    graph.add_argument("stage", choices=["dataset", "develop", "evaluate", "publish"])
    graph.add_argument("--protocol", type=Path, default=Path("configs/graph-v1.json"))
    server = sub.add_parser("serve", help="Serve API and built frontend")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8000)
    schema = sub.add_parser("openapi", help="Export schema for frontend type generation")
    schema.add_argument("--output", default="frontend/openapi.json")
    args = parser.parse_args()
    settings = Settings().for_league(args.league)
    if args.league == "premier-league":
        if args.command not in {
            "fetch",
            "ingest",
            "audit",
            "migrate",
            "xg",
            "xt",
            "graph",
            "develop-styles",
        }:
            parser.error(
                "This command has no Premier League workflow. "
                "Use ordinary 'serve' for both leagues. "
                "WSL analyst benchmarks and curated showcase cannot be copied to Premier League."
            )
        if args.command == "ingest":
            args.scope = "all"
            if args.split_manifest == Path("configs/splits/wsl-v1.json"):
                args.split_manifest = Path("configs/splits/premier-league-v1.json")
        if args.command in {"xg", "xt", "graph"}:
            if args.protocol == Path(f"configs/{args.command}-v1.json"):
                args.protocol = Path(f"configs/{args.command}-premier-league-v1.json")
    if args.command == "transfer-showcase":
        from tactigraph.transfer import transfer

        print(json.dumps(transfer(args.source, settings), indent=2))
        return
    if args.command == "showcase":
        from tactigraph.db import DatasetReport, initialize, make_engine
        from tactigraph.release import VERSION, approve, export_review, prepare

        engine = make_engine(settings)
        try:
            with initialize(engine).begin() as session:
                if args.stage == "prepare":
                    result = prepare(session, args.output)
                elif args.stage == "approve":
                    if args.review is None:
                        parser.error("--review is required")
                    result = approve(session, args.review)
                else:
                    row = session.get(DatasetReport, VERSION)
                    if row is None:
                        raise ValueError("Prepare the showcase first")
                    export_review(row.payload, args.output)
                    result = {"exported": str(args.output)}
            print(json.dumps(result, indent=2))
        finally:
            engine.dispose()
        return
    if args.command == "develop-styles":
        from tactigraph.models.styles import develop

        report = develop(
            settings,
            Path(
                "configs/styles-premier-league-v1.json"
                if args.league == "premier-league"
                else "configs/styles-v1.json"
            ),
        )
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in (
                        "version",
                        "training_windows",
                        "training_silhouette",
                        "seed_ari",
                        "match_bootstrap_ari",
                    )
                },
                indent=2,
            )
        )
        return
    if args.command == "publish-analyst":
        from tactigraph.analyst.publish import publish

        print(json.dumps(publish(settings), indent=2))
        return
    if args.command == "evaluate-analyst":
        from tactigraph.analyst.evaluation import evaluate

        print(json.dumps(evaluate(settings, local=args.local, groq=args.groq)["summary"], indent=2))
        return
    if args.command == "evaluate-retrieval":
        from tactigraph.retrieval.experiment import evaluate

        report = evaluate()
        print(
            json.dumps(
                {key: report[key] for key in ("version", "selected", "acceptance_targets_met")},
                indent=2,
            )
        )
        return
    if args.command == "graph":
        if args.stage in {"dataset", "develop"}:
            from tactigraph.models.graph_experiment import stage
        else:
            from tactigraph.models.graph_evaluation import stage

        print(json.dumps(stage(settings, args.protocol, args.stage), indent=2))
        return
    if args.command == "xt":
        from tactigraph.models.xt_experiment import stage

        print(json.dumps(stage(settings, args.protocol, args.stage), indent=2))
        return
    if args.command == "xg":
        if args.stage == "develop":
            from tactigraph.models.experiment import develop

            result = develop(settings, args.protocol)
        elif args.stage == "evaluate":
            from tactigraph.models.evaluation import evaluate

            report = evaluate(settings, args.protocol)
            result = {
                k: report[k] for k in ("version", "status", "serving", "test_non_penalty_shots")
            }
        else:
            from tactigraph.models.publish import publish

            result = publish(settings, args.protocol)
        print(json.dumps(result, indent=2))
        return
    if args.command == "fetch":
        from tactigraph.data.catalog import fetch_scope

        result = fetch_scope(settings, args.workers)
        print(json.dumps(result, indent=2))
        raise SystemExit(bool(result["failures"]))
    if args.command in {"ingest", "migrate", "audit"}:
        from tactigraph.data.ingest import ingest_first_match
        from tactigraph.db import initialize, make_engine

        engine = make_engine(settings)
        try:
            sessions = initialize(engine)
            if args.command == "migrate":
                result = {"schema_revision": "0003"}
            elif args.command == "audit":
                from tactigraph.data.audit import audit_dataset

                report = audit_dataset(settings, sessions)
                result = {k: report[k] for k in ("coverage_complete", "counts", "integrity_checks")}
            elif args.scope in {"wsl", "all"}:
                from tactigraph.data.pipeline import ingest_scope

                result = ingest_scope(
                    settings, sessions, force=args.force, split_path=args.split_manifest
                )
            else:
                result = ingest_first_match(settings, sessions)
            print(json.dumps(result, indent=2))
            if result.get("failures") or result.get("coverage_complete") is False:
                raise SystemExit(1)
        finally:
            engine.dispose()
    elif args.command == "openapi":
        from tactigraph.api.app import create_app

        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(create_app(settings).openapi(), indent=2), encoding="utf-8")
    elif args.command == "serve":
        import uvicorn

        from tactigraph.api.app import create_app

        uvicorn.run(create_app(settings), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
