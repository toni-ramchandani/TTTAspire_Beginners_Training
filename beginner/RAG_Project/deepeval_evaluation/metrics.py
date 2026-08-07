"""DeepEval metric profiles and explicit, configurable diagnostic thresholds."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


METRIC_KEYS = (
    "answer_relevancy",
    "faithfulness",
    "contextual_precision",
    "contextual_recall",
    "contextual_relevancy",
)

DEEPEVAL_NAME_TO_KEY = {
    "Answer Relevancy": "answer_relevancy",
    "Faithfulness": "faithfulness",
    "Contextual Precision": "contextual_precision",
    "Contextual Recall": "contextual_recall",
    "Contextual Relevancy": "contextual_relevancy",
    "Policy Correctness [GEval]": "policy_correctness",
}


@dataclass(frozen=True)
class DeepEvalThresholds:
    values: dict[str, float]

    @classmethod
    def from_env(cls) -> "DeepEvalThresholds":
        defaults = {
            "answer_relevancy": 0.70,
            "faithfulness": 0.70,
            "contextual_precision": 0.70,
            "contextual_recall": 0.70,
            "contextual_relevancy": 0.70,
            "policy_correctness": 0.70,
        }
        values: dict[str, float] = {}
        for key, default in defaults.items():
            variable = f"DEEPEVAL_THRESHOLD_{key.upper()}"
            try:
                value = float(os.getenv(variable, str(default)))
            except ValueError as exc:
                raise ValueError(f"{variable} must be numeric.") from exc
            if not 0 <= value <= 1:
                raise ValueError(f"{variable} must be between 0 and 1.")
            values[key] = value
        return cls(values=values)


def build_metric_suite(
    model: Any,
    profile: str,
    thresholds: DeepEvalThresholds,
    include_reason: bool = True,
    verbose_mode: bool = False,
) -> list[Any]:
    try:
        from deepeval.metrics import (
            AnswerRelevancyMetric,
            ContextualPrecisionMetric,
            ContextualRecallMetric,
            ContextualRelevancyMetric,
            FaithfulnessMetric,
            GEval,
        )
        from deepeval.test_case import SingleTurnParams
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "Cannot import DeepEval 4 metrics. Run: "
            "pip install -r requirements-deepeval.txt"
        ) from exc

    if profile not in {"core", "full"}:
        raise ValueError("Metric profile must be 'core' or 'full'.")

    common = {
        "model": model,
        "include_reason": include_reason,
        "async_mode": True,
        "strict_mode": False,
        "verbose_mode": verbose_mode,
    }
    metrics: list[Any] = [
        AnswerRelevancyMetric(
            threshold=thresholds.values["answer_relevancy"], **common
        ),
        FaithfulnessMetric(threshold=thresholds.values["faithfulness"], **common),
        ContextualPrecisionMetric(
            threshold=thresholds.values["contextual_precision"], **common
        ),
        ContextualRecallMetric(
            threshold=thresholds.values["contextual_recall"], **common
        ),
        ContextualRelevancyMetric(
            threshold=thresholds.values["contextual_relevancy"], **common
        ),
    ]
    if profile == "full":
        metrics.append(
            GEval(
                name="Policy Correctness",
                evaluation_params=[
                    SingleTurnParams.INPUT,
                    SingleTurnParams.ACTUAL_OUTPUT,
                    SingleTurnParams.EXPECTED_OUTPUT,
                ],
                evaluation_steps=[
                    "Compare the actual output with the approved expected output.",
                    "Check whether material recovery, escalation, safety, and uncertainty requirements are present and correct.",
                    "Penalize unsafe shortcuts, invented facts, unsupported guarantees, and material omissions.",
                    "Judge policy correctness only; do not reward writing style or verbosity.",
                ],
                model=model,
                threshold=thresholds.values["policy_correctness"],
                async_mode=True,
                strict_mode=False,
                verbose_mode=verbose_mode,
            )
        )
    return metrics

