"""Command-line entry point for the separate DeepEval evaluation layer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from deepeval_evaluation.judges import (
    DeepEvalConfigurationError,
    DeepEvalJudgeSettings,
    build_judge_bundle,
    run_preflight,
)
from deepeval_evaluation.runner import run_live_experiment, run_trace_experiment
from evaluation.dataset import load_golden_cases
from evaluation.models import EvaluationDataError
from rag.config import ConfigurationError
from rag.providers import ProviderError

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = PROJECT_ROOT / "evaluation" / "data" / "golden_cases.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "deepeval_evaluation" / "results"


def _provider_argument(parser: argparse.ArgumentParser, name: str, help_text: str) -> None:
    parser.add_argument(name, choices=("ollama", "openai"), help=help_text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the payroll-MFA RAG with exact checks and a separate "
            "DeepEval test layer."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_cases = subparsers.add_parser("list-cases", help="Show golden cases.")
    list_cases.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)

    preflight = subparsers.add_parser(
        "preflight", help="Verify DeepEval imports and judge configuration."
    )
    _provider_argument(
        preflight,
        "--judge-provider",
        "Provider used by DeepEval for LLM-as-a-judge metrics.",
    )
    preflight.add_argument(
        "--live",
        action="store_true",
        help="Also make one small structured-output judge call.",
    )

    run = subparsers.add_parser(
        "run", help="Run the RAG for golden questions, then evaluate every trace."
    )
    _provider_argument(run, "--rag-provider", "Provider used by the RAG application.")
    _provider_argument(
        run,
        "--judge-provider",
        "Provider used by DeepEval; defaults to --rag-provider.",
    )
    run.add_argument("--top-k", type=int, default=3)
    run.add_argument("--metric-profile", choices=("core", "full"), default="core")
    run.add_argument("--case-id", action="append", help="Repeat to select cases.")
    run.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    run.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    run.add_argument(
        "--skip-deepeval",
        action="store_true",
        help="Run only exact retrieval, citation, concept, and policy checks.",
    )
    run.add_argument("--show-answers", action="store_true")
    run.add_argument("--show-reasons", action="store_true")
    run.add_argument(
        "--allow-metric-errors",
        action="store_true",
        help="Return success even if one or more DeepEval metric calls fail.",
    )
    run.add_argument(
        "--enforce-thresholds",
        action="store_true",
        help="Return exit code 1 when any DeepEval case fails a threshold.",
    )

    trace = subparsers.add_parser(
        "trace", help="Evaluate one previously saved canonical RAG trace."
    )
    trace.add_argument("--trace", type=Path, required=True)
    trace.add_argument("--case-id", required=True)
    _provider_argument(
        trace,
        "--judge-provider",
        "Provider used by DeepEval; defaults to the trace provider.",
    )
    trace.add_argument("--metric-profile", choices=("core", "full"), default="core")
    trace.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    trace.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    trace.add_argument("--skip-deepeval", action="store_true")
    trace.add_argument("--allow-question-mismatch", action="store_true")
    trace.add_argument("--show-answers", action="store_true")
    trace.add_argument("--show-reasons", action="store_true")
    trace.add_argument("--allow-metric-errors", action="store_true")
    trace.add_argument("--enforce-thresholds", action="store_true")
    return parser


def _print_report(
    report: dict[str, object],
    json_path: Path,
    csv_path: Path,
    show_answers: bool,
    show_reasons: bool,
) -> None:
    print(f"\nExperiment: {report['experiment_id']}")
    print("Framework: DeepEval (separate from Ragas)")
    print("\nPer-case results")
    for result in report["cases"]:  # type: ignore[index]
        retrieval = result["retrieval_metrics"]
        deterministic = result["deterministic_metrics"]
        print(
            f"- {result['case_id']} | P={retrieval['precision_at_k']:.3f} "
            f"R={retrieval['recall_at_k']:.3f} Hit={retrieval['hit_at_k']:.0f} "
            f"RR={retrieval['reciprocal_rank_at_k']:.3f} "
            f"AP={retrieval['average_precision_at_k']:.3f} "
            f"nDCG={retrieval['ndcg_at_k']:.3f} "
            f"Citation-valid={deterministic['citation_validity']:.3f}"
        )
        semantic = result["deepeval_metrics"]
        if semantic:
            for name, outcome in semantic.items():
                if outcome["error"] is not None:
                    print(f"  DeepEval {name}: ERROR - {outcome['error']}")
                else:
                    status = "PASS" if outcome["passed"] else "FAIL"
                    print(
                        f"  DeepEval {name}: {outcome['value']:.3f} / "
                        f"{outcome['threshold']:.3f} {status}"
                    )
                    if show_reasons and outcome["reason"]:
                        print(f"    Reason: {outcome['reason']}")
        if show_answers:
            print(f"  Answer: {result['trace']['answer']}")

    summary = report["summary"]  # type: ignore[index]
    aliases = summary["aliases"]
    print("\nAggregate exact retrieval")
    print(
        f"HitRate={aliases['hit_rate_at_k']:.3f} "
        f"MRR={aliases['mrr_at_k']:.3f} MAP={aliases['map_at_k']:.3f} "
        f"mean-nDCG={aliases['mean_ndcg_at_k']:.3f} "
        f"micro-P={summary['retrieval_micro']['precision_at_k']:.3f} "
        f"micro-R={summary['retrieval_micro']['recall_at_k']:.3f}"
    )
    if summary["deepeval_metrics"]:
        print("\nAggregate DeepEval")
        for name, aggregate in summary["deepeval_metrics"].items():
            mean = aggregate["mean_score"]
            mean_text = "n/a" if mean is None else f"{mean:.3f}"
            pass_rate = aggregate["pass_rate"]
            pass_text = "n/a" if pass_rate is None else f"{pass_rate:.3f}"
            print(
                f"- {name}: mean={mean_text} pass-rate={pass_text} "
                f"errors={aggregate['errors']}"
            )
    print(f"\nJSON report: {json_path}")
    print(f"CSV report:  {csv_path}")
    print(
        "Thresholds are diagnostic defaults; calibrate against human labels before "
        "using --enforce-thresholds in a release workflow."
    )


def _report_exit_code(
    report: dict[str, object],
    allow_metric_errors: bool,
    enforce_thresholds: bool,
) -> int:
    summary = report["summary"]  # type: ignore[index]
    if summary["deepeval_metric_errors"] and not allow_metric_errors:
        return 3
    if enforce_thresholds:
        for result in report["cases"]:  # type: ignore[index]
            if result["deepeval_metrics"] and result["deepeval_case_passed"] is not True:
                return 1
    return 0


def run_command(arguments: argparse.Namespace) -> int:
    if arguments.command == "list-cases":
        for case in load_golden_cases(arguments.dataset):
            print(f"{case.case_id} | {', '.join(case.tags)} | {case.question}")
        return 0

    if arguments.command == "preflight":
        settings = DeepEvalJudgeSettings.from_env(
            PROJECT_ROOT, arguments.judge_provider
        )
        result = run_preflight(build_judge_bundle(settings), live=arguments.live)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if arguments.command == "run":
        report, json_path, csv_path = run_live_experiment(
            project_root=PROJECT_ROOT,
            dataset_path=arguments.dataset,
            output_dir=arguments.output_dir,
            rag_provider=arguments.rag_provider,
            judge_provider=arguments.judge_provider,
            top_k=arguments.top_k,
            metric_profile=arguments.metric_profile,
            case_ids=arguments.case_id,
            skip_deepeval=arguments.skip_deepeval,
        )
    elif arguments.command == "trace":
        report, json_path, csv_path = run_trace_experiment(
            project_root=PROJECT_ROOT,
            dataset_path=arguments.dataset,
            output_dir=arguments.output_dir,
            trace_path=arguments.trace,
            case_id=arguments.case_id,
            judge_provider=arguments.judge_provider,
            metric_profile=arguments.metric_profile,
            skip_deepeval=arguments.skip_deepeval,
            allow_question_mismatch=arguments.allow_question_mismatch,
        )
    else:
        raise ValueError(f"Unknown command: {arguments.command}")

    _print_report(
        report,
        json_path,
        csv_path,
        arguments.show_answers,
        arguments.show_reasons,
    )
    return _report_exit_code(
        report, arguments.allow_metric_errors, arguments.enforce_thresholds
    )


def main() -> int:
    try:
        return run_command(build_parser().parse_args())
    except (
        ConfigurationError,
        DeepEvalConfigurationError,
        EvaluationDataError,
        ProviderError,
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

