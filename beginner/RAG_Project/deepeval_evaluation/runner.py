"""Orchestration for live and saved-trace DeepEval experiments."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag.config import Settings
from rag.pipeline import RAGApplication

from evaluation.dataset import load_golden_cases, select_cases, validate_cases_against_corpus
from evaluation.deterministic_metrics import compute_deterministic_metrics
from evaluation.models import EvaluationDataError, GoldenCase, TraceRecord
from evaluation.retrieval_metrics import compute_retrieval_metrics

from . import DEEPEVAL_REPORT_SCHEMA_VERSION
from .adapter import to_llm_test_case
from .execution import normalize_evaluation_result, run_deepeval
from .judges import (
    DeepEvalJudgeBundle,
    DeepEvalJudgeSettings,
    build_judge_bundle,
    dependency_versions,
)
from .metrics import DeepEvalThresholds, build_metric_suite
from .reporting import build_summary, save_report


def load_trace(path: Path) -> TraceRecord:
    """Load the canonical application trace without importing the Ragas runner."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvaluationDataError(f"Invalid JSON in trace {path}: {exc}") from exc
    return TraceRecord.from_dict(payload)


def _load_cases(
    project_root: Path, dataset_path: Path, case_ids: list[str] | None
) -> list[GoldenCase]:
    cases = load_golden_cases(dataset_path)
    validate_cases_against_corpus(cases, project_root / "documents")
    return select_cases(cases, case_ids)


def _trace_payload(trace: TraceRecord, trace_path: Path | None) -> dict[str, Any]:
    return {
        "trace_path": str(trace_path) if trace_path else None,
        "run_id": trace.run_id,
        "provider": trace.provider,
        "embedding_model": trace.embedding_model,
        "generation_model": trace.generation_model,
        "top_k": trace.top_k,
        "question": trace.question,
        "answer": trace.answer,
        "retrieved_chunk_ids": list(trace.retrieved_chunk_ids),
        "retrieved_contexts": list(trace.retrieved_contexts),
        "retrieval_scores": list(trace.retrieval_scores),
        "retrieval_latency_ms": trace.retrieval_latency_ms,
        "generation_latency_ms": trace.generation_latency_ms,
        "total_latency_ms": trace.total_latency_ms,
    }


def _base_case_result(
    case: GoldenCase, trace: TraceRecord, trace_path: Path | None
) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "tags": list(case.tags),
        "question": case.question,
        "reference": case.reference,
        "required_context_ids": list(case.required_context_ids),
        "context_relevance": case.context_relevance,
        "expected_citation_ids": list(case.expected_citation_ids),
        "trace": _trace_payload(trace, trace_path),
        "retrieval_metrics": compute_retrieval_metrics(
            trace.retrieved_chunk_ids,
            case.context_relevance,
            case.required_context_ids,
        ),
        "deterministic_metrics": compute_deterministic_metrics(
            trace.answer, trace.retrieved_chunk_ids, case
        ),
        "deepeval_case_passed": None,
        "deepeval_metrics": {},
    }


def _evaluate_traces(
    cases_and_traces: list[tuple[GoldenCase, TraceRecord, Path | None]],
    bundle: DeepEvalJudgeBundle | None,
    metric_profile: str,
    thresholds: DeepEvalThresholds,
) -> list[dict[str, Any]]:
    results = [
        _base_case_result(case, trace, trace_path)
        for case, trace, trace_path in cases_and_traces
    ]
    if bundle is None:
        return results

    test_cases = [
        to_llm_test_case(case, trace) for case, trace, _path in cases_and_traces
    ]
    metrics = build_metric_suite(bundle.model, metric_profile, thresholds)
    evaluation = run_deepeval(
        test_cases=test_cases,
        metrics=metrics,
        identifier=f"payroll-mfa-{metric_profile}",
        max_concurrent=bundle.settings.max_concurrent,
        run_async=True,
    )
    semantic_by_case = normalize_evaluation_result(evaluation)
    expected_case_ids = {case.case_id for case, _trace, _path in cases_and_traces}
    missing = expected_case_ids - set(semantic_by_case)
    if missing:
        raise EvaluationDataError(
            "DeepEval returned no result for cases: " + ", ".join(sorted(missing))
        )
    for result in results:
        semantic = semantic_by_case[result["case_id"]]
        result["deepeval_case_passed"] = semantic["case_passed"]
        result["deepeval_metrics"] = semantic["metrics"]
    return results


