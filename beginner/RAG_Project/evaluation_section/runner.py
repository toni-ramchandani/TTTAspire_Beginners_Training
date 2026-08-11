"""Run the current RAG and evaluator layers against selected seed cases."""

from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.judges import JudgeSettings, build_judge_bundle, dependency_versions
from evaluation.models import TraceRecord
from evaluation.ragas_runner import build_metric_calls
from evaluation.reporting import build_summary
from evaluation.runner import evaluate_case
from rag.config import Settings
from rag.pipeline import RAGApplication

from .dataset import load_seed_dataset, select_seed_cases, validate_seed_dataset
from .diagnosis import diagnose_case


def _save(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "latest.json"
    csv_path = output_dir / "latest.csv"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "case_id",
                "scenario_type",
                "business_critical",
                "review_status",
                "bounded_outcome",
                "required_context_recall_at_k",
                "precision_at_k",
                "required_concept_coverage",
                "forbidden_claim_pass",
                "citation_recall",
                "total_latency_ms",
                "issue_components",
            ],
        )
        writer.writeheader()
        for result in report["cases"]:
            diagnosis = result["diagnosis"]
            writer.writerow(
                {
                    "case_id": result["case_id"],
                    "scenario_type": diagnosis["scenario_type"],
                    "business_critical": diagnosis["business_critical"],
                    "review_status": diagnosis["review_status"],
                    "bounded_outcome": diagnosis["bounded_outcome"],
                    "required_context_recall_at_k": result["retrieval_metrics"]["required_context_recall_at_k"],
                    "precision_at_k": result["retrieval_metrics"]["precision_at_k"],
                    "required_concept_coverage": result["deterministic_metrics"]["required_concept_coverage"],
                    "forbidden_claim_pass": result["deterministic_metrics"]["forbidden_claim_pass"],
                    "citation_recall": result["deterministic_metrics"]["citation_recall"],
                    "total_latency_ms": result["trace"]["total_latency_ms"],
                    "issue_components": "|".join(item["component"] for item in diagnosis["issues"]),
                }
            )
    return json_path, csv_path


def run_seed_evaluation(
    project_root: Path,
    dataset_path: Path,
    output_dir: Path,
    rag_provider: str,
    judge_provider: str | None,
    top_k: int,
    metric_profile: str,
    case_ids: list[str] | None,
    skip_ragas: bool,
) -> tuple[dict[str, Any], Path, Path]:
    all_cases = load_seed_dataset(dataset_path)
    validation = validate_seed_dataset(all_cases, project_root / "documents")
    if not validation["valid"]:
        raise ValueError("Seed dataset validation failed: " + "; ".join(validation["errors"]))
    selected = select_seed_cases(all_cases, case_ids)

    app = RAGApplication(project_root, Settings.from_env(project_root, rag_provider))
    bundle = None
    metric_calls = None
    if not skip_ragas:
        bundle = build_judge_bundle(
            JudgeSettings.from_env(project_root, judge_provider or rag_provider)
        )
        metric_calls = build_metric_calls(bundle, metric_profile)

    results: list[dict[str, Any]] = []
    for seed_case in selected:
        raw_trace, trace_path = app.ask(seed_case.golden_case.question, top_k)
        trace = TraceRecord.from_dict(raw_trace.to_dict())
        result = evaluate_case(seed_case.golden_case, trace, metric_calls, trace_path)
        result["seed_metadata"] = {
            "source_type": seed_case.source_type,
            "review_status": seed_case.review_status,
            "scenario_type": seed_case.scenario_type,
            "business_critical": seed_case.business_critical,
            "risk_areas": list(seed_case.risk_areas),
        }
        result["diagnosis"] = diagnose_case(result, seed_case)
        results.append(result)

    now = datetime.now(timezone.utc)
    report: dict[str, Any] = {
        "schema_version": "evaluation-section-1.0",
        "experiment_id": f"seed-eval-{now.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "created_at_utc": now.isoformat(),
        "dataset_validation": validation,
        "selected_case_count": len(selected),
        "requested_top_k": top_k,
        "metric_profile": metric_profile,
        "ragas_enabled": not skip_ragas,
        "judge": (
            None
            if bundle is None
            else {
                "provider": bundle.settings.provider,
                "chat_model": bundle.settings.chat_model,
                "embedding_model": bundle.settings.embedding_model,
            }
        ),
        "dependency_versions": dependency_versions(),
        "cases": results,
    }
    report["summary"] = build_summary(results)
    report["blocking_policy_case_ids"] = [
        result["case_id"]
        for result in results
        if result["diagnosis"]["bounded_outcome"] == "blocking_policy_failure_observed"
    ]
    report["interpretation_rule"] = (
        "Per-case evidence and business-critical failures take precedence over aggregate means. "
        "No composite RAG quality score is calculated."
    )
    json_path, csv_path = _save(report, output_dir)
    return report, json_path, csv_path
