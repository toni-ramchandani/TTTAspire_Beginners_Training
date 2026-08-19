"""Transparent evaluator functions executed by the LangSmith experiment runner.

LangSmith records evaluator results as feedback; it does not define the metric
mathematics in these functions. The calculations reuse the project's existing
exact retrieval, citation, concept, and policy checks.
"""

from __future__ import annotations

import statistics
from typing import Any

from evaluation.deterministic_metrics import compute_deterministic_metrics
from evaluation.models import GoldenCase
from evaluation.retrieval_metrics import compute_retrieval_metrics


def _case(reference_outputs: dict[str, Any]) -> GoldenCase:
    return GoldenCase(
        case_id="langsmith-evaluator",
        question="not-required",
        reference=str(reference_outputs.get("answer") or "reference unavailable"),
        required_context_ids=tuple(reference_outputs["required_context_ids"]),
        context_relevance={
            str(key): int(value)
            for key, value in reference_outputs["context_relevance"].items()
        },
        expected_citation_ids=tuple(reference_outputs["expected_citation_ids"]),
        required_concepts=tuple(
            tuple(group) for group in reference_outputs["required_concepts"]
        ),
        forbidden_claim_patterns=tuple(
            reference_outputs["forbidden_claim_patterns"]
        ),
        tags=(),
    )


