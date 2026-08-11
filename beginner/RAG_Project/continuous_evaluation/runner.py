"""Execute production-like traffic, evaluate traces, and retain evidence."""

from __future__ import annotations

import csv
import json
import time
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import REPORT_SCHEMA_VERSION, TRACE_ENVELOPE_SCHEMA_VERSION
from .deepeval_online import evaluate_reference_free_with_deepeval
from .evaluators import evaluate_online_trace
from .sampling import semantic_selection
from .traffic import TrafficRequest, load_traffic


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _case_lookup(project_root: Path) -> dict[str, dict[str, Any]]:
    values = _load_json(project_root / "evaluation" / "data" / "golden_cases.json")
    return {str(value["case_id"]): value for value in values}


def _risk_lookup(project_root: Path) -> dict[str, dict[str, Any]]:
    path = project_root / "evaluation_section" / "data" / "risk_cases.jsonl"
    values = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {str(value["case_id"]): value for value in values}


def _metadata(
    *,
    request: TrafficRequest,
    environment: str,
    release_id: str,
    prompt_version: str,
    provider: Any,
    top_k: int,
) -> dict[str, Any]:
    return {
        "environment": environment,
        "release_id": release_id,
        "prompt_version": prompt_version,
        "corpus_version": "SEC-17-v2.1+OPS-09-v1.4",
        "chunker_version": "markdown-section-v1",
        "traffic_type": request.traffic_type,
        "request_id": request.request_id,
        "approved_case_id": request.approved_case_id,
        "risk_case_id": request.risk_case_id,
        "privacy_mode": "synthetic-content-captured",
        "rag_provider": provider.provider_name,
        "embedding_model": provider.embedding_model,
        "generation_model": provider.generation_model,
        "top_k": top_k,
    }


def _controlled_indirect_trace(
    *,
    app: Any,
    request: TrafficRequest,
    metadata: dict[str, Any],
    hosted: bool,
    client: Any | None,
    project_name: str | None,
) -> tuple[Any, Path, str | None]:
    from rag.models import DocumentChunk, RAGTrace, RetrievedChunk

    context = request.controlled_context
    if not context:
        raise ValueError("Controlled indirect execution requires controlled_context")
    chunk = DocumentChunk(
        chunk_id=f"UNTRUSTED-TRAINING::{request.risk_case_id.lower()}",
        document_id="UNTRUSTED-TRAINING",
        document_title="Synthetic Untrusted Retrieval Fixture",
        document_version="1.0",
        section_title="Controlled prompt-injection fixture",
        source_file="continuous_evaluation/data/production_like_traffic.jsonl",
        text=context,
    )
    retrieved = [RetrievedChunk(chunk=chunk, score=1.0)]
    root_id: str | None = None

    def execute(run_tree: Any | None = None):
        nonlocal root_id
        total_started = time.perf_counter()
        retrieval_started = time.perf_counter()
        selected = list(retrieved)
        retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000)
        generation_started = time.perf_counter()
        answer = app._generate(request.question, selected)
        generation_ms = round((time.perf_counter() - generation_started) * 1000)
        total_ms = round((time.perf_counter() - total_started) * 1000)
        now = datetime.now(timezone.utc)
        trace = RAGTrace(
            schema_version="1.0",
            run_id=f"rag-{now.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}",
            created_at_utc=now.isoformat(),
            question=request.question,
            answer=answer,
            provider=app.provider.provider_name,
            embedding_model=app.provider.embedding_model,
            generation_model=app.provider.generation_model,
            top_k=1,
            chunker_version="controlled-untrusted-fixture-v1",
            retrieval_latency_ms=retrieval_ms,
            generation_latency_ms=generation_ms,
            total_latency_ms=total_ms,
            retrieved=tuple(selected),
        )
        path = app._save_trace(trace)
        if run_tree is not None:
            root_id = str(run_tree.id)
        return trace, path

    if not hosted:
        trace, path = execute()
        return trace, path, None

    from langsmith import traceable
    from langsmith_evaluation.tracing import _document_view

    def traced_execute(run_tree: Any | None = None):
        def retrieval_step() -> list[Any]:
            return list(retrieved)

        traced_retrieval = traceable(
            name="payroll_mfa_retrieve_untrusted_fixture",
            run_type="retriever",
            project_name=project_name,
            client=client,
            tags=["payroll-mfa", "synthetic-security-canary", "indirect-injection"],
            metadata=metadata,
            process_outputs=lambda items: _document_view(items, True),
        )(retrieval_step)
        traced_retrieval()
        return execute(run_tree=run_tree)

    wrapped = traceable(
        name="payroll_mfa_rag",
        run_type="chain",
        project_name=project_name,
        client=client,
        tags=["payroll-mfa", "synthetic-security-canary", "indirect-injection"],
        metadata=metadata,
        process_inputs=lambda values: {
            "question": request.question,
            "traffic_type": request.traffic_type,
        },
        process_outputs=lambda value: {
            "answer": value[0].answer,
            "run_id": value[0].run_id,
            "retrieved_chunk_ids": [
                item.chunk.chunk_id for item in value[0].retrieved
            ],
            "retrieval_latency_ms": value[0].retrieval_latency_ms,
            "generation_latency_ms": value[0].generation_latency_ms,
            "total_latency_ms": value[0].total_latency_ms,
        },
    )(traced_execute)
    trace, path = wrapped()
    return trace, path, root_id


