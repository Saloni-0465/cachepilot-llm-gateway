#!/usr/bin/env python3
"""Evaluate semantic-cache similarity thresholds on labeled prompt pairs."""

import argparse
from pathlib import Path

from cachepilot.semantic.evaluation import load_pairs, score_pairs, threshold_metrics


def print_metrics(rows: list[dict[str, float | int | str]]) -> None:
    print(
        f"{'split':<12} {'threshold':>9} {'safe hits':>10} "
        f"{'unsafe hits':>12} {'safe precision':>15} {'safe recall':>12} "
        f"{'unsafe hit rate':>16}"
    )
    for row in rows:
        print(
            f"{row['split']:<12} {row['threshold']:>9.2f} "
            f"{row['safe_hits']:>10} {row['unsafe_hits']:>12} "
            f"{row['safe_hit_precision']:>14.1%} "
            f"{row['safe_pair_recall']:>11.1%} "
            f"{row['unsafe_hit_rate']:>15.1%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/semantic_cache_pairs.jsonl"),
    )
    parser.add_argument(
        "--model",
        default="sentence-transformers/all-MiniLM-L6-v2",
        help="Sentence Transformers model used to embed each prompt.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        help="Evaluate one selected threshold on both development and holdout sets.",
    )
    parser.add_argument(
        "--show-pairs",
        action="store_true",
        help="Print individual pair scores after aggregate metrics.",
    )
    args = parser.parse_args()

    if args.threshold is not None and not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between 0 and 1")

    pairs = load_pairs(args.dataset)
    scored = score_pairs(pairs, model_name=args.model)

    if args.threshold is None:
        thresholds = [round(value / 100, 2) for value in range(50, 100, 5)]
        rows = [
            threshold_metrics(scored, threshold, "development")
            for threshold in thresholds
        ]
        print("Threshold sweep on development pairs. Choose a threshold here.")
    else:
        rows = [
            threshold_metrics(scored, args.threshold, split)
            for split in ("development", "holdout")
        ]
        print("Selected-threshold report. Treat holdout results as final evaluation.")

    print_metrics(rows)

    if args.show_pairs:
        print("\nPair scores (higher means more semantically similar):")
        print(f"{'id':<24} {'split':<12} {'label':<8} {'similarity':>10}  rationale")
        for item in scored:
            label = "safe" if item.pair.safe_to_reuse else "unsafe"
            print(
                f"{item.pair.pair_id:<24} {item.pair.split:<12} "
                f"{label:<8} {item.similarity:>10.3f}  {item.pair.rationale}"
            )


if __name__ == "__main__":
    main()
