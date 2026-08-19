"""Current Ragas 0.4 collections-based metric execution."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Callable

from .judges import JudgeBundle
from .models import GoldenCase, SemanticMetricOutcome, TraceRecord


@dataclass(frozen=True)
class MetricCall:
    name: str
    metric: Any
    arguments: Callable[[GoldenCase, TraceRecord], dict[str, Any]]


def build_metric_calls(bundle: JudgeBundle, profile: str) -> list[MetricCall]:
    try:
        from ragas.metrics.collections import (
            AnswerCorrectness,
            AnswerRelevancy,
            ContextPrecision,
            ContextPrecisionWithoutReference,
            ContextRecall,
            ContextRelevance,
            FactualCorrectness,
            Faithfulness,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "Cannot import Ragas 0.4 collection metrics. "
            "Run: pip install -r requirements-eval.txt"
        ) from exc

    if profile not in {"core", "full"}:
        raise ValueError("Metric profile must be 'core' or 'full'.")

    question_response = lambda case, trace: {  # noqa: E731
        "user_input": trace.question,
        "response": trace.answer,
    }
    response_reference = lambda case, trace: {  # noqa: E731
        "response": trace.answer,
        "reference": case.reference,
    }
    reference_contexts = lambda case, trace: {  # noqa: E731
        "user_input": trace.question,
        "reference": case.reference,
        "retrieved_contexts": list(trace.retrieved_contexts),
    }

    calls = [
        MetricCall(
            "faithfulness",
            Faithfulness(llm=bundle.llm),
            lambda case, trace: {
                "user_input": trace.question,
                "response": trace.answer,
                "retrieved_contexts": list(trace.retrieved_contexts),
            },
        ),
        MetricCall(
            "answer_relevancy",
            AnswerRelevancy(llm=bundle.llm, embeddings=bundle.embeddings),
            question_response,
        ),
        MetricCall(
            "factual_f1",
            FactualCorrectness(
                llm=bundle.llm, mode="f1", atomicity="high", coverage="high"
            ),
            response_reference,
        ),
        MetricCall(
            "context_precision",
            ContextPrecision(llm=bundle.llm),
            reference_contexts,
        ),
        MetricCall(
            "context_recall",
            ContextRecall(llm=bundle.llm),
            reference_contexts,
        ),
    ]

    if profile == "full":
        calls.extend(
            [
                MetricCall(
                    "factual_precision",
                    FactualCorrectness(
                        llm=bundle.llm,
                        mode="precision",
                        atomicity="high",
                        coverage="high",
                    ),
                    response_reference,
                ),
                MetricCall(
                    "factual_recall",
                    FactualCorrectness(
                        llm=bundle.llm,
                        mode="recall",
                        atomicity="high",
                        coverage="high",
                    ),
                    response_reference,
                ),
                MetricCall(
                    "answer_correctness",
                    AnswerCorrectness(llm=bundle.llm, embeddings=bundle.embeddings),
                    lambda case, trace: {
                        "user_input": trace.question,
                        "response": trace.answer,
                        "reference": case.reference,
                    },
                ),
                MetricCall(
                    "context_relevance",
                    ContextRelevance(llm=bundle.llm),
                    lambda case, trace: {
                        "user_input": trace.question,
                        "retrieved_contexts": list(trace.retrieved_contexts),
                    },
                ),
                MetricCall(
                    "context_utilization",
                    ContextPrecisionWithoutReference(llm=bundle.llm),
                    lambda case, trace: {
                        "user_input": trace.question,
                        "response": trace.answer,
                        "retrieved_contexts": list(trace.retrieved_contexts),
                    },
                ),
            ]
        )
    return calls


def score_with_ragas(
    case: GoldenCase,
    trace: TraceRecord,
    calls: list[MetricCall],
) -> dict[str, SemanticMetricOutcome]:
    outcomes: dict[str, SemanticMetricOutcome] = {}
    for call in calls:
        started = time.perf_counter()
        try:
            result = call.metric.score(**call.arguments(case, trace))
            raw_value = result.value
            if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
                raise TypeError(f"Ragas returned non-numeric value {raw_value!r}.")
            value = float(raw_value)
            if not math.isfinite(value):
                raise ValueError(f"Ragas returned non-finite value {value!r}.")
            outcomes[call.name] = SemanticMetricOutcome(
                value=value,
                reason=result.reason,
                error=None,
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:  # Preserve partial experiment evidence.
            outcomes[call.name] = SemanticMetricOutcome(
                value=None,
                reason=None,
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=round((time.perf_counter() - started) * 1000),
            )
    return outcomes
