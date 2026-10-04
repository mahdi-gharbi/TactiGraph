"""Blind twelve existing guided/query output pairs; never generates or scores answers."""

import argparse
from pathlib import Path

from tactigraph.analyst.query_evaluation import prepare_blind_pairs, read_json

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="JSON list of twelve actual guided/query output pairs",
    )
    parser.add_argument("--output", type=Path, default=Path("output/query-v2/blind-review"))
    args = parser.parse_args()
    packet, ratings, private_key = prepare_blind_pairs(read_json(args.source), args.output)
    print(f"Reviewer packet: {packet}\nUnscored ratings: {ratings}")
    print(f"Keep this mapping away from reviewers: {private_key}")
