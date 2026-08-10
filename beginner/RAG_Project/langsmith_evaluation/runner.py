"""Run LangSmith tracing and experiments over the existing RAG application."""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
from typing import Any, Iterable

from langsmith import evaluate

from evaluation.dataset import load_golden_cases, validate_cases_against_corpus
from rag.config import Settings

from .dataset import (
    GOLDEN_DATASET_VERSION,
    hosted_example_payloads,
    load_golden_examples,
)
from .evaluators import (
    build_evaluators,
    experiment_summary,
    pairwise_evidence_preference,
)
from .reporting import build_report, normalize_rows, save_report
from .settings import LANGSMITH_SDK_VERSION, LangSmithSettings
from .tracing import LangSmithRAGApplication


def dependency_versions() -> dict[str, str]:
    names = ("langsmith", "ragas", "deepeval", "openai", "numpy")
    values: dict[str, str] = {}
    for name in names:
        try:
            values[name] = version(name)
        except Exception:
            values[name] = "not-installed"
    return values


def preflight(
    project_root: Path, settings: LangSmithSettings, hosted: bool
) -> dict[str, Any]:
    """Validate local artifacts and optionally authenticate with LangSmith."""

    versions = dependency_versions()
    if versions["langsmith"] != LANGSMITH_SDK_VERSION:
        raise RuntimeError(
            f"Expected langsmith {LANGSMITH_SDK_VERSION}; found "
            f"{versions['langsmith']}. Install requirements-langsmith.txt."
        )
    cases = load_golden_cases(
        project_root / "evaluation" / "data" / "golden_cases.json"
    )
    validate_cases_against_corpus(cases, project_root / "documents")
    hosted_access = "not-requested"
    visible_dataset_count = None
    if hosted:
        client = settings.client()
        visible_dataset_count = sum(1 for _ in client.list_datasets(limit=10))
        hosted_access = "authenticated"
    return {
        "status": "ok",
        "hosted_access": hosted_access,
        "visible_dataset_count_capped_at": visible_dataset_count,
        "golden_case_count": len(cases),
        "golden_dataset_version": GOLDEN_DATASET_VERSION,
        "project_name": settings.project_name,
        "dataset_name": settings.dataset_name,
        "endpoint": settings.endpoint,
        "workspace_id_configured": bool(settings.workspace_id),
        "tracing_enabled": settings.tracing_enabled,
        "capture_content": settings.capture_content,
        "dependency_versions": versions,
    }


def sync_dataset(project_root: Path, settings: LangSmithSettings) -> dict[str, Any]:
    """Create or update the hosted dataset from the eight governed examples."""

    client = settings.client()
    if client.has_dataset(dataset_name=settings.dataset_name):
        dataset = client.read_dataset(dataset_name=settings.dataset_name)
        created = False
    else:
        dataset = client.create_dataset(
            dataset_name=settings.dataset_name,
            description=(
                "Eight governed payroll-MFA RAG evaluation cases. Inputs, "
                "references, exact required chunk IDs, required concepts, and "
                "forbidden claims come from evaluation/data/golden_cases.json."
            ),
            metadata={
                "project": "payroll-mfa-rag",
                "dataset_version": GOLDEN_DATASET_VERSION,
                "synthetic": True,
            },
        )
        created = True
    payloads = hosted_example_payloads(project_root)
    response = client.create_examples(dataset_id=dataset.id, examples=payloads)
    return {
        "dataset_id": str(dataset.id),
        "dataset_name": dataset.name,
        "dataset_version": GOLDEN_DATASET_VERSION,
        "created": created,
        "submitted_example_count": len(payloads),
        "upsert_response": str(response),
    }


def _experiment_details(results: Any) -> tuple[str | None, str | None, str | None]:
    """Read public result properties without assuming hosted or local mode."""

    values: list[str | None] = []
    for attribute in ("experiment_name", "experiment_id", "url"):
        try:
            value = getattr(results, attribute, None)
        except Exception:
            value = None
        values.append(str(value) if value else None)
    return values[0], values[1], values[2]


def _live_target(application: LangSmithRAGApplication, top_k: int):
    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        trace, trace_path = application.ask(str(inputs["question"]), top_k)
        value = trace.to_dict()
        return {
            "case_id": inputs.get("case_id"),
            "answer": value["answer"],
            "retrieved_chunk_ids": value["retrieved_chunk_ids"],
            "retrieved_contexts": value["retrieved_contexts"],
            "retrieval_scores": value["retrieval_scores"],
            "provider": value["provider"],
            "embedding_model": value["embedding_model"],
            "generation_model": value["generation_model"],
            "retrieval_latency_ms": value["retrieval_latency_ms"],
            "generation_latency_ms": value["generation_latency_ms"],
            "total_latency_ms": value["total_latency_ms"],
            "canonical_trace_id": value["run_id"],
            "canonical_trace_path": str(trace_path),
            "langsmith_rag_run_id": application.langsmith_run_id(value["run_id"]),
        }

    return target