def _publish_feedback(client: Any, run_id: str, evaluation: dict[str, Any]) -> int:
    count = 0
    for key, metric in evaluation["online_deterministic"].items():
        value = metric.get("value")
        if value is None:
            continue
        score = float(value) if isinstance(value, (int, float, bool)) else None
        if score is None:
            continue
        client.create_feedback(
            run_id=run_id,
            key=f"langsmith_feedback_{key}",
            score=score,
            comment=json.dumps(metric.get("evidence"), ensure_ascii=False),
        )
        count += 1
    return count


def _write_report(report: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(report["run_id"])
    json_path = output_dir / f"{run_id}.json"
    csv_path = output_dir / f"{run_id}.csv"
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    json_path.write_text(payload, encoding="utf-8")
    (output_dir / "latest.json").write_text(payload, encoding="utf-8")
    fieldnames = [
        "request_id",
        "traffic_type",
        "canonical_run_id",
        "langsmith_run_id",
        "bounded_outcome",
        "trace_complete",
        "retrieval_nonempty",
        "citation_validity",
        "attack_attempt_detected",
        "unsafe_effect_observed",
        "required_context_recall",
        "semantic_selected",
        "semantic_error",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for item in report["results"]:
            deterministic = item["evaluation"]["online_deterministic"]
            canary = item["evaluation"]["approved_canary_metrics"]
            writer.writerow(
                {
                    "request_id": item["request_id"],
                    "traffic_type": item["metadata"]["traffic_type"],
                    "canonical_run_id": item["trace"]["run_id"],
                    "langsmith_run_id": item.get("langsmith_run_id"),
                    "bounded_outcome": item["evaluation"]["bounded_outcome"],
                    "trace_complete": deterministic["trace_complete"]["value"],
                    "retrieval_nonempty": deterministic["retrieval_nonempty"]["value"],
                    "citation_validity": deterministic["citation_validity"]["value"],
                    "attack_attempt_detected": deterministic["attack_attempt_detected"]["value"],
                    "unsafe_effect_observed": deterministic["unsafe_effect_observed"]["value"],
                    "required_context_recall": (
                        canary.get("required_context_recall", {}).get("value")
                    ),
                    "semantic_selected": item["semantic_selection"]["selected"],
                    "semantic_error": item.get("semantic_error"),
                }
            )
    return json_path, csv_path


def run_live_traffic(
    *,
    project_root: Path,
    traffic_path: Path,
    output_dir: Path,
    rag_provider: str,
    judge_provider: str,
    top_k: int,
    environment: str,
    release_id: str,
    prompt_version: str,
    semantic: bool,
    semantic_sample_rate: float,
    hosted: bool,
    publish_feedback: bool,
) -> tuple[dict[str, Any], Path, Path]:
    if publish_feedback and not hosted:
        raise ValueError("publish_feedback requires hosted=True")
    from rag.config import Settings
    from rag.pipeline import RAGApplication

    requests = load_traffic(traffic_path)
    approved_cases = _case_lookup(project_root)
    risk_cases = _risk_lookup(project_root)
    rag_settings = Settings.from_env(project_root, rag_provider)
    client = None
    project_name = None
    tracing_context_factory = None
    if hosted:
        from langsmith import tracing_context
        from langsmith_evaluation.settings import LangSmithSettings
        from langsmith_evaluation.tracing import LangSmithRAGApplication

        ls_settings = LangSmithSettings.from_env(project_root)
        ls_settings.require_hosted()
        if not ls_settings.tracing_enabled:
            raise ValueError("LANGSMITH_TRACING must be true for hosted execution")
        client = ls_settings.client()
        project_name = ls_settings.project_name
        app = LangSmithRAGApplication(
            project_root,
            rag_settings,
            langsmith_settings=ls_settings,
            langsmith_client=client,
        )
        tracing_context_factory = tracing_context
    else:
        app = RAGApplication(project_root, rag_settings)

    results: list[dict[str, Any]] = []
    for request in requests:
        if request.approved_case_id and request.approved_case_id not in approved_cases:
            raise ValueError(f"Unknown approved_case_id {request.approved_case_id}")
        risk_case = risk_cases.get(request.risk_case_id or "")
        if request.risk_case_id and risk_case is None:
            raise ValueError(f"Unknown risk_case_id {request.risk_case_id}")
        metadata = _metadata(
            request=request,
            environment=environment,
            release_id=release_id,
            prompt_version=prompt_version,
            provider=app.provider,
            top_k=top_k,
        )
        if request.controlled_context:
            context = (
                tracing_context_factory(
                    project_name=project_name,
                    client=client,
                    enabled=True,
                    tags=["payroll-mfa", request.traffic_type, "indirect-injection"],
                    metadata=metadata,
                )
                if hosted
                else nullcontext()
            )
            with context:
                trace, trace_path, langsmith_run_id = _controlled_indirect_trace(
                    app=app,
                    request=request,
                    metadata=metadata,
                    hosted=hosted,
                    client=client,
                    project_name=project_name,
                )
        else:
            context = (
                tracing_context_factory(
                    project_name=project_name,
                    client=client,
                    enabled=True,
                    tags=["payroll-mfa", request.traffic_type],
                    metadata=metadata,
                )
                if hosted
                else nullcontext()
            )
            with context:
                trace, trace_path = app.ask(request.question, top_k)
            langsmith_run_id = (
                app.langsmith_run_id(trace.run_id) if hosted else None
            )
        envelope = {
            "schema_version": TRACE_ENVELOPE_SCHEMA_VERSION,
            "request_id": request.request_id,
            "metadata": metadata,
            "attack_attempt_expected": bool(request.risk_case_id),
            "risk_case": risk_case,
            "trace_path": str(trace_path),
            "trace": trace.to_dict(),
            "langsmith_run_id": langsmith_run_id,
        }
        evaluation = evaluate_online_trace(
            envelope,
            approved_cases.get(request.approved_case_id or ""),
        )
        selected, selection_reason = semantic_selection(
            request, semantic_sample_rate
        )
        envelope["evaluation"] = evaluation
        envelope["semantic_selection"] = {
            "enabled": semantic,
            "selected": bool(semantic and selected),
            "reason": selection_reason,
        }
        if semantic and selected:
            try:
                envelope["deepeval_online"] = evaluate_reference_free_with_deepeval(
                    project_root=project_root,
                    envelope=envelope,
                    judge_provider=judge_provider,
                )
                envelope["semantic_error"] = None
            except Exception as exc:
                envelope["deepeval_online"] = None
                envelope["semantic_error"] = f"{type(exc).__name__}: {exc}"
        else:
            envelope["deepeval_online"] = None
            envelope["semantic_error"] = None
        envelope["published_feedback_count"] = (
            _publish_feedback(client, langsmith_run_id, evaluation)
            if publish_feedback and client is not None and langsmith_run_id
            else 0
        )
        results.append(envelope)

    if client is not None:
        client.flush(timeout=30)
    now = datetime.now(timezone.utc)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": f"continuous-{now.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "created_at_utc": now.isoformat(),
        "mode": "hosted-traced" if hosted else "local-live",
        "traffic_file": str(traffic_path),
        "result_count": len(results),
        "semantic_enabled": semantic,
        "semantic_sample_rate": semantic_sample_rate,
        "results": results,
        "blocking_request_ids": [
            item["request_id"]
            for item in results
            if item["evaluation"]["bounded_outcome"]
            == "blocking_policy_failure_observed"
        ],
        "interpretation_rule": (
            "Per-trace evidence and blocking policy failures take precedence over averages. "
            "Reference-free scores do not establish correctness."
        ),
    }
    json_path, csv_path = _write_report(report, output_dir)
    return report, json_path, csv_path


def evaluate_fixture(
    *,
    project_root: Path,
    fixture_path: Path,
    output_dir: Path,
    semantic: bool,
    judge_provider: str,
) -> tuple[dict[str, Any], Path]:
    envelope = _load_json(fixture_path)
    approved_case_id = envelope.get("metadata", {}).get("approved_case_id")
    approved_case = _case_lookup(project_root).get(str(approved_case_id or ""))
    envelope["evaluation"] = evaluate_online_trace(envelope, approved_case)
    if semantic:
        try:
            envelope["deepeval_online"] = evaluate_reference_free_with_deepeval(
                project_root=project_root,
                envelope=envelope,
                judge_provider=judge_provider,
            )
            envelope["semantic_error"] = None
        except Exception as exc:
            envelope["deepeval_online"] = None
            envelope["semantic_error"] = f"{type(exc).__name__}: {exc}"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "fixture_evaluation.json"
    path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False), encoding="utf-8")
    return envelope, path
