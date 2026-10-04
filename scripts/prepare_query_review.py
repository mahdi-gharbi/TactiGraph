"""Export the unscored bilingual query-v2 protocol/scenario review packet."""

import argparse
from pathlib import Path

from tactigraph.analyst.query_evaluation import prepare_review

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/query-v2/schema-review-r2"))
    args = parser.parse_args()
    packet, ratings = prepare_review(args.output)
    print(f"Review packet: {packet}\nUnscored ratings: {ratings}")
    print("No approval, freeze, provider benchmark or final evaluation was performed.")