def run_live(
    *,
    project_root: Path,
    settings: LangSmithSettings,
    output_dir: Path,
    rag_provider: str,
    top_k: int,
    profile: str,
    hosted: bool,
    case_ids: Iterable[str] | None = None,
    experiment_prefix: str | None = None,
    num_repetitions: int = 1,
) -> tuple[dict[str, Any], Path, Path]:
    """Run the real RAG over the golden cases locally or in hosted LangSmith."""

    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    if num_repetitions < 1:
        raise ValueError("num_repetitions must be at least 1.")
    rag_settings = Settings.from_env(project_root, rag_provider)
    client = settings.client() if hosted else None
    application = LangSmithRAGApplication(
        project_root,
        rag_settings,
        langsmith_settings=settings,
        langsmith_client=client,
    )
    data: Any
    if hosted:
        data = settings.dataset_name
    else:
        data = load_golden_examples(project_root, case_ids)
    if hosted and case_ids:
        raise ValueError(
            "Hosted runs use the synchronized dataset. Use a LangSmith dataset "
            "split for hosted filtering or omit --hosted for a local case subset."
        )

    prefix = experiment_prefix or f"payroll-mfa-{rag_provider}-top{top_k}"
    kwargs = {
        "data": data,
        "evaluators": build_evaluators(profile),
        "summary_evaluators": [experiment_summary],
        "experiment_prefix": prefix,
        "description": (
            "Existing payroll-MFA RAG evaluated over the governed eight-case "
            "dataset with transparent code evaluators."
        ),
        "max_concurrency": settings.max_concurrency,
        "num_repetitions": num_repetitions,
        "upload_results": hosted,
        "metadata": {
            "mode": "hosted-live" if hosted else "local-live",
            "models": [f"{rag_provider}:{rag_settings.chat_model}"],
            "embedding_model": rag_settings.embedding_model,
            "top_k": top_k,
            "num_repetitions": num_repetitions,
            "metric_profile": profile,
            "dataset_version": GOLDEN_DATASET_VERSION,
            "framework_version": LANGSMITH_SDK_VERSION,
        },
    }
    results = (
        client.evaluate(_live_target(application, top_k), **kwargs)
        if client is not None
        else evaluate(_live_target(application, top_k), **kwargs)
    )
    rows = list(results)
    experiment_name, experiment_id, experiment_url = _experiment_details(results)
    report = build_report(
        mode="hosted-live" if hosted else "local-live",
        profile=profile,
        cases=normalize_rows(rows),
        upload_results=hosted,
        sdk_version=LANGSMITH_SDK_VERSION,
        experiment_name=experiment_name,
        experiment_id=experiment_id,
        experiment_url=experiment_url,
        project_name=settings.project_name,
        dataset_name=settings.dataset_name if hosted else "local-golden-v1",
        dataset_version=GOLDEN_DATASET_VERSION,
        rag_provider=rag_provider,
        top_k=top_k,
        num_repetitions=num_repetitions,
    )
    json_path, csv_path = save_report(report, output_dir)
    return report, json_path, csv_path


def compare_experiments(
    *,
    experiment_a: str,
    experiment_b: str,
    settings: LangSmithSettings,
    experiment_prefix: str,
) -> dict[str, Any]:
    """Create a hosted pairwise experiment without rerunning either RAG target."""

    if experiment_a == experiment_b:
        raise ValueError("Comparison requires two different experiment names or IDs.")
    client = settings.client()
    results = client.evaluate(
        (experiment_a, experiment_b),
        evaluators=[pairwise_evidence_preference],
        randomize_order=True,
        experiment_prefix=experiment_prefix,
        description=(
            "Risk-first deterministic comparison of two payroll-MFA RAG "
            "experiments over the same governed examples."
        ),
        max_concurrency=settings.max_concurrency,
        metadata={
            "dataset_version": GOLDEN_DATASET_VERSION,
            "comparison_rule": "forbidden-pass-then-evidence-coverage-v1",
        },
    )
    rows = list(results)
    comparative = getattr(results, "comparative_experiment", None)
    return {
        "experiment_a": experiment_a,
        "experiment_b": experiment_b,
        "comparative_experiment_id": (
            str(comparative.id) if comparative is not None else None
        ),
        "comparative_experiment_name": (
            str(comparative.name) if comparative is not None else None
        ),
        "comparison_url": getattr(results, "url", None),
        "compared_example_count": len(rows),
        "target_rerun": False,
        "randomized_order": True,
    }


def reevaluate_existing(
    *, experiment: str, settings: LangSmithSettings, profile: str
) -> Any:
    """Apply current evaluators to cached experiment runs without rerunning RAG."""

    client = settings.client()
    return client.evaluate(
        experiment,
        evaluators=build_evaluators(profile),
        experiment_prefix="payroll-mfa-added-evaluators",
        description="Apply code evaluators to cached experiment traces.",
        max_concurrency=settings.max_concurrency,
    )