def retrieval_required_context(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> dict[str, Any]:
    case = _case(reference_outputs)
    retrieved_ids = list(outputs.get("retrieved_chunk_ids") or [])
    if not retrieved_ids:
        return {
            "key": "required_context_recall",
            "score": 0.0,
            "comment": "The target emitted no retrieved chunk IDs.",
        }
    metrics = compute_retrieval_metrics(
        retrieved_ids,
        case.context_relevance,
        case.required_context_ids,
    )
    missing = sorted(set(case.required_context_ids) - set(retrieved_ids))
    return {
        "key": "required_context_recall",
        "score": metrics["required_context_recall_at_k"],
        "comment": (
            "All required contexts were retrieved."
            if not missing
            else "Missing required contexts: " + ", ".join(missing)
        ),
    }


def answer_policy_checks(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> list[dict[str, Any]]:
    case = _case(reference_outputs)
    answer = str(outputs.get("answer") or "")
    retrieved_ids = list(outputs.get("retrieved_chunk_ids") or [])
    metrics = compute_deterministic_metrics(answer, retrieved_ids, case)
    concept_total = len(case.required_concepts)
    concept_score = float(metrics["required_concept_coverage"])
    forbidden_matches = list(metrics["forbidden_claim_matches"])
    return [
        {
            "key": "required_concept_coverage",
            "score": concept_score,
            "comment": (
                f"Matched {round(concept_score * concept_total)} of "
                f"{concept_total} required concept groups."
            ),
        },
        {
            "key": "forbidden_claim_pass",
            "score": float(metrics["forbidden_claim_pass"]),
            "comment": (
                "No forbidden claim pattern matched."
                if not forbidden_matches
                else "Matched forbidden patterns: " + " | ".join(forbidden_matches)
            ),
        },
    ]


def citation_checks(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> list[dict[str, Any]]:
    case = _case(reference_outputs)
    metrics = compute_deterministic_metrics(
        str(outputs.get("answer") or ""),
        list(outputs.get("retrieved_chunk_ids") or []),
        case,
    )
    cited_ids = list(metrics["cited_ids"])
    if not cited_ids:
        validity_comment = "No inline chunk-ID citations were present."
    elif metrics["invalid_cited_ids"]:
        validity_comment = (
            "Citations absent from retrieval: "
            + ", ".join(metrics["invalid_cited_ids"])
        )
    else:
        validity_comment = "Every citation names a retrieved chunk."
    return [
        {
            "key": "citation_validity",
            "score": metrics["citation_validity"],
            "comment": validity_comment,
        },
        {
            "key": "citation_recall",
            "score": metrics["citation_recall"],
            "comment": (
                "Expected citations found: "
                + str(len(case.expected_citation_ids) - len(metrics["missing_expected_citation_ids"]))
                + "/"
                + str(len(case.expected_citation_ids))
            ),
        },
    ]


def exact_reference_match(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> dict[str, Any]:
    expected = reference_outputs.get("answer")
    if expected is None:
        return {
            "key": "exact_reference_match",
            "value": "not_applicable",
            "comment": "This example intentionally has no natural-language reference.",
        }
    matched = str(outputs.get("answer") or "").strip() == str(expected).strip()
    return {
        "key": "exact_reference_match",
        "score": matched,
        "comment": (
            "Actual and reference strings match exactly."
            if matched
            else "Exact match failed; this does not by itself prove semantic incorrectness."
        ),
    }


def build_evaluators(profile: str) -> list[Any]:
    if profile == "core":
        return [retrieval_required_context, answer_policy_checks]
    if profile == "full":
        return [
            retrieval_required_context,
            answer_policy_checks,
            citation_checks,
            exact_reference_match,
        ]
    raise ValueError("metric profile must be 'core' or 'full'.")


def _comparison_vector(
    outputs: dict[str, Any], reference_outputs: dict[str, Any]
) -> tuple[float, float]:
    """Return a risk-first vector for transparent pairwise comparison.

    The first value is the blocking forbidden-claim result. The second is the
    mean of required-context recall, required-concept coverage, and citation
    recall. This is a workshop comparison rule, not a universal quality score.
    """

    retrieval = retrieval_required_context(outputs, reference_outputs)
    policy = {
        item["key"]: item for item in answer_policy_checks(outputs, reference_outputs)
    }
    citations = {
        item["key"]: item for item in citation_checks(outputs, reference_outputs)
    }
    evidence_coverage = statistics.fmean(
        [
            float(retrieval["score"]),
            float(policy["required_concept_coverage"]["score"]),
            float(citations["citation_recall"]["score"]),
        ]
    )
    return float(policy["forbidden_claim_pass"]["score"]), evidence_coverage


def pairwise_evidence_preference(
    outputs: list[dict[str, Any]],
    reference_outputs: dict[str, Any],
    runs: list[Any],
) -> dict[str, Any]:
    """Rank two cached experiment outputs using an explicit risk-first rule."""

    if len(outputs) != 2 or len(runs) != 2:
        raise ValueError("Pairwise comparison requires exactly two outputs and runs.")
    vectors = [
        _comparison_vector(output, reference_outputs) for output in outputs
    ]
    if vectors[0] > vectors[1]:
        scores = [1.0, 0.0]
        decision = "first run preferred"
    elif vectors[1] > vectors[0]:
        scores = [0.0, 1.0]
        decision = "second run preferred"
    else:
        scores = [0.5, 0.5]
        decision = "tie"
    return {
        "key": "pairwise_evidence_preference",
        "scores": {
            str(runs[0].id): scores[0],
            str(runs[1].id): scores[1],
        },
        "comment": (
            f"Risk-first vectors were {vectors[0]} and {vectors[1]}; {decision}. "
            "Each vector is (forbidden-claim pass, mean evidence coverage)."
        ),
    }


def experiment_summary(
    outputs: list[dict[str, Any]], reference_outputs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    recalls: list[float] = []
    forbidden_passes: list[float] = []
    concept_coverages: list[float] = []
    for output, reference in zip(outputs, reference_outputs):
        retrieval_result = retrieval_required_context(output, reference)
        recalls.append(float(retrieval_result["score"]))
        policy_results = {
            item["key"]: item for item in answer_policy_checks(output, reference)
        }
        forbidden_passes.append(float(policy_results["forbidden_claim_pass"]["score"]))
        concept_coverages.append(
            float(policy_results["required_concept_coverage"]["score"])
        )
    return [
        {
            "key": "mean_required_context_recall",
            "score": statistics.fmean(recalls) if recalls else 0.0,
        },
        {
            "key": "mean_required_concept_coverage",
            "score": statistics.fmean(concept_coverages) if concept_coverages else 0.0,
        },
        {
            "key": "forbidden_claim_pass_rate",
            "score": statistics.fmean(forbidden_passes) if forbidden_passes else 0.0,
        },
    ]
