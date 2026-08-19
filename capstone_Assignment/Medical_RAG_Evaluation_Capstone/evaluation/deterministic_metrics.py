"""Citation and policy checks that do not call an evaluator model."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from .models import GoldenCase

CITATION_PATTERN = re.compile(r"\[([A-Za-z0-9._-]+::[A-Za-z0-9._-]+)\]")

DETERMINISTIC_RATE_METRICS = (
    "citation_validity",
    "citation_precision",
    "citation_recall",
    "citation_f1",
    "required_concept_coverage",
    "forbidden_claim_pass",
)


def _ordered_unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _fraction(numerator: int, denominator: int, empty_value: float) -> float:
    return empty_value if denominator == 0 else numerator / denominator


def compute_deterministic_metrics(
    answer: str,
    retrieved_ids: Sequence[str],
    case: GoldenCase,
) -> dict[str, Any]:
    cited_ids = _ordered_unique(CITATION_PATTERN.findall(answer))
    retrieved_set = set(retrieved_ids)
    expected_set = set(case.expected_citation_ids)
    cited_set = set(cited_ids)

    valid_citations = cited_set & retrieved_set
    expected_citations = cited_set & expected_set
    citation_validity = _fraction(
        len(valid_citations), len(cited_set), 1.0 if not expected_set else 0.0
    )
    citation_precision = _fraction(
        len(expected_citations), len(cited_set), 1.0 if not expected_set else 0.0
    )
    citation_recall = _fraction(
        len(expected_citations), len(expected_set), 1.0
    )
    citation_f1 = (
        0.0
        if citation_precision + citation_recall == 0
        else 2
        * citation_precision
        * citation_recall
        / (citation_precision + citation_recall)
    )

    concept_matches: list[dict[str, Any]] = []
    for patterns in case.required_concepts:
        matched = next(
            (
                pattern
                for pattern in patterns
                if re.search(pattern, answer, flags=re.IGNORECASE | re.MULTILINE)
            ),
            None,
        )
        concept_matches.append(
            {"patterns": list(patterns), "matched": matched is not None, "match": matched}
        )

    forbidden_matches = [
        pattern
        for pattern in case.forbidden_claim_patterns
        if re.search(pattern, answer, flags=re.IGNORECASE | re.MULTILINE)
    ]

    matched_concepts = sum(1 for item in concept_matches if item["matched"])
    concept_coverage = _fraction(
        matched_concepts, len(concept_matches), 1.0
    )

    return {
        "cited_ids": cited_ids,
        "invalid_cited_ids": sorted(cited_set - retrieved_set),
        "unexpected_cited_ids": sorted(cited_set - expected_set),
        "missing_expected_citation_ids": sorted(expected_set - cited_set),
        "citation_count": len(cited_ids),
        "citation_validity": citation_validity,
        "citation_precision": citation_precision,
        "citation_recall": citation_recall,
        "citation_f1": citation_f1,
        "required_concept_coverage": concept_coverage,
        "concept_matches": concept_matches,
        "forbidden_claim_pass": float(not forbidden_matches),
        "forbidden_claim_matches": forbidden_matches,
    }
