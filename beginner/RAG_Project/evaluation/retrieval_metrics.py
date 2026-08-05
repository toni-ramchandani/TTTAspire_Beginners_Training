"""Deterministic information-retrieval metrics over stable chunk IDs."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence


RETRIEVAL_RATE_METRICS = (
    "precision_at_k",
    "recall_at_k",
    "f1_at_k",
    "hit_at_k",
    "reciprocal_rank_at_k",
    "average_precision_at_k",
    "ndcg_at_k",
    "required_context_recall_at_k",
    "all_required_contexts_at_k",
)


def _safe_f1(precision: float, recall: float) -> float:
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def _dcg(grades: Sequence[int]) -> float:
    return sum(
        (2**grade - 1) / math.log2(rank + 1)
        for rank, grade in enumerate(grades, start=1)
        if grade > 0
    )


def compute_retrieval_metrics(
    retrieved_ids: Sequence[str],
    context_relevance: Mapping[str, int],
    required_context_ids: Sequence[str],
) -> dict[str, float | int]:
    """Calculate binary and graded ranking metrics for the observed top-k list.

    The trace contains only the retrieved top-k list, so reciprocal rank and average
    precision are explicitly truncated at k. Average precision uses the total number
    of judged-relevant contexts as its denominator; missing relevant contexts remain
    visible rather than being excused when k is small.
    """

    k = len(retrieved_ids)
    if k < 1:
        raise ValueError("At least one retrieved ID is required.")
    if len(retrieved_ids) != len(set(retrieved_ids)):
        raise ValueError("Retrieved IDs must be unique.")

    relevant_ids = {chunk_id for chunk_id, grade in context_relevance.items() if grade > 0}
    if not relevant_ids:
        raise ValueError("At least one context must have a positive relevance grade.")
    required_ids = set(required_context_ids)
    if not required_ids:
        raise ValueError("At least one required context ID is needed.")

    relevance_flags = [1 if chunk_id in relevant_ids else 0 for chunk_id in retrieved_ids]
    relevant_retrieved = sum(relevance_flags)
    precision = relevant_retrieved / k
    recall = relevant_retrieved / len(relevant_ids)

    first_relevant_rank = next(
        (rank for rank, flag in enumerate(relevance_flags, start=1) if flag), None
    )
    reciprocal_rank = 0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank

    precision_sum = 0.0
    hits_so_far = 0
    for rank, flag in enumerate(relevance_flags, start=1):
        if flag:
            hits_so_far += 1
            precision_sum += hits_so_far / rank
    average_precision = precision_sum / len(relevant_ids)

    observed_grades = [context_relevance.get(chunk_id, 0) for chunk_id in retrieved_ids]
    ideal_grades = sorted(context_relevance.values(), reverse=True)[:k]
    ideal_dcg = _dcg(ideal_grades)
    ndcg = 0.0 if ideal_dcg == 0 else _dcg(observed_grades) / ideal_dcg

    required_hits = len(required_ids.intersection(retrieved_ids))
    required_recall = required_hits / len(required_ids)

    return {
        "k": k,
        "retrieved_relevant_count": relevant_retrieved,
        "judged_relevant_count": len(relevant_ids),
        "required_context_count": len(required_ids),
        "required_context_hit_count": required_hits,
        "precision_at_k": precision,
        "recall_at_k": recall,
        "f1_at_k": _safe_f1(precision, recall),
        "hit_at_k": float(relevant_retrieved > 0),
        "reciprocal_rank_at_k": reciprocal_rank,
        "average_precision_at_k": average_precision,
        "ndcg_at_k": ndcg,
        "required_context_recall_at_k": required_recall,
        "all_required_contexts_at_k": float(required_hits == len(required_ids)),
    }
