"""Create an unscored, stratified review worksheet from the frozen WSL showcase."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

INTENTS = ("period_comparison", "chance_creation", "network_concentration")
FIELDNAMES = (
    "report_id",
    "sha256",
    "season_id",
    "match_id",
    "fixture",
    "intent",
    "question",
    "claims_to_check",
    "pinned_source_url",
    "reviewer",
    "reviewed_at_iso",
    "factual_accuracy_0_2",
    "source_support_0_2",
    "limits_clear_0_2",
    "usefulness_0_2",
    "critical_error_yes_no",
    "notes",
)
QUESTIONS = {
    "period_comparison": "Did final-third progression change between minutes 45–60 and 60–75?",
    "chance_creation": "Did shot creation change between minutes 45–60 and 60–75?",
    "network_concentration": "Did outgoing passing become more concentrated?",
}


def prepare(source: Path, destination: Path) -> list[dict]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("version") != "showcase-v1" or len(payload.get("reports", [])) != 36:
        raise ValueError("Expected the frozen 36-report WSL showcase-v1 packet")
    matches = {match["match_id"]: match for match in payload["matches"]}
    groups: dict[tuple[int, str], list[dict]] = {}
    for entry in payload["reports"]:
        report = entry["report"]
        match_id = report["arguments"]["match_id"]
        match = matches[match_id]
        intent = report["arguments"]["intent"]
        actual_hash = hashlib.sha256(
            json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if intent not in INTENTS or entry["sha256"] != actual_hash:
            raise ValueError("Unexpected report intent or changed fingerprint")
        groups.setdefault((match["season_id"], intent), []).append(entry)
    if len(groups) != 12:
        raise ValueError("Expected four seasons by three guided intents")

    # Selection does not inspect report numbers, wording, or match outcomes.
    selected = []
    for (season_id, intent), entries in sorted(groups.items()):
        chosen = min(
            entries,
            key=lambda entry: hashlib.sha256(
                f"human-eval-v1:{season_id}:{intent}:"
                f"{entry['report']['arguments']['match_id']}".encode()
            ).hexdigest(),
        )
        report = chosen["report"]
        match_id = report["arguments"]["match_id"]
        match = matches[match_id]
        selected.append(
            {
                "report_id": report["report_id"],
                "sha256": chosen["sha256"],
                "season_id": season_id,
                "match_id": match_id,
                "fixture": f"{match['home']} – {match['away']}",
                "intent": intent,
                "question": QUESTIONS[intent],
                "claims_to_check": " | ".join(claim["text"] for claim in report["claims"]),
                "pinned_source_url": (
                    "https://github.com/hudl/open-data/blob/"
                    f"{report['evidence']['source_commit']}/data/events/{match_id}.json"
                ),
                **{name: "" for name in FIELDNAMES[9:]},
            }
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        with destination.open(encoding="utf-8-sig", newline="") as stream:
            existing = list(csv.DictReader(stream))
        if [(r["report_id"], r["sha256"]) for r in existing] != [
            (r["report_id"], r["sha256"]) for r in selected
        ]:
            raise ValueError("Existing ratings refer to different reports; use a new destination")
        return selected
    with destination.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(selected)
    return selected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("output/release-review/reports.json"))
    parser.add_argument("--output", type=Path, default=Path("output/human-evaluation/ratings.csv"))
    args = parser.parse_args()
    rows = prepare(args.source, args.output)
    print(f"Prepared {len(rows)} unscored reports at {args.output}")
