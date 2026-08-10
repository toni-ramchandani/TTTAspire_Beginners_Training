"""Local JSON and CSV evidence for LangSmith SDK experiment results."""

from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPORT_SCHEMA_VERSION = "1.0"


def _evaluation_item(item: Any) -> dict[str, Any]:
    extra = getattr(item, "extra", None)
    return {
        "score": getattr(item, "score", None),
        "value": getattr(item, "value", None),
        "comment": getattr(item, "comment", None),
        "correction": getattr(item, "correction", None),
        "extra": extra if isinstance(extra, dict) else None,
    }


def normalize_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        run = row["run"]
        example = row["example"]
        run_error = getattr(run, "error", None)
        run_end = getattr(run, "end_time", None)
        run_status = getattr(run, "status", None)
        if run_status is None:
            run_status = "error" if run_error else "success" if run_end else "pending"
        feedback: dict[str, Any] = {}
        for item in row["evaluation_results"]["results"]:
            feedback[str(item.key)] = _evaluation_item(item)
        normalized.append(
            {
                "case_id": (example.inputs or {}).get("case_id"),
                "inputs": example.inputs,
                "actual_outputs": run.outputs,
                "reference_outputs": example.outputs,
                "example_metadata": example.metadata,
                "run": {
                    "id": str(run.id),
                    "name": run.name,
                    "status": run_status,
                    "error": run_error,
                    "start_time": run.start_time.isoformat(),
                    "end_time": (
                        run_end.isoformat() if run_end else None
                    ),
                },
                "feedback": feedback,
            }
        )
    return normalized


def _numeric_scores(cases: list[dict[str, Any]]) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {}
    for case in cases:
        for key, outcome in case["feedback"].items():
            score = outcome.get("score")
            if isinstance(score, bool):
                score = float(score)
            if isinstance(score, (int, float)):
                values.setdefault(key, []).append(float(score))
    return values


def build_report(
    *,
    mode: str,
    profile: str,
    cases: list[dict[str, Any]],
    upload_results: bool,
    sdk_version: str,
    experiment_name: str | None,
    experiment_id: str | None,
    experiment_url: str | None,
    project_name: str,
    dataset_name: str,
    dataset_version: str,
    rag_provider: str | None,
    top_k: int | None,
    num_repetitions: int,
) -> dict[str, Any]:
    numeric = _numeric_scores(cases)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "framework": "langsmith",
        "framework_version": sdk_version,
        "report_id": f"langsmith-{uuid.uuid4().hex[:12]}",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "upload_results": upload_results,
        "experiment_name": experiment_name,
        "experiment_id": experiment_id,
        "experiment_url": experiment_url,
        "project_name": project_name,
        "dataset_name": dataset_name,
        "dataset_version": dataset_version,
        "metric_profile": profile,
        "rag_provider": rag_provider,
        "top_k": top_k,
        "num_repetitions": num_repetitions,
        "summary": {
            "case_count": len(cases),
            "run_error_count": sum(1 for case in cases if case["run"]["error"]),
            "mean_feedback_scores": {
                key: sum(scores) / len(scores)
                for key, scores in sorted(numeric.items())
                if scores
            },
            "scored_case_counts": {
                key: len(scores) for key, scores in sorted(numeric.items())
            },
        },
        "cases": cases,
    }


def _flatten_case(case: dict[str, Any]) -> dict[str, Any]:
    actual = case.get("actual_outputs") or {}
    reference = case.get("reference_outputs") or {}
    row: dict[str, Any] = {
        "case_id": case.get("case_id"),
        "question": (case.get("inputs") or {}).get("question"),
        "actual_answer": actual.get("answer"),
        "reference_answer": reference.get("answer"),
        "retrieved_chunk_ids": " | ".join(
            actual.get("retrieved_chunk_ids") or []
        ),
        "run_id": case["run"]["id"],
        "run_status": case["run"]["status"],
        "run_error": case["run"]["error"],
    }
    for key, outcome in case["feedback"].items():
        prefix = f"langsmith_feedback_{key}"
        row[f"{prefix}_score"] = outcome.get("score")
        row[f"{prefix}_value"] = outcome.get("value")
        row[f"{prefix}_comment"] = outcome.get("comment")
    return row


def save_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = report["report_id"]
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    json_path.write_text(payload, encoding="utf-8")
    (output_dir / "latest.json").write_text(payload, encoding="utf-8")

    rows = [_flatten_case(case) for case in report["cases"]]
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "latest.csv").write_text(
        csv_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return json_path, csv_path
