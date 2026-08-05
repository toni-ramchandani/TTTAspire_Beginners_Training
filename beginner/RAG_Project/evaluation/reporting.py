"""Experiment aggregation, CSV/JSON persistence, and optional release gates."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

from .deterministic_metrics import DETERMINISTIC_RATE_METRICS
from .retrieval_metrics import RETRIEVAL_RATE_METRICS


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

    semantic_values: dict[str, list[float]] = defaultdict(list)
    semantic_errors = 0
    semantic_attempts = 0
    for result in case_results:
        for metric_name, outcome in result["ragas_metrics"].items():
            semantic_attempts += 1
            if outcome["error"] is not None:
                semantic_errors += 1
            elif outcome["value"] is not None:
                semantic_values[metric_name].append(float(outcome["value"]))
    ragas_macro = {
        metric: _mean(values) for metric, values in sorted(semantic_values.items())
    }

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
    micro_precision = 0.0 if total_retrieved == 0 else total_relevant_hits / total_retrieved
    micro_recall = 0.0 if total_relevant == 0 else total_relevant_hits / total_relevant

    return {
        "case_count": len(case_results),
        "retrieval_macro": retrieval_macro,
        "retrieval_micro": {
            "precision_at_k": micro_precision,
            "recall_at_k": micro_recall,
        },
        "deterministic_macro": deterministic_macro,
        "ragas_macro": ragas_macro,
        "ragas_metric_attempts": semantic_attempts,
        "ragas_metric_errors": semantic_errors,
        "ragas_error_rate": (
            0.0 if semantic_attempts == 0 else semantic_errors / semantic_attempts
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
        }
        row.update(
            {
                f"retrieval_{key}": value
                for key, value in result["retrieval_metrics"].items()
            }
        )
        for key in DETERMINISTIC_RATE_METRICS:
            row[f"deterministic_{key}"] = result["deterministic_metrics"][key]
        for metric_name, outcome in result["ragas_metrics"].items():
            row[f"ragas_{metric_name}"] = outcome["value"]
            row[f"ragas_{metric_name}_error"] = outcome["error"]
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


def _resolve_path(value: dict[str, Any], dotted_path: str) -> Any:
    current: Any = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(dotted_path)
        current = current[part]
    return current


def apply_gates(report: dict[str, Any], gates_path: Path | None) -> dict[str, Any]:
    if gates_path is None:
        return {"enabled": False, "passed": True, "failures": []}
    configuration = json.loads(gates_path.read_text(encoding="utf-8"))
    if not isinstance(configuration, dict):
        raise ValueError("Gate configuration must be a JSON object.")
    if not configuration.get("enabled", False):
        return {"enabled": False, "passed": True, "failures": []}

    failures: list[str] = []
    minimum_summary = configuration.get("minimum_summary", {})
    minimum_case = configuration.get("minimum_case", {})
    if not isinstance(minimum_summary, dict) or not isinstance(minimum_case, dict):
        raise ValueError("minimum_summary and minimum_case must be JSON objects.")

    for path, threshold in minimum_summary.items():
        actual = _resolve_path(report, path)
        if actual is None or float(actual) < float(threshold):
            failures.append(f"{path}={actual!r} is below {threshold}")
    for result in report["cases"]:
        for path, threshold in minimum_case.items():
            actual = _resolve_path(result, path)
            if actual is None or float(actual) < float(threshold):
                failures.append(
                    f"{result['case_id']} {path}={actual!r} is below {threshold}"
                )

    maximum_error_rate = configuration.get("maximum_ragas_error_rate")
    if maximum_error_rate is not None:
        actual_error_rate = float(report["summary"]["ragas_error_rate"])
        if actual_error_rate > float(maximum_error_rate):
            failures.append(
                f"summary.ragas_error_rate={actual_error_rate} exceeds "
                f"{maximum_error_rate}"
            )
    return {"enabled": True, "passed": not failures, "failures": failures}
