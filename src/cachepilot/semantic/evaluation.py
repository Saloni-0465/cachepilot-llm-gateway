"""Embedding-based scoring and threshold metrics for semantic cache pairs."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


@dataclass(frozen=True)
class PromptPair:
    pair_id: str
    split: str
    prompt_a: str
    prompt_b: str
    safe_to_reuse: bool
    rationale: str


@dataclass(frozen=True)
class ScoredPair:
    pair: PromptPair
    similarity: float


def load_pairs(path: Path) -> list[PromptPair]:
    import json

    pairs: list[PromptPair] = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                pair = PromptPair(**json.loads(line))
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError(f"Invalid pair at {path}:{line_number}: {exc}") from exc
            if pair.split not in {"development", "holdout"}:
                raise ValueError(
                    f"Pair {pair.pair_id!r} has unsupported split {pair.split!r}"
                )
            pairs.append(pair)

    if not pairs:
        raise ValueError(f"No prompt pairs found in {path}")
    if len({pair.pair_id for pair in pairs}) != len(pairs):
        raise ValueError("Prompt pair IDs must be unique")
    return pairs


def score_pairs(
    pairs: list[PromptPair],
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> list[ScoredPair]:
    """Embed both prompt texts and calculate cosine similarity per pair."""
    model = SentenceTransformer(model_name)
    texts = [text for pair in pairs for text in (pair.prompt_a, pair.prompt_b)]
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    )
    return [
        ScoredPair(
            pair=pair,
            similarity=float(np.dot(vectors[2 * index], vectors[2 * index + 1])),
        )
        for index, pair in enumerate(pairs)
    ]


def threshold_metrics(
    scored_pairs: list[ScoredPair],
    threshold: float,
    split: str,
) -> dict[str, float | int | str]:
    rows = [item for item in scored_pairs if item.pair.split == split]
    safe_total = sum(item.pair.safe_to_reuse for item in rows)
    unsafe_total = len(rows) - safe_total
    hits = [item for item in rows if item.similarity >= threshold]
    safe_hits = sum(item.pair.safe_to_reuse for item in hits)
    unsafe_hits = len(hits) - safe_hits

    return {
        "split": split,
        "threshold": threshold,
        "safe_pairs": safe_total,
        "unsafe_pairs": unsafe_total,
        "predicted_hits": len(hits),
        "safe_hits": safe_hits,
        "unsafe_hits": unsafe_hits,
        "safe_hit_precision": safe_hits / len(hits) if hits else 0.0,
        "safe_pair_recall": safe_hits / safe_total if safe_total else 0.0,
        "unsafe_hit_rate": unsafe_hits / unsafe_total if unsafe_total else 0.0,
    }
