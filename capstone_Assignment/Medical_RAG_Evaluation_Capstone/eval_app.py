"""Command-line entry point for deterministic and Ragas evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evaluation.dataset import load_golden_cases
from evaluation.judges import (
    JudgeConfigurationError,
    JudgeSettings,
    build_judge_bundle,
    run_preflight,
)
from evaluation.models import EvaluationDataError
from evaluation.runner import run_live_experiment, run_trace_experiment
from rag.config import ConfigurationError
from rag.providers import ProviderError

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = PROJECT_ROOT / "evaluation" / "data" / "golden_cases.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "evaluation" / "results"


def _provider_argument(parser: argparse.ArgumentParser, name: str, help_text: str) -> None:
    parser.add_argument(name, choices=("ollama", "openai"), help=help_text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate the medical patient-education RAG with deterministic IR checks and Ragas."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_cases = subparsers.add_parser("list-cases", help="Show golden cases.")
    list_cases.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)

    preflight = subparsers.add_parser(
        "preflight", help="Verify Ragas imports and evaluator-provider configuration."
    )
    _provider_argument(
        preflight,
        "--judge-provider",
        "Provider used by Ragas for semantic scoring.",
    )
    preflight.add_argument(
        "--live",
        action="store_true",
        help="Also make one embedding call and one structured-output call.",
    )

    run = subparsers.add_parser(
        "run", help="Run the RAG for golden questions and evaluate every new trace."
    )
    _provider_argument(run, "--rag-provider", "Provider used by the RAG application.")
    _provider_argument(
        run,
        "--judge-provider",
        "Provider used by Ragas; defaults to --rag-provider.",
    )
    run.add_argument("--top-k", type=int, default=3)
    run.add_argument(
        "--metric-profile", choices=("core", "full"), default="core"
    )
    run.add_argument("--case-id", action="append", help="Repeat to select cases.")
    run.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    run.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    run.add_argument(
        "--skip-ragas",
        action="store_true",
        help="Run only exact retrieval, citation, and policy checks.",
    )
    run.add_argument("--gates", type=Path, help="Optional enabled gate JSON file.")
    run.add_argument("--show-answers", action="store_true")
    run.add_argument(
        "--allow-metric-errors",
        action="store_true",
        help="Return success even if one or more Ragas metric calls fail.",
    )

    trace = subparsers.add_parser(
        "trace", help="Evaluate one previously saved canonical RAG trace."
    )
    trace.add_argument("--trace", type=Path, required=True)
    trace.add_argument("--case-id", required=True)
    _provider_argument(
        trace,
        "--judge-provider",
        "Provider used by Ragas; defaults to the provider recorded in the trace.",
    )
    trace.add_argument(
        "--metric-profile", choices=("core", "full"), default="core"
    )
    trace.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    trace.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    trace.add_argument("--skip-ragas", action="store_true")
    trace.add_argument("--allow-question-mismatch", action="store_true")
    trace.add_argument("--gates", type=Path)
    trace.add_argument("--show-answers", action="store_true")
    trace.add_argument("--allow-metric-errors", action="store_true")
    return parser


def _print_report(
    report: dict[str, object], json_path: Path, csv_path: Path, show_answers: bool
) -> None:
    print(f"\nExperiment: {report['experiment_id']}")
    print("\nPer-case results")
    for result in report["cases"]:  # type: ignore[index]
        retrieval = result["retrieval_metrics"]
        deterministic = result["deterministic_metrics"]
        semantic = result["ragas_metrics"]
        print(
            f"- {result['case_id']} | P={retrieval['precision_at_k']:.3f} "
            f"R={retrieval['recall_at_k']:.3f} Hit={retrieval['hit_at_k']:.0f} "
            f"RR={retrieval['reciprocal_rank_at_k']:.3f} "
            f"AP={retrieval['average_precision_at_k']:.3f} "
            f"nDCG={retrieval['ndcg_at_k']:.3f} "
            f"Citation-valid={deterministic['citation_validity']:.3f}"
        )
        if semantic:
            scores = " ".join(
                f"{name}={outcome['value']:.3f}"
                if outcome["value"] is not None
                else f"{name}=ERROR"
                for name, outcome in semantic.items()
            )
            print(f"  Ragas: {scores}")
        if show_answers:
            print(f"  Answer: {result['trace']['answer']}")

    summary = report["summary"]  # type: ignore[index]
    aliases = summary["aliases"]
    print("\nAggregate retrieval")
    print(
        f"HitRate={aliases['hit_rate_at_k']:.3f} "
        f"MRR={aliases['mrr_at_k']:.3f} MAP={aliases['map_at_k']:.3f} "
        f"mean-nDCG={aliases['mean_ndcg_at_k']:.3f} "
        f"micro-P={summary['retrieval_micro']['precision_at_k']:.3f} "
        f"micro-R={summary['retrieval_micro']['recall_at_k']:.3f}"
    )
    if summary["ragas_macro"]:
        print("\nAggregate Ragas")
        print(
            " ".join(
                f"{name}={value:.3f}"
                for name, value in summary["ragas_macro"].items()
                if value is not None
            )
        )
    print(f"\nJSON report: {json_path}")
    print(f"CSV report:  {csv_path}")
    gates = report["gates"]  # type: ignore[index]
    if gates["enabled"]:
        print(f"Gates: {'PASS' if gates['passed'] else 'FAIL'}")
        for failure in gates["failures"]:
            print(f"  - {failure}")


def _report_exit_code(report: dict[str, object], allow_metric_errors: bool) -> int:
    gates = report["gates"]  # type: ignore[index]
    if gates["enabled"] and not gates["passed"]:
        return 1
    summary = report["summary"]  # type: ignore[index]
    if summary["ragas_metric_errors"] and not allow_metric_errors:
        return 3
    return 0


def run_command(arguments: argparse.Namespace) -> int:
    if arguments.command == "list-cases":
        for case in load_golden_cases(arguments.dataset):
            print(f"{case.case_id} | {', '.join(case.tags)} | {case.question}")
        return 0

    if arguments.command == "preflight":
        settings = JudgeSettings.from_env(PROJECT_ROOT, arguments.judge_provider)
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
            skip_ragas=arguments.skip_ragas,
            gates_path=arguments.gates,
        )
        _print_report(report, json_path, csv_path, arguments.show_answers)
        return _report_exit_code(report, arguments.allow_metric_errors)

    if arguments.command == "trace":
        report, json_path, csv_path = run_trace_experiment(
            project_root=PROJECT_ROOT,
            dataset_path=arguments.dataset,
            output_dir=arguments.output_dir,
            trace_path=arguments.trace,
            case_id=arguments.case_id,
            judge_provider=arguments.judge_provider,
            metric_profile=arguments.metric_profile,
            skip_ragas=arguments.skip_ragas,
            allow_question_mismatch=arguments.allow_question_mismatch,
            gates_path=arguments.gates,
        )
        _print_report(report, json_path, csv_path, arguments.show_answers)
        return _report_exit_code(report, arguments.allow_metric_errors)

    raise ValueError(f"Unknown command: {arguments.command}")


def main() -> int:
    try:
        return run_command(build_parser().parse_args())
    except (
        ConfigurationError,
        EvaluationDataError,
        JudgeConfigurationError,
        ProviderError,
        FileNotFoundError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
