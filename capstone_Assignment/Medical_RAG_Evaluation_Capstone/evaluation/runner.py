"""Orchestration for live and saved-trace Ragas experiments."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag.config import Settings
from rag.pipeline import RAGApplication

from .dataset import load_golden_cases, select_cases, validate_cases_against_corpus
from .deterministic_metrics import compute_deterministic_metrics
from .judges import JudgeBundle, JudgeSettings, build_judge_bundle, dependency_versions
from .models import EvaluationDataError, GoldenCase, TraceRecord
from .ragas_runner import MetricCall, build_metric_calls, score_with_ragas
from .reporting import apply_gates, build_summary, save_report
from .retrieval_metrics import compute_retrieval_metrics

EVALUATION_SCHEMA_VERSION = "1.0"


def load_trace(path: Path) -> TraceRecord:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvaluationDataError(f"Invalid JSON in trace {path}: {exc}") from exc
    return TraceRecord.from_dict(payload)


def evaluate_case(
    case: GoldenCase,
    trace: TraceRecord,
    metric_calls: list[MetricCall] | None,
    trace_path: Path | None,
) -> dict[str, Any]:
    retrieval = compute_retrieval_metrics(
        trace.retrieved_chunk_ids,
        case.context_relevance,
        case.required_context_ids,
    )
    deterministic = compute_deterministic_metrics(
        trace.answer, trace.retrieved_chunk_ids, case
    )
    semantic = (
        {}
        if metric_calls is None
        else {
            name: outcome.to_dict()
            for name, outcome in score_with_ragas(case, trace, metric_calls).items()
        }
    )
    return {
        "case_id": case.case_id,
        "tags": list(case.tags),
        "question": case.question,
        "reference": case.reference,
        "required_context_ids": list(case.required_context_ids),
        "context_relevance": case.context_relevance,
        "expected_citation_ids": list(case.expected_citation_ids),
        "trace": {
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
        },
        "retrieval_metrics": retrieval,
        "deterministic_metrics": deterministic,
        "ragas_metrics": semantic,
    }


def _new_report(
    mode: str,
    cases: list[dict[str, Any]],
    judge_bundle: JudgeBundle | None,
    metric_profile: str,
    requested_top_k: int | None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    report: dict[str, Any] = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "experiment_id": (
            f"ragas-{now.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
        ),
        "created_at_utc": now.isoformat(),
        "mode": mode,
        "requested_top_k": requested_top_k,
        "metric_profile": metric_profile,
        "judge": (
            None
            if judge_bundle is None
            else {
                "provider": judge_bundle.settings.provider,
                "chat_model": judge_bundle.settings.chat_model,
                "embedding_model": judge_bundle.settings.embedding_model,
                "base_url": judge_bundle.settings.base_url,
            }
        ),
        "dependency_versions": dependency_versions(),
        "cases": cases,
    }
    report["summary"] = build_summary(cases)
    return report


def _load_cases(
    project_root: Path, dataset_path: Path, case_ids: list[str] | None
) -> list[GoldenCase]:
    cases = load_golden_cases(dataset_path)
    validate_cases_against_corpus(cases, project_root / "documents")
    return select_cases(cases, case_ids)


def run_live_experiment(
    project_root: Path,
    dataset_path: Path,
    output_dir: Path,
    rag_provider: str,
    judge_provider: str | None,
    top_k: int,
    metric_profile: str,
    case_ids: list[str] | None = None,
    skip_ragas: bool = False,
    gates_path: Path | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    cases = _load_cases(project_root, dataset_path, case_ids)
    rag_settings = Settings.from_env(project_root, rag_provider)
    application = RAGApplication(project_root, rag_settings)

    bundle: JudgeBundle | None = None
    metric_calls: list[MetricCall] | None = None
    if not skip_ragas:
        bundle = build_judge_bundle(
            JudgeSettings.from_env(project_root, judge_provider or rag_provider)
        )
        metric_calls = build_metric_calls(bundle, metric_profile)

    results: list[dict[str, Any]] = []
    for case in cases:
        raw_trace, trace_path = application.ask(case.question, top_k)
        trace = TraceRecord.from_dict(raw_trace.to_dict())
        results.append(evaluate_case(case, trace, metric_calls, trace_path))

    report = _new_report("live", results, bundle, metric_profile, top_k)
    report["gates"] = apply_gates(report, gates_path)
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
    skip_ragas: bool = False,
    allow_question_mismatch: bool = False,
    gates_path: Path | None = None,
) -> tuple[dict[str, Any], Path, Path]:
    case = _load_cases(project_root, dataset_path, [case_id])[0]
    trace = load_trace(trace_path)
    if not allow_question_mismatch and trace.question != case.question:
        raise EvaluationDataError(
            "Trace question does not exactly match the selected golden case. "
            "Use the correct case or pass --allow-question-mismatch deliberately."
        )

    bundle: JudgeBundle | None = None
    metric_calls: list[MetricCall] | None = None
    if not skip_ragas:
        bundle = build_judge_bundle(
            JudgeSettings.from_env(project_root, judge_provider or trace.provider)
        )
        metric_calls = build_metric_calls(bundle, metric_profile)

    result = evaluate_case(case, trace, metric_calls, trace_path)
    report = _new_report("saved-trace", [result], bundle, metric_profile, trace.top_k)
    report["gates"] = apply_gates(report, gates_path)
    json_path, csv_path = save_report(report, output_dir)
    return report, json_path, csv_path
