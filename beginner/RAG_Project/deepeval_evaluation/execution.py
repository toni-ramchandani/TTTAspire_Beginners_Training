"""Execute DeepEval and normalize its result objects into stable report fields."""

from __future__ import annotations

from typing import Any

from .metrics import DEEPEVAL_NAME_TO_KEY


def run_deepeval(
    test_cases: list[Any],
    metrics: list[Any],
    identifier: str,
    max_concurrent: int,
    run_async: bool = True,
) -> Any:
    from deepeval import evaluate
    from deepeval.evaluate.configs import (
        AsyncConfig,
        CacheConfig,
        DisplayConfig,
        ErrorConfig,
    )

    return evaluate(
        test_cases=test_cases,
        metrics=metrics,
        identifier=identifier,
        async_config=AsyncConfig(
            run_async=run_async,
            max_concurrent=max_concurrent,
        ),
        display_config=DisplayConfig(
            show_indicator=False,
            print_results=False,
            inspect_after_run=False,
        ),
        cache_config=CacheConfig(write_cache=False, use_cache=False),
        # Preserve partial evidence. Errors remain errors in the report and are
        # never converted to zero scores.
        error_config=ErrorConfig(ignore_errors=True, skip_on_missing_params=False),
    )


def normalize_evaluation_result(result: Any) -> dict[str, dict[str, Any]]:
    """Return results keyed by golden case ID and canonical metric key."""

    normalized: dict[str, dict[str, Any]] = {}
    for test_result in result.test_results:
        metadata = test_result.metadata or {}
        case_id = str(metadata.get("case_id") or test_result.name)
        metrics: dict[str, Any] = {}
        for metric in test_result.metrics_data or []:
            key = DEEPEVAL_NAME_TO_KEY.get(metric.name)
            if key is None:
                key = metric.name.lower().replace(" [geval]", "").replace(" ", "_")
            metrics[key] = {
                "display_name": metric.name,
                "value": metric.score,
                "threshold": metric.threshold,
                "passed": metric.success,
                "reason": metric.reason,
                "error": metric.error,
                "evaluation_model": metric.evaluation_model,
                "evaluation_cost": metric.evaluation_cost,
                "input_tokens": metric.input_tokens,
                "output_tokens": metric.output_tokens,
            }
        normalized[case_id] = {
            "case_passed": test_result.success,
            "metrics": metrics,
        }
    return normalized

