"""Typed contracts for golden cases, RAG traces, and metric outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class EvaluationDataError(ValueError):
    """Raised when a golden case or trace violates the evaluation contract."""


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluationDataError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise EvaluationDataError(f"{field_name} must be a list of non-empty strings.")
    return tuple(item.strip() for item in value)


@dataclass(frozen=True)
class GoldenCase:
    """Human-owned expected behavior for one evaluation question."""

    case_id: str
    question: str
    reference: str
    required_context_ids: tuple[str, ...]
    context_relevance: dict[str, int]
    expected_citation_ids: tuple[str, ...]
    required_concepts: tuple[tuple[str, ...], ...]
    forbidden_claim_patterns: tuple[str, ...]
    tags: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GoldenCase":
        if not isinstance(value, dict):
            raise EvaluationDataError("Every golden case must be a JSON object.")

        required_context_ids = _string_tuple(
            value.get("required_context_ids"), "required_context_ids"
        )
        if not required_context_ids:
            raise EvaluationDataError("required_context_ids must contain at least one ID.")
        if len(required_context_ids) != len(set(required_context_ids)):
            raise EvaluationDataError("required_context_ids must not contain duplicates.")

        raw_relevance = value.get("context_relevance")
        if not isinstance(raw_relevance, dict) or not raw_relevance:
            raise EvaluationDataError("context_relevance must be a non-empty object.")
        context_relevance: dict[str, int] = {}
        for chunk_id, grade in raw_relevance.items():
            if not isinstance(chunk_id, str) or not chunk_id.strip():
                raise EvaluationDataError(
                    "context_relevance keys must be non-empty chunk IDs."
                )
            if not isinstance(grade, int) or isinstance(grade, bool) or not 1 <= grade <= 3:
                raise EvaluationDataError(
                    "context_relevance grades must be integers from 1 to 3."
                )
            context_relevance[chunk_id.strip()] = grade

        missing_grades = set(required_context_ids) - set(context_relevance)
        if missing_grades:
            raise EvaluationDataError(
                "Every required context must have a relevance grade: "
                + ", ".join(sorted(missing_grades))
            )

        expected_citation_ids = _string_tuple(
            value.get("expected_citation_ids", list(required_context_ids)),
            "expected_citation_ids",
        )

        raw_concepts = value.get("required_concepts", [])
        if not isinstance(raw_concepts, list):
            raise EvaluationDataError("required_concepts must be a list of pattern groups.")
        required_concepts: list[tuple[str, ...]] = []
        for index, group in enumerate(raw_concepts, start=1):
            patterns = _string_tuple(group, f"required_concepts group {index}")
            if not patterns:
                raise EvaluationDataError(
                    f"required_concepts group {index} must contain a pattern."
                )
            required_concepts.append(patterns)

        return cls(
            case_id=_required_text(value.get("case_id"), "case_id"),
            question=_required_text(value.get("question"), "question"),
            reference=_required_text(value.get("reference"), "reference"),
            required_context_ids=required_context_ids,
            context_relevance=context_relevance,
            expected_citation_ids=expected_citation_ids,
            required_concepts=tuple(required_concepts),
            forbidden_claim_patterns=_string_tuple(
                value.get("forbidden_claim_patterns", []),
                "forbidden_claim_patterns",
            ),
            tags=_string_tuple(value.get("tags", []), "tags"),
        )

    @property
    def relevant_context_ids(self) -> frozenset[str]:
        return frozenset(
            chunk_id for chunk_id, grade in self.context_relevance.items() if grade > 0
        )


@dataclass(frozen=True)
class TraceRecord:
    """Validated subset of the canonical RAG trace used by evaluators."""

    run_id: str
    question: str
    answer: str
    provider: str
    embedding_model: str
    generation_model: str
    top_k: int
    retrieved_chunk_ids: tuple[str, ...]
    retrieved_contexts: tuple[str, ...]
    retrieval_scores: tuple[float, ...]
    retrieval_latency_ms: int
    generation_latency_ms: int
    total_latency_ms: int

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TraceRecord":
        if not isinstance(value, dict):
            raise EvaluationDataError("Trace must be a JSON object.")

        ids = _string_tuple(value.get("retrieved_chunk_ids"), "retrieved_chunk_ids")
        contexts = _string_tuple(
            value.get("retrieved_contexts"), "retrieved_contexts"
        )
        raw_scores = value.get("retrieval_scores")
        if not isinstance(raw_scores, list) or any(
            not isinstance(score, (int, float)) or isinstance(score, bool)
            for score in raw_scores
        ):
            raise EvaluationDataError("retrieval_scores must be a numeric list.")
        scores = tuple(float(score) for score in raw_scores)

        if not (len(ids) == len(contexts) == len(scores)):
            raise EvaluationDataError(
                "Retrieved IDs, contexts, and scores must have equal lengths."
            )
        if len(ids) != len(set(ids)):
            raise EvaluationDataError("retrieved_chunk_ids must not contain duplicates.")

        top_k = value.get("top_k")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise EvaluationDataError("top_k must be a positive integer.")
        if top_k != len(ids):
            raise EvaluationDataError(
                "Trace top_k must equal the number of retrieved contexts."
            )

        def non_negative_int(field_name: str) -> int:
            raw = value.get(field_name, 0)
            if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
                raise EvaluationDataError(
                    f"{field_name} must be a non-negative integer."
                )
            return raw

        return cls(
            run_id=_required_text(value.get("run_id"), "run_id"),
            question=_required_text(value.get("question"), "question"),
            answer=_required_text(value.get("answer"), "answer"),
            provider=_required_text(value.get("provider"), "provider"),
            embedding_model=_required_text(
                value.get("embedding_model"), "embedding_model"
            ),
            generation_model=_required_text(
                value.get("generation_model"), "generation_model"
            ),
            top_k=top_k,
            retrieved_chunk_ids=ids,
            retrieved_contexts=contexts,
            retrieval_scores=scores,
            retrieval_latency_ms=non_negative_int("retrieval_latency_ms"),
            generation_latency_ms=non_negative_int("generation_latency_ms"),
            total_latency_ms=non_negative_int("total_latency_ms"),
        )


@dataclass(frozen=True)
class SemanticMetricOutcome:
    """Serializable result of one Ragas metric call."""

    value: float | None
    reason: str | None
    error: str | None
    latency_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "reason": self.reason,
            "error": self.error,
            "latency_ms": self.latency_ms,
        }
