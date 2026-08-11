"""CLI for continuous RAG evaluation: trace, evaluate, review, and promote."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from pathlib import Path

from continuous_evaluation.hosted_setup import create_human_review_queue
from continuous_evaluation.promotion import promote_reviewed_trace
from continuous_evaluation.runner import evaluate_fixture, run_live_traffic
from continuous_evaluation.traffic import load_traffic


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_TRAFFIC = (
    PROJECT_ROOT / "continuous_evaluation" / "data" / "production_like_traffic.jsonl"
)
DEFAULT_FIXTURE = (
    PROJECT_ROOT
    / "continuous_evaluation"
    / "fixtures"
    / "synthetic_failure_trace.json"
)
DEFAULT_RESULTS = PROJECT_ROOT / "continuous_evaluation" / "results"


def _print(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _preflight(args: argparse.Namespace) -> int:
    traffic = load_traffic(args.traffic)
    dependencies = {}
    for name in ("numpy", "langsmith", "deepeval", "ollama"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = "not-installed"
    _print(
        {
            "status": "ok",
            "traffic_count": len(traffic),
            "fixture_exists": args.fixture.exists(),
            "approved_case_count": len(
                json.loads(
                    (
                        PROJECT_ROOT
                        / "evaluation"
                        / "data"
                        / "golden_cases.json"
                    ).read_text(encoding="utf-8")
                )
            ),
            "dependencies": dependencies,
            "boundary": (
                "Deterministic fixture evaluation uses only the standard library. "
                "Live RAG, DeepEval, and LangSmith require their pinned dependencies."
            ),
        }
    )
    return 0


def _fixture(args: argparse.Namespace) -> int:
    result, path = evaluate_fixture(
        project_root=PROJECT_ROOT,
        fixture_path=args.input,
        output_dir=args.output_dir,
        semantic=args.semantic,
        judge_provider=args.judge_provider,
    )
    _print(
        {
            "request_id": result["request_id"],
            "bounded_outcome": result["evaluation"]["bounded_outcome"],
            "required_context_recall": result["evaluation"][
                "approved_canary_metrics"
            ]["required_context_recall"]["value"],
            "unsafe_effect_observed": result["evaluation"][
                "online_deterministic"
            ]["unsafe_effect_observed"]["value"],
            "semantic_error": result.get("semantic_error"),
            "report": str(path),
        }
    )
    return 0


def _run(args: argparse.Namespace) -> int:
    if (args.hosted or args.publish_feedback) and not args.confirm_hosted:
        raise ValueError(
            "Hosted tracing and feedback create external data. Pass --confirm-hosted "
            "after reviewing endpoint, project, capture, retention, and cost settings."
        )
    report, json_path, csv_path = run_live_traffic(
        project_root=PROJECT_ROOT,
        traffic_path=args.traffic,
        output_dir=args.output_dir,
        rag_provider=args.rag_provider,
        judge_provider=args.judge_provider,
        top_k=args.top_k,
        environment=args.environment,
        release_id=args.release_id,
        prompt_version=args.prompt_version,
        semantic=args.semantic,
        semantic_sample_rate=args.semantic_sample_rate,
        hosted=args.hosted,
        publish_feedback=args.publish_feedback,
    )
    _print(
        {
            "run_id": report["run_id"],
            "mode": report["mode"],
            "result_count": report["result_count"],
            "blocking_request_ids": report["blocking_request_ids"],
            "json_report": str(json_path),
            "csv_report": str(csv_path),
        }
    )
    return 0


def _promote(args: argparse.Namespace) -> int:
    value = promote_reviewed_trace(
        envelope_path=args.envelope,
        review_path=args.review,
        output_path=args.output,
        case_id=args.case_id,
    )
    _print(
        {
            "case_id": value["case_id"],
            "review_status": value["review_status"],
            "output": str(args.output),
            "boundary": value["promotion_boundary"],
        }
    )
    return 0


def _setup_review_queue(args: argparse.Namespace) -> int:
    if not args.confirm_hosted:
        raise ValueError(
            "This creates hosted feedback schemas and an annotation queue. "
            "Pass --confirm-hosted deliberately."
        )
    from langsmith_evaluation.settings import LangSmithSettings

    settings = LangSmithSettings.from_env(PROJECT_ROOT)
    _print(create_human_review_queue(settings.client()))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    preflight = sub.add_parser("preflight")
    preflight.add_argument("--traffic", type=Path, default=DEFAULT_TRAFFIC)
    preflight.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    preflight.set_defaults(handler=_preflight)

    fixture = sub.add_parser(
        "fixture", help="Evaluate the guaranteed failing trace without calling the RAG."
    )
    fixture.add_argument("--input", type=Path, default=DEFAULT_FIXTURE)
    fixture.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS)
    fixture.add_argument("--semantic", action="store_true")
    fixture.add_argument(
        "--judge-provider", choices=("ollama", "openai"), default="ollama"
    )
    fixture.set_defaults(handler=_fixture)

    run = sub.add_parser("run", help="Run the production-like traffic through the RAG.")
    run.add_argument("--traffic", type=Path, default=DEFAULT_TRAFFIC)
    run.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS)
    run.add_argument("--rag-provider", choices=("ollama", "openai"), default="ollama")
    run.add_argument("--judge-provider", choices=("ollama", "openai"), default="ollama")
    run.add_argument("--top-k", type=int, default=3)
    run.add_argument("--environment", default="workshop")
    run.add_argument("--release-id", default="candidate-v1")
    run.add_argument("--prompt-version", default="payroll-mfa-system-v1")
    run.add_argument("--semantic", action="store_true")
    run.add_argument("--semantic-sample-rate", type=float, default=1.0)
    run.add_argument("--hosted", action="store_true")
    run.add_argument("--publish-feedback", action="store_true")
    run.add_argument("--confirm-hosted", action="store_true")
    run.set_defaults(handler=_run)

    promote = sub.add_parser(
        "promote", help="Create an OBS-* candidate from a completed human review."
    )
    promote.add_argument("--envelope", type=Path, required=True)
    promote.add_argument("--review", type=Path, required=True)
    promote.add_argument("--case-id", default="OBS-031")
    promote.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RESULTS / "observed_candidates.jsonl",
    )
    promote.set_defaults(handler=_promote)

    setup = sub.add_parser("setup-review-queue")
    setup.add_argument("--confirm-hosted", action="store_true")
    setup.set_defaults(handler=_setup_review_queue)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return int(args.handler(args))
    except (FileNotFoundError, ImportError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

