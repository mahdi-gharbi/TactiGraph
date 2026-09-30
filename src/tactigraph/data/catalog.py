"""Pinned WSL inventory and bounded, resumable downloads (no database mutation)."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

from tactigraph.config import SOURCE_COMMIT, Settings
from tactigraph.data.ingest import acquire

SEASONS = {4: 107, 42: 87, 90: 131, 281: 132}


def catalog(settings: Settings):
    matches, manifests = [], []
    with httpx.Client(
        timeout=90, follow_redirects=True, transport=httpx.HTTPTransport(retries=3)
    ) as client:
        competition = 2 if settings.league == "premier-league" else 37
        seasons = {27: 380} if competition == 2 else SEASONS
        for season, expected in seasons.items():
            rows, manifest = acquire(f"data/matches/{competition}/{season}.json", settings, client)
            if len(rows) != expected or any(
                m["competition"]["competition_id"] != competition
                or m["season"]["season_id"] != season
                for m in rows
            ):
                raise ValueError(f"Pinned catalog scope mismatch for season {season}")
            manifest["schema_version"] = "matches-v3"
            matches.extend(rows)
            manifests.append(manifest)
    if len({m["match_id"] for m in matches}) != len(matches):
        raise ValueError("Duplicate match in catalog")
    return sorted(matches, key=lambda m: (m["match_date"], m["match_id"])), manifests


def fetch_scope(settings: Settings, workers: int = 4):
    if not 1 <= workers <= 8:
        raise ValueError("Use 1–8 download workers")
    matches, _ = catalog(settings)

    def fetch_match(match):
        mid = match["match_id"]
        with httpx.Client(
            timeout=90, follow_redirects=True, transport=httpx.HTTPTransport(retries=3)
        ) as client:
            for kind in ("events", "lineups"):
                acquire(f"data/{kind}/{mid}.json", settings, client)
        return mid

    failures = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        tasks = {executor.submit(fetch_match, m): m["match_id"] for m in matches}
        for count, task in enumerate(as_completed(tasks), 1):
            try:
                task.result()
            except (httpx.HTTPError, ValueError, OSError) as exc:
                failures.append({"match_id": tasks[task], "error": str(exc)})
            if count % 20 == 0 or count == len(matches):
                print(
                    f"Downloaded/verified {count}/{len(matches)} matches; {len(failures)} failures",
                    flush=True,
                )
    report = {
        "source_commit": SOURCE_COMMIT,
        "expected": len(matches),
        "verified": len(matches) - len(failures),
        "failures": failures,
    }
    path = settings.data_dir / "reports" / "download.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = fetch_scope(Settings())
    print(json.dumps(result, indent=2))
    raise SystemExit(bool(result["failures"]))
