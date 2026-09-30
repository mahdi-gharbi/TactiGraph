"""Reproduce the isolated Premier League workspace; stop on any failed stage."""

import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    steps = [["fetch", "--workers", "6"], ["ingest"], ["audit"]]
    for model in ("xg", "xt", "graph"):
        steps.extend([[model, stage] for stage in ("develop", "evaluate", "publish")])
    steps.append(["develop-styles"])
    for step in steps:
        print(f"\nPremier League: {' '.join(step)}", flush=True)
        subprocess.run(
            [sys.executable, "-u", "-m", "tactigraph.cli", "--league", "premier-league", *step],
            cwd=root,
            check=True,
        )
    print("Premier League import, audit and model publication complete.", flush=True)


if __name__ == "__main__":
    main()
