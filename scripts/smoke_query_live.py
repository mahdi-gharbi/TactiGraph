"""Two integration calls, outside the benchmark; no accuracy/generalization score."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx

from tactigraph.analyst.query import run_query
from tactigraph.analyst.verification import verify_report
from tactigraph.config import Settings
from tactigraph.db import initialize, make_engine


class DiagnosticsTransport(httpx.AsyncBaseTransport):
    def __init__(self, key):
        self.key = key
        self.transport = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request):
        response = await self.transport.handle_async_request(request)
        if response.status_code >= 400:
            await response.aread()
            error = response.json().get("error", {})
            print(
                json.dumps(
                    {
                        "http_status": response.status_code,
                        "type": error.get("type"),
                        "code": error.get("code"),
                        "message": str(error.get("message", "")).replace(self.key, "[redacted]")[
                            :700
                        ],
                    }
                )
            )
        return response

    async def aclose(self):
        await self.transport.aclose()


async def smoke(sessions, settings, match_id, team_id, diagnose=False):
    cases = []
    for language, question in (
        (
            "fr",
            "Compare la création d’occasions entre les minutes 45–60 et 60–75, et explique le xG.",
        ),
        ("en", "Compare chance creation between minutes 45–60 and 60–75, and explain xG."),
    ):
        transport = (
            DiagnosticsTransport(settings.groq_api_key.get_secret_value()) if diagnose else None
        )
        response = await run_query(
            sessions,
            {
                "question": question,
                "language": language,
                "match_id": match_id,
                "team_id": team_id,
            },
            settings,
            transport=transport,
        )
        verified = None
        if response.report:
            with sessions() as session:
                verified = verify_report(response.report, session=session)
        contract_valid = (
            response.status == "answered"
            and response.plan is not None
            and response.plan.intent == "chance_creation"
            and response.plan.before.period == 2
            and response.plan.before.start_ms == 0
            and response.plan.before.end_ms == 900000
            and response.plan.after.start_ms == 900000
            and response.plan.after.end_ms == 1800000
            and response.plan.methodology_topics == ["xg"]
            and all(
                c.language == language and c.version == "methodology-v2"
                for c in response.methodology
            )
        )
        cases.append(
            {
                "language": language,
                "contract_valid": contract_valid,
                "verification": verified,
                "response": response.model_dump(mode="json"),
            }
        )
    return {
        "scope": "Live bilingual integration smoke on two user-example questions; "
        "not a benchmark or an independent quality evaluation.",
        "league": settings.league,
        "cases": cases,
        "monetary_cost": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", choices=("wsl", "premier-league"), default="wsl")
    parser.add_argument("--match", type=int, required=True)
    parser.add_argument("--team", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--diagnose", action="store_true")
    args = parser.parse_args()
    settings = Settings().for_league(args.league)
    engine = make_engine(settings)
    try:
        report = asyncio.run(
            smoke(initialize(engine), settings, args.match, args.team, args.diagnose)
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, ensure_ascii=False)
        print(
            json.dumps(
                [
                    {
                        "language": case["language"],
                        "status": case["response"]["status"],
                        "metadata": case["response"]["metadata"],
                        "verification": case["verification"],
                    }
                    for case in report["cases"]
                ],
                indent=2,
            )
        )
        if any(not c["contract_valid"] for c in report["cases"]):
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
