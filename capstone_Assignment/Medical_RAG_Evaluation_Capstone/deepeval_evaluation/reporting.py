"""DeepEval-specific aggregation and JSON/CSV persistence."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

from evaluation.deterministic_metrics import DETERMINISTIC_RATE_METRICS
from evaluation.retrieval_metrics import RETRIEVAL_RATE_METRICS


def _mean(values: list[float]) -> float | None:
    return None if not values else fmean(values)


def build_summary(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval_macro = {
        metric: _mean(
            [float(result["retrieval_metrics"][metric]) for result in case_results]
        )
        for metric in RETRIEVAL_RATE_METRICS
    }
    deterministic_macro = {
        metric: _mean(
            [float(result["deterministic_metrics"][metric]) for result in case_results]
        )
        for metric in DETERMINISTIC_RATE_METRICS
    }

    metric_scores: dict[str, list[float]] = defaultdict(list)
    metric_passes: dict[str, int] = defaultdict(int)
    metric_attempts: dict[str, int] = defaultdict(int)
    metric_errors: dict[str, int] = defaultdict(int)
    total_errors = 0
    total_attempts = 0
    for result in case_results:
        for name, outcome in result["deepeval_metrics"].items():
            total_attempts += 1
            metric_attempts[name] += 1
            if outcome["error"] is not None:
                total_errors += 1
                metric_errors[name] += 1
                continue
            if outcome["value"] is not None:
                metric_scores[name].append(float(outcome["value"]))
            if outcome["passed"] is True:
                metric_passes[name] += 1

    metric_names = sorted(
        set(metric_attempts) | set(metric_scores) | set(metric_errors)
    )
    semantic = {
        name: {
            "mean_score": _mean(metric_scores[name]),
            "attempts": metric_attempts[name],
            "scored": len(metric_scores[name]),
            "errors": metric_errors[name],
            "passes": metric_passes[name],
            "pass_rate": (
                None
                if metric_attempts[name] - metric_errors[name] == 0
                else metric_passes[name]
                / (metric_attempts[name] - metric_errors[name])
            ),
        }
        for name in metric_names
    }

    attempted_cases = [
        result for result in case_results if result["deepeval_metrics"]
    ]
    passed_cases = sum(
        1 for result in attempted_cases if result["deepeval_case_passed"] is True
    )
    total_retrieved = sum(
        int(result["retrieval_metrics"]["k"]) for result in case_results
    )
    total_relevant_hits = sum(
        int(result["retrieval_metrics"]["retrieved_relevant_count"])
        for result in case_results
    )
    total_relevant = sum(
        int(result["retrieval_metrics"]["judged_relevant_count"])
        for result in case_results
    )
    return {
        "case_count": len(case_results),
        "retrieval_macro": retrieval_macro,
        "retrieval_micro": {
            "precision_at_k": (
                0.0 if total_retrieved == 0 else total_relevant_hits / total_retrieved
            ),
            "recall_at_k": (
                0.0 if total_relevant == 0 else total_relevant_hits / total_relevant
            ),
        },
        "deterministic_macro": deterministic_macro,
        "deepeval_metrics": semantic,
        "deepeval_metric_attempts": total_attempts,
        "deepeval_metric_errors": total_errors,
        "deepeval_error_rate": (
            0.0 if total_attempts == 0 else total_errors / total_attempts
        ),
        "deepeval_case_attempts": len(attempted_cases),
        "deepeval_case_passes": passed_cases,
        "deepeval_case_pass_rate": (
            None if not attempted_cases else passed_cases / len(attempted_cases)
        ),
        "aliases": {
            "hit_rate_at_k": retrieval_macro["hit_at_k"],
            "mrr_at_k": retrieval_macro["reciprocal_rank_at_k"],
            "map_at_k": retrieval_macro["average_precision_at_k"],
            "mean_ndcg_at_k": retrieval_macro["ndcg_at_k"],
        },
    }


def _atomic_text_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def save_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    experiment_id = str(report["experiment_id"])
    json_path = output_dir / f"{experiment_id}.json"
    csv_path = output_dir / f"{experiment_id}.csv"
    json_text = json.dumps(report, indent=2, ensure_ascii=False)
    _atomic_text_write(json_path, json_text)
    _atomic_text_write(output_dir / "latest.json", json_text)

    rows: list[dict[str, Any]] = []
    for result in report["cases"]:
        row: dict[str, Any] = {
            "experiment_id": experiment_id,
            "case_id": result["case_id"],
            "question": result["question"],
            "rag_provider": result["trace"]["provider"],
            "generation_model": result["trace"]["generation_model"],
            "embedding_model": result["trace"]["embedding_model"],
            "top_k": result["trace"]["top_k"],
            "retrieved_chunk_ids": " | ".join(
                result["trace"]["retrieved_chunk_ids"]
            ),
            "answer": result["trace"]["answer"],
            "deepeval_case_passed": result["deepeval_case_passed"],
        }
        row.update(
            {
                f"retrieval_{key}": value
                for key, value in result["retrieval_metrics"].items()
            }
        )
        for key in DETERMINISTIC_RATE_METRICS:
            row[f"deterministic_{key}"] = result["deterministic_metrics"][key]
        for metric_name, outcome in result["deepeval_metrics"].items():
            row[f"deepeval_{metric_name}"] = outcome["value"]
            row[f"deepeval_{metric_name}_threshold"] = outcome["threshold"]
            row[f"deepeval_{metric_name}_passed"] = outcome["passed"]
            row[f"deepeval_{metric_name}_reason"] = outcome["reason"]
            row[f"deepeval_{metric_name}_error"] = outcome["error"]
        rows.append(row)

    fieldnames = sorted({key for row in rows for key in row})
    temporary_csv = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with temporary_csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary_csv.replace(csv_path)
    _atomic_text_write(output_dir / "latest.csv", csv_path.read_text(encoding="utf-8"))
    return json_path, csv_path

