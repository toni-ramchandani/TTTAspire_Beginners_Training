from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from evaluation.dataset import load_golden_cases, validate_cases_against_corpus
from evaluation.deterministic_metrics import compute_deterministic_metrics
from evaluation.judges import JudgeSettings, build_judge_bundle
from evaluation.models import TraceRecord
from evaluation.reporting import apply_gates, build_summary, save_report
from evaluation.retrieval_metrics import compute_retrieval_metrics


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "evaluation" / "data" / "golden_cases.json"


def _case(case_id: str):
    return next(case for case in load_golden_cases(DATASET_PATH) if case.case_id == case_id)


def test_golden_dataset_is_unique_and_references_real_chunks() -> None:
    cases = load_golden_cases(DATASET_PATH)
    corpus_ids = validate_cases_against_corpus(cases, PROJECT_ROOT / "documents")

    assert len(cases) == 8
    assert len({case.case_id for case in cases}) == 8
    assert len(corpus_ids) == 15
    assert {case.case_id for case in cases} == {
        "MFA-001",
        "MFA-002",
        "MFA-003",
        "MFA-004",
        "MFA-005",
        "MFA-006",
        "MFA-007",
        "MFA-008",
    }


def test_retrieval_metrics_cover_set_rank_and_graded_relevance() -> None:
    metrics = compute_retrieval_metrics(
        retrieved_ids=["A", "X", "C"],
        context_relevance={"A": 3, "B": 2, "C": 1},
        required_context_ids=["A", "B"],
    )

    assert metrics["precision_at_k"] == pytest.approx(2 / 3)
    assert metrics["recall_at_k"] == pytest.approx(2 / 3)
    assert metrics["f1_at_k"] == pytest.approx(2 / 3)
    assert metrics["hit_at_k"] == 1.0
    assert metrics["reciprocal_rank_at_k"] == 1.0
    assert metrics["average_precision_at_k"] == pytest.approx((1 + 2 / 3) / 3)
    assert metrics["required_context_recall_at_k"] == 0.5
    assert metrics["all_required_contexts_at_k"] == 0.0
    assert 0 < metrics["ndcg_at_k"] < 1


def test_retrieval_metrics_return_zero_when_top_k_has_no_relevant_item() -> None:
    metrics = compute_retrieval_metrics(
        retrieved_ids=["X", "Y"],
        context_relevance={"A": 3},
        required_context_ids=["A"],
    )

    for name in (
        "precision_at_k",
        "recall_at_k",
        "f1_at_k",
        "hit_at_k",
        "reciprocal_rank_at_k",
        "average_precision_at_k",
        "ndcg_at_k",
        "required_context_recall_at_k",
        "all_required_contexts_at_k",
    ):
        assert metrics[name] == 0.0


def test_citation_and_policy_checks_are_independent_of_ragas() -> None:
    case = _case("MFA-002")
    safe_answer = (
        "A manager cannot approve a bypass [SEC-17::prohibited-shortcuts]. "
        "Use an urgent Payroll Support ticket; the assisted process does not restore "
        "portal access [SEC-17::payroll-deadline-fallback]."
    )
    metrics = compute_deterministic_metrics(
        safe_answer,
        [
            "SEC-17::prohibited-shortcuts",
            "SEC-17::payroll-deadline-fallback",
        ],
        case,
    )

    assert metrics["citation_validity"] == 1.0
    assert metrics["citation_precision"] == 1.0
    assert metrics["citation_recall"] == 1.0
    assert metrics["forbidden_claim_pass"] == 1.0

    unsafe = compute_deterministic_metrics(
        "A manager can approve a temporary MFA bypass.",
        ["SEC-17::prohibited-shortcuts"],
        case,
    )
    assert unsafe["forbidden_claim_pass"] == 0.0
    assert unsafe["citation_validity"] == 0.0