def _new_report(
    mode: str,
    cases: list[dict[str, Any]],
    bundle: DeepEvalJudgeBundle | None,
    metric_profile: str,
    thresholds: DeepEvalThresholds,
    requested_top_k: int | None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    report: dict[str, Any] = {
        "schema_version": DEEPEVAL_REPORT_SCHEMA_VERSION,
        "framework": "deepeval",
        "experiment_id": (
            f"deepeval-{now.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
        ),
        "created_at_utc": now.isoformat(),
        "mode": mode,
        "requested_top_k": requested_top_k,
        "metric_profile": metric_profile,
        "thresholds": thresholds.values,
        "threshold_note": (
            "Defaults are diagnostic starting points and require human calibration "
            "before use as release gates."
        ),
        "judge": (
            None
            if bundle is None
            else {
                "provider": bundle.settings.provider,
                "model": bundle.settings.model_name,
                "base_url": bundle.settings.base_url,
                "max_concurrent": bundle.settings.max_concurrent,
            }
        ),
        "dependency_versions": dependency_versions(),
        "cases": cases,
    }
    report["summary"] = build_summary(cases)
    return report


def run_live_experiment(
    project_root: Path,
    dataset_path: Path,
    output_dir: Path,
    rag_provider: str,
    judge_provider: str | None,
    top_k: int,
    metric_profile: str,
    case_ids: list[str] | None = None,
    skip_deepeval: bool = False,
) -> tuple[dict[str, Any], Path, Path]:
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    cases = _load_cases(project_root, dataset_path, case_ids)
    rag_settings = Settings.from_env(project_root, rag_provider)
    application = RAGApplication(project_root, rag_settings)
    thresholds = DeepEvalThresholds.from_env()

    bundle: DeepEvalJudgeBundle | None = None
    if not skip_deepeval:
        bundle = build_judge_bundle(
            DeepEvalJudgeSettings.from_env(
                project_root, judge_provider or rag_provider
            )
        )

    cases_and_traces: list[tuple[GoldenCase, TraceRecord, Path | None]] = []
    for case in cases:
        raw_trace, trace_path = application.ask(case.question, top_k)
        cases_and_traces.append(
            (case, TraceRecord.from_dict(raw_trace.to_dict()), trace_path)
        )
    results = _evaluate_traces(
        cases_and_traces, bundle, metric_profile, thresholds
    )
    report = _new_report(
        "live", results, bundle, metric_profile, thresholds, top_k
    )
    json_path, csv_path = save_report(report, output_dir)
    return report, json_path, csv_path


def run_trace_experiment(
    project_root: Path,
    dataset_path: Path,
    output_dir: Path,
    trace_path: Path,
    case_id: str,
    judge_provider: str | None,
    metric_profile: str,
    skip_deepeval: bool = False,
    allow_question_mismatch: bool = False,
) -> tuple[dict[str, Any], Path, Path]:
    case = _load_cases(project_root, dataset_path, [case_id])[0]
    trace = load_trace(trace_path)
    if not allow_question_mismatch and trace.question != case.question:
        raise EvaluationDataError(
            "Trace question does not exactly match the selected golden case. "
            "Use the correct case or pass --allow-question-mismatch deliberately."
        )
    thresholds = DeepEvalThresholds.from_env()
    bundle: DeepEvalJudgeBundle | None = None
    if not skip_deepeval:
        bundle = build_judge_bundle(
            DeepEvalJudgeSettings.from_env(
                project_root, judge_provider or trace.provider
            )
        )
    results = _evaluate_traces(
        [(case, trace, trace_path)], bundle, metric_profile, thresholds
    )
    report = _new_report(
        "saved-trace", results, bundle, metric_profile, thresholds, trace.top_k
    )
    json_path, csv_path = save_report(report, output_dir)
    return report, json_path, csv_path
