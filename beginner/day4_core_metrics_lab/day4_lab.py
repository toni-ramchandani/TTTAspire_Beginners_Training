"""Day 4: theory-first DeepEval lab over 20 frozen payroll-MFA outputs.

The script evaluates the response that already exists. It does not regenerate answers.
Use DeepEval CLI settings to choose OpenAI or Gemini; no provider is hard-coded.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Optional privacy setting. Remove this line if your organization manages telemetry centrally.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")

try:
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, GEval
    from deepeval.test_case import LLMTestCase, SingleTurnParams
except ImportError as exc:  # pragma: no cover - environment dependent
    raise SystemExit(
        "DeepEval is not installed. Run: python -m pip install -r requirements.txt"
    ) from exc


@dataclass(frozen=True)
class Case:
    id: str
    pattern: str
    question: str
    actual_output: str
    retrieval_context: list[str]
    expected_output: str
    review_focus: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score frozen Day 4 outputs with DeepEval Answer Relevancy and Faithfulness."
    )
    parser.add_argument("--cases", default="day4_cases.json", help="Path to the JSON case file.")
    parser.add_argument("--case", action="append", dest="case_ids", help="Run one case ID; repeatable.")
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N selected cases.")
    parser.add_argument("--threshold", type=float, default=0.70, help="Classroom threshold, default 0.70.")
    parser.add_argument(
        "--with-correctness",
        action="store_true",
        help="Also run optional reference-correctness G-Eval.",
    )
    parser.add_argument(
        "--penalize-ambiguous",
        action="store_true",
        help="Make Faithfulness treat idk/ambiguous verdicts as failures.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Ask metrics to retain/print intermediate evaluation details where supported.",
    )
    parser.add_argument("--output-dir", default="results", help="Directory for JSON and CSV results.")
    return parser.parse_args()


def load_cases(path: Path) -> list[Case]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Case file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc

    cases: list[Case] = []
    for item in raw:
        cases.append(Case(**item))
    if len(cases) != 20:
        raise SystemExit(f"Expected exactly 20 cases, found {len(cases)} in {path}")
    if len({case.id for case in cases}) != len(cases):
        raise SystemExit("Duplicate case IDs found")
    return cases


def select_cases(cases: list[Case], case_ids: list[str] | None, limit: int | None) -> list[Case]:
    selected = cases
    if case_ids:
        wanted = set(case_ids)
        selected = [case for case in cases if case.id in wanted]
        missing = wanted - {case.id for case in selected}
        if missing:
            raise SystemExit(f"Unknown case IDs: {', '.join(sorted(missing))}")
    if limit is not None:
        if limit < 1:
            raise SystemExit("--limit must be at least 1")
        selected = selected[:limit]
    return selected


def correctness_metric(threshold: float, verbose: bool) -> GEval:
    # Explicit steps avoid a separate criteria-to-steps generation call and reduce one
    # source of run-to-run variation. Only ACTUAL_OUTPUT and EXPECTED_OUTPUT are supplied,
    # preserving correctness as a separate evidence relationship from faithfulness.
    return GEval(
        name="Reference Correctness",
        evaluation_steps=[
            "Compare the actual output only with the expected output.",
            "Identify contradictions, unsafe instructions, and claims that the expected output forbids.",
            "Identify required decisions or steps from the expected output that the actual output omits.",
            "Do not reward a claim merely because it appears in retrieval context; retrieval context is not an evaluation parameter for this metric.",
            "Assign the highest score only when the governed meaning is correct and materially complete."
        ],
        evaluation_params=[
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.EXPECTED_OUTPUT,
        ],
        threshold=threshold,
        async_mode=False,
        verbose_mode=verbose,
    )


def build_metrics(
    threshold: float,
    with_correctness: bool,
    penalize_ambiguous: bool,
    verbose: bool,
) -> list[Any]:
    metrics: list[Any] = [
        AnswerRelevancyMetric(
            threshold=threshold,
            include_reason=True,
            async_mode=False,
            verbose_mode=verbose,
        ),
        FaithfulnessMetric(
            threshold=threshold,
            include_reason=True,
            async_mode=False,
            verbose_mode=verbose,
            penalize_ambiguous_claims=penalize_ambiguous,
        ),
    ]
    if with_correctness:
        metrics.append(correctness_metric(threshold, verbose))
    return metrics


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return jsonable(value.dict())
    return str(value)


def metric_record(metric: Any, error: str | None = None) -> dict[str, Any]:
    score = getattr(metric, "score", None)
    threshold = getattr(metric, "threshold", None)
    success = getattr(metric, "success", None)
    if success is None and score is not None and threshold is not None:
        success = score >= threshold
    record: dict[str, Any] = {
        "metric": getattr(metric, "__name__", metric.__class__.__name__),
        "model": getattr(metric, "evaluation_model", None),
        "score": score,
        "threshold": threshold,
        "success": success,
        "reason": getattr(metric, "reason", None),
        "error": error,
    }
    # Preserve evidence that explains the score. These are populated after measure().
    for name in ("statements", "verdicts", "truths", "claims", "evaluation_steps", "verbose_logs"):
        if hasattr(metric, name):
            record[name] = jsonable(getattr(metric, name))
    return record


def evaluate_case(case: Case, args: argparse.Namespace) -> dict[str, Any]:
    test_case = LLMTestCase(
        input=case.question,
        actual_output=case.actual_output,
        retrieval_context=case.retrieval_context,
        expected_output=case.expected_output,
    )
    metric_results: list[dict[str, Any]] = []
    # Fresh metric instances prevent mutable score/reason/evidence from leaking across cases.
    for metric in build_metrics(
        args.threshold,
        args.with_correctness,
        args.penalize_ambiguous,
        args.verbose,
    ):
        try:
            metric.measure(test_case)
            metric_results.append(metric_record(metric))
        except Exception as exc:  # preserve evaluator failure separately from quality failure
            metric_results.append(metric_record(metric, error=f"{type(exc).__name__}: {exc}"))

    return {
        "id": case.id,
        "pattern": case.pattern,
        "question": case.question,
        "actual_output": case.actual_output,
        "retrieval_context": case.retrieval_context,
        "expected_output": case.expected_output,
        "review_focus": case.review_focus,
        "metrics": metric_results,
    }


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    fieldnames = [
        "case_id", "pattern", "metric", "model", "score", "threshold", "success", "reason", "error", "review_focus"
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in rows:
            for metric in result["metrics"]:
                writer.writerow(
                    {
                        "case_id": result["id"],
                        "pattern": result["pattern"],
                        "metric": metric["metric"],
                        "model": metric["model"],
                        "score": metric["score"],
                        "threshold": metric["threshold"],
                        "success": metric["success"],
                        "reason": metric["reason"],
                        "error": metric["error"],
                        "review_focus": result["review_focus"],
                    }
                )


def print_summary(results: list[dict[str, Any]]) -> None:
    print("\nDAY 4 RESULT SUMMARY")
    print("=" * 88)
    for result in results:
        print(f"{result['id']} | {result['pattern']}")
        for metric in result["metrics"]:
            score = "ERROR" if metric["score"] is None else f"{metric['score']:.3f}"
            print(f"  {metric['metric']:<28} score={score:<7} pass={metric['success']}")
            if metric["error"]:
                print(f"    evaluator error: {metric['error']}")
            elif metric["reason"]:
                print(f"    reason: {metric['reason']}")
        print(f"  inspect: {result['review_focus']}")
        print()


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    cases_path = Path(args.cases)
    if not cases_path.is_absolute():
        cases_path = script_dir / cases_path
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = script_dir / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = select_cases(load_cases(cases_path), args.case_ids, args.limit)
    results = [evaluate_case(case, args) for case in cases]

    run_meta = {
        "deepeval_version_target": "4.1.5",
        "threshold": args.threshold,
        "with_correctness": args.with_correctness,
        "penalize_ambiguous_claims": args.penalize_ambiguous,
        "case_count": len(results),
        "results": results,
    }
    json_path = output_dir / "day4_results.json"
    csv_path = output_dir / "day4_results.csv"
    write_json(json_path, run_meta)
    write_csv(csv_path, results)
    print_summary(results)
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