def test_trace_contract_rejects_misaligned_retrieval_arrays() -> None:
    with pytest.raises(ValueError, match="equal lengths"):
        TraceRecord.from_dict(
            {
                "run_id": "run-1",
                "question": "Q",
                "answer": "A",
                "provider": "ollama",
                "embedding_model": "embed",
                "generation_model": "chat",
                "top_k": 1,
                "retrieved_chunk_ids": ["A::one"],
                "retrieved_contexts": [],
                "retrieval_scores": [0.5],
            }
        )


def test_ollama_judge_settings_use_openai_compatible_v1_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("RAGAS_OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("RAGAS_OLLAMA_CHAT_MODEL", "local-chat")
    monkeypatch.setenv("RAGAS_OLLAMA_EMBEDDING_MODEL", "local-embed")

    settings = JudgeSettings.from_env(PROJECT_ROOT, "ollama")

    assert settings.base_url == "http://localhost:11434/v1"
    assert settings.api_key == "ollama"
    assert settings.chat_model == "local-chat"
    assert settings.embedding_model == "local-embed"


def test_ragas_04_factories_initialize_with_tested_dependency_set(monkeypatch) -> None:
    pytest.importorskip("ragas")
    monkeypatch.setenv("RAGAS_OLLAMA_BASE_URL", "http://localhost:11434")
    settings = JudgeSettings.from_env(PROJECT_ROOT, "ollama")

    bundle = build_judge_bundle(settings)

    assert bundle.settings.provider == "ollama"
    assert bundle.llm is not None
    assert bundle.embeddings is not None
    assert bundle.llm.is_async is True
    assert bundle.embeddings.is_async is True


def test_report_summary_uses_macro_map_mrr_and_error_rate(tmp_path: Path) -> None:
    retrieval = {
        "k": 2,
        "retrieved_relevant_count": 1,
        "judged_relevant_count": 2,
        "required_context_count": 2,
        "required_context_hit_count": 1,
        "precision_at_k": 0.5,
        "recall_at_k": 0.5,
        "f1_at_k": 0.5,
        "hit_at_k": 1.0,
        "reciprocal_rank_at_k": 1.0,
        "average_precision_at_k": 0.5,
        "ndcg_at_k": 0.7,
        "required_context_recall_at_k": 0.5,
        "all_required_contexts_at_k": 0.0,
    }
    deterministic = {
        "citation_validity": 1.0,
        "citation_precision": 1.0,
        "citation_recall": 0.5,
        "citation_f1": 2 / 3,
        "required_concept_coverage": 0.75,
        "forbidden_claim_pass": 1.0,
    }
    result = {
        "case_id": "TEST-1",
        "question": "Q",
        "trace": {
            "provider": "ollama",
            "generation_model": "chat",
            "embedding_model": "embed",
            "top_k": 2,
            "retrieved_chunk_ids": ["A", "X"],
            "answer": "A",
        },
        "retrieval_metrics": retrieval,
        "deterministic_metrics": deterministic,
        "ragas_metrics": {
            "faithfulness": {
                "value": 0.8,
                "reason": None,
                "error": None,
                "latency_ms": 10,
            },
            "context_recall": {
                "value": None,
                "reason": None,
                "error": "failed",
                "latency_ms": 10,
            },
        },
    }
    summary = build_summary([result])
    assert summary["aliases"]["map_at_k"] == 0.5
    assert summary["aliases"]["mrr_at_k"] == 1.0
    assert summary["ragas_macro"]["faithfulness"] == 0.8
    assert summary["ragas_error_rate"] == 0.5

    report = {
        "experiment_id": "test-experiment",
        "cases": [result],
        "summary": summary,
    }
    json_path, csv_path = save_report(report, tmp_path)
    assert json.loads(json_path.read_text(encoding="utf-8"))["experiment_id"] == (
        "test-experiment"
    )
    assert "retrieval_precision_at_k" in csv_path.read_text(encoding="utf-8")


def test_disabled_example_gates_do_not_create_an_invented_release_bar() -> None:
    report = {"summary": {}, "cases": []}
    result = apply_gates(report, PROJECT_ROOT / "evaluation" / "gates.example.json")

    assert result == {"enabled": False, "passed": True, "failures": []}
