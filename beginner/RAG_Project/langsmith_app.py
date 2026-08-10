"""CLI for LangSmith tracing, datasets, experiments, comparison, and feedback."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rag.config import ConfigurationError, Settings

from langsmith_evaluation.runner import (
    compare_experiments,
    preflight,
    reevaluate_existing,
    run_live,
    sync_dataset,
)
from langsmith_evaluation.settings import LangSmithSettings
from langsmith_evaluation.tracing import LangSmithRAGApplication


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "langsmith_evaluation" / "results"


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _require_confirmation(args: argparse.Namespace, action: str) -> None:
    if not getattr(args, "confirm_hosted", False):
        raise ConfigurationError(
            f"{action} writes to hosted LangSmith. Re-run with --confirm-hosted "
            "after checking the endpoint, project, dataset, payload content, "
            "retention, and expected model cost."
        )


def _command_preflight(args: argparse.Namespace) -> int:
    settings = LangSmithSettings.from_env(PROJECT_ROOT)
    _print(preflight(PROJECT_ROOT, settings, args.hosted))
    return 0


def _command_sync(args: argparse.Namespace) -> int:
    _require_confirmation(args, "Dataset synchronization")
    settings = LangSmithSettings.from_env(PROJECT_ROOT)
    _print(sync_dataset(PROJECT_ROOT, settings))
    return 0


def _command_run(args: argparse.Namespace) -> int:
    settings = LangSmithSettings.from_env(PROJECT_ROOT)
    if args.hosted:
        _require_confirmation(args, "Hosted experiment")
        if args.sync_dataset:
            sync_dataset(PROJECT_ROOT, settings)
    report, json_path, csv_path = run_live(
        project_root=PROJECT_ROOT,
        settings=settings,
        output_dir=args.output_dir,
        rag_provider=args.rag_provider,
        top_k=args.top_k,
        profile=args.metric_profile,
        hosted=args.hosted,
        case_ids=args.case_id,
        experiment_prefix=args.experiment_prefix,
        num_repetitions=args.num_repetitions,
    )
    _print(
        {
            "mode": report["mode"],
            "case_count": report["summary"]["case_count"],
            "experiment_name": report["experiment_name"],
            "experiment_id": report["experiment_id"],
            "experiment_url": report["experiment_url"],
            "mean_feedback_scores": report["summary"]["mean_feedback_scores"],
            "json_report": str(json_path),
            "csv_report": str(csv_path),
            "uploaded": report["upload_results"],
        }
    )
    return 0


def _command_trace(args: argparse.Namespace) -> int:
    _require_confirmation(args, "Tracing")
    settings = LangSmithSettings.from_env(PROJECT_ROOT)
    settings.require_hosted()
    if not settings.tracing_enabled:
        raise ConfigurationError("LANGSMITH_TRACING must be true for trace-one.")
    client = settings.client()
    rag_settings = Settings.from_env(PROJECT_ROOT, args.rag_provider)
    application = LangSmithRAGApplication(
        PROJECT_ROOT,
        rag_settings,
        langsmith_settings=settings,
        langsmith_client=client,
    )
    trace, trace_path = application.ask(args.question, args.top_k)
    client.flush(timeout=30)
    langsmith_run_id = application.langsmith_run_id(trace.run_id)
    run_url = None
    if langsmith_run_id is not None:
        hosted_run = client.read_run(langsmith_run_id)
        run_url = client.get_run_url(run=hosted_run)
    _print(
        {
            "canonical_trace_id": trace.run_id,
            "canonical_trace_path": str(trace_path),
            "langsmith_run_id": langsmith_run_id,
            "langsmith_run_url": run_url,
            "project_name": settings.project_name,
            "retrieved_chunk_ids": [
                item.chunk.chunk_id for item in trace.retrieved
            ],
            "capture_content": settings.capture_content,
        }
    )
    return 0


def _command_compare(args: argparse.Namespace) -> int:
    _require_confirmation(args, "Comparative experiment")
    settings = LangSmithSettings.from_env(PROJECT_ROOT)
    _print(
        compare_experiments(
            experiment_a=args.experiment_a,
            experiment_b=args.experiment_b,
            settings=settings,
            experiment_prefix=args.experiment_prefix,
        )
    )
    return 0


def _command_reevaluate(args: argparse.Namespace) -> int:
    _require_confirmation(args, "Re-evaluation")
    settings = LangSmithSettings.from_env(PROJECT_ROOT)
    results = reevaluate_existing(
        experiment=args.experiment,
        settings=settings,
        profile=args.metric_profile,
    )
    rows = list(results)
    _print(
        {
            "source_experiment": args.experiment,
            "new_experiment_name": getattr(results, "experiment_name", None),
            "new_experiment_url": getattr(results, "url", None),
            "evaluated_row_count": len(rows),
            "target_rerun": False,
        }
    )
    return 0


def _command_feedback(args: argparse.Namespace) -> int:
    _require_confirmation(args, "Feedback creation")
    settings = LangSmithSettings.from_env(PROJECT_ROOT)
    client = settings.client()
    value = client.create_feedback(
        run_id=args.run_id,
        key=args.key,
        score=args.score,
        value=args.value,
        comment=args.comment,
        extend_trace_retention=args.extend_retention,
    )
    _print(
        {
            "feedback_id": str(value.id),
            "run_id": args.run_id,
            "key": args.key,
            "extend_trace_retention": args.extend_retention,
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Add hosted LangSmith tracing and experiments to the existing "
            "payroll-MFA RAG without replacing Ragas or DeepEval."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--hosted", action="store_true")
    preflight_parser.set_defaults(handler=_command_preflight)

    sync_parser = subparsers.add_parser("sync-dataset")
    sync_parser.add_argument("--confirm-hosted", action="store_true")
    sync_parser.set_defaults(handler=_command_sync)

    run_parser = subparsers.add_parser(
        "run", help="Run the real RAG over the governed golden cases."
    )
    run_parser.add_argument(
        "--rag-provider", choices=("ollama", "openai"), default="ollama"
    )
    run_parser.add_argument("--top-k", type=int, default=3)
    run_parser.add_argument("--case-id", action="append")
    run_parser.add_argument(
        "--metric-profile", choices=("core", "full"), default="core"
    )
    run_parser.add_argument("--num-repetitions", type=int, default=1)
    run_parser.add_argument("--hosted", action="store_true")
    run_parser.add_argument("--sync-dataset", action="store_true")
    run_parser.add_argument("--confirm-hosted", action="store_true")
    run_parser.add_argument("--experiment-prefix")
    run_parser.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR
    )
    run_parser.set_defaults(handler=_command_run)

    trace_parser = subparsers.add_parser("trace-one")
    trace_parser.add_argument("question")
    trace_parser.add_argument(
        "--rag-provider", choices=("ollama", "openai"), default="ollama"
    )
    trace_parser.add_argument("--top-k", type=int, default=3)
    trace_parser.add_argument("--confirm-hosted", action="store_true")
    trace_parser.set_defaults(handler=_command_trace)

    compare_parser = subparsers.add_parser(
        "compare", help="Create a hosted pairwise comparative experiment."
    )
    compare_parser.add_argument("experiment_a")
    compare_parser.add_argument("experiment_b")
    compare_parser.add_argument(
        "--experiment-prefix", default="payroll-mfa-pairwise"
    )
    compare_parser.add_argument("--confirm-hosted", action="store_true")
    compare_parser.set_defaults(handler=_command_compare)

    reeval_parser = subparsers.add_parser("reevaluate")
    reeval_parser.add_argument("experiment")
    reeval_parser.add_argument(
        "--metric-profile", choices=("core", "full"), default="core"
    )
    reeval_parser.add_argument("--confirm-hosted", action="store_true")
    reeval_parser.set_defaults(handler=_command_reevaluate)

    feedback_parser = subparsers.add_parser("feedback")
    feedback_parser.add_argument("run_id")
    feedback_parser.add_argument("--key", required=True)
    feedback_parser.add_argument("--score", type=float)
    feedback_parser.add_argument("--value")
    feedback_parser.add_argument("--comment")
    feedback_parser.add_argument("--extend-retention", action="store_true")
    feedback_parser.add_argument("--confirm-hosted", action="store_true")
    feedback_parser.set_defaults(handler=_command_feedback)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.handler(args))
    except (ConfigurationError, FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
