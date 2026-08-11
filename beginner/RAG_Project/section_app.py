"""One CLI for the outcome-driven evaluation-dataset, RAG, and risk section."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from evaluation.judges import JudgeConfigurationError
from evaluation.models import EvaluationDataError
from rag.config import ConfigurationError
from rag.providers import ProviderError

from evaluation_section.build_seed import build
from evaluation_section.dataset import load_seed_dataset, validate_seed_dataset
from evaluation_section.risk import run_risk_suite
from evaluation_section.runner import run_seed_evaluation


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = PROJECT_ROOT / "evaluation_section" / "data" / "eval_seed_v1.jsonl"
DEFAULT_RISK_CASES = PROJECT_ROOT / "evaluation_section" / "data" / "risk_cases.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "evaluation_section" / "results"


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)

    build_cmd = sub.add_parser("build-dataset", help="Rebuild the deterministic 30-row seed.")
    build_cmd.add_argument("--output", type=Path, default=DEFAULT_DATASET)

    validate = sub.add_parser("validate-dataset", help="Validate schema, provenance, slices, and hygiene.")
    validate.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)

    evaluate = sub.add_parser("evaluate-rag", help="Run selected seed cases through the current RAG and evaluators.")
    evaluate.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    evaluate.add_argument("--rag-provider", choices=("ollama", "openai"), default="ollama")
    evaluate.add_argument("--judge-provider", choices=("ollama", "openai"))
    evaluate.add_argument("--top-k", type=int, default=3)
    evaluate.add_argument("--metric-profile", choices=("core", "full"), default="core")
    evaluate.add_argument("--case-id", action="append")
    evaluate.add_argument("--skip-ragas", action="store_true")
    evaluate.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT / "rag")

    risk = sub.add_parser("risk-screen", help="Run safe synthetic direct, indirect, and paired risk cases.")
    risk.add_argument("--cases", type=Path, default=DEFAULT_RISK_CASES)
    risk.add_argument("--rag-provider", choices=("ollama", "openai"), default="ollama")
    risk.add_argument("--top-k", type=int, default=3)
    risk.add_argument("--case-id", action="append")
    risk.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT / "risk")
    risk.add_argument("--confirm-live", action="store_true")
    return root


def main() -> int:
    args = parser().parse_args()
    if args.command == "build-dataset":
        print(json.dumps(build(PROJECT_ROOT, args.output), indent=2, ensure_ascii=False))
        return 0
    if args.command == "validate-dataset":
        result = validate_seed_dataset(
            load_seed_dataset(args.dataset), PROJECT_ROOT / "documents"
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["valid"] else 1
    if args.command == "evaluate-rag":
        report, json_path, csv_path = run_seed_evaluation(
            project_root=PROJECT_ROOT,
            dataset_path=args.dataset,
            output_dir=args.output_dir,
            rag_provider=args.rag_provider,
            judge_provider=args.judge_provider,
            top_k=args.top_k,
            metric_profile=args.metric_profile,
            case_ids=args.case_id,
            skip_ragas=args.skip_ragas,
        )
        print(json.dumps({
            "experiment_id": report["experiment_id"],
            "selected_case_count": report["selected_case_count"],
            "blocking_policy_case_ids": report["blocking_policy_case_ids"],
            "json_report": str(json_path),
            "csv_report": str(csv_path),
        }, indent=2, ensure_ascii=False))
        return 0
    if args.command == "risk-screen":
        if not args.confirm_live:
            raise ValueError("risk-screen calls the configured model; pass --confirm-live deliberately")
        report, path = run_risk_suite(
            project_root=PROJECT_ROOT,
            cases_path=args.cases,
            output_dir=args.output_dir,
            provider=args.rag_provider,
            top_k=args.top_k,
            case_ids=args.case_id,
        )
        print(json.dumps({
            "run_id": report["run_id"],
            "case_count": report["case_count"],
            "screen_failure_case_ids": report["screen_failure_case_ids"],
            "report": str(path),
        }, indent=2, ensure_ascii=False))
        return 0
    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ConfigurationError,
        EvaluationDataError,
        JudgeConfigurationError,
        ProviderError,
        FileNotFoundError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
