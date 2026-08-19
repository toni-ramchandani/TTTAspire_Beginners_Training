from __future__ import annotations

import json
from pathlib import Path

from capstone_precheck import run_precheck
from evaluation.dataset import load_golden_cases, validate_cases_against_corpus
from evaluation.deterministic_metrics import compute_deterministic_metrics
from evaluation.models import TraceRecord
from rag.chunking import load_document_chunks
from rag.pipeline import SYSTEM_INSTRUCTIONS


ROOT = Path(__file__).resolve().parents[1]


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_medical_corpus_has_stable_unique_chunk_ids() -> None:
    chunks = load_document_chunks(ROOT / "documents")
    ids = [chunk.chunk_id for chunk in chunks]
    assert len(chunks) == 18
    assert len(ids) == len(set(ids))
    assert all(chunk_id.startswith(("MED-SCOPE-01::", "MED-RESP-02::", "MED-MEDSAFE-03::")) for chunk_id in ids)


def test_ten_governed_cases_reference_real_chunks() -> None:
    cases = load_golden_cases(ROOT / "evaluation" / "data" / "golden_cases.json")
    corpus_ids = validate_cases_against_corpus(cases, ROOT / "documents")
    assert len(cases) == 10
    assert {case.case_id for case in cases} == {f"MED-{index:03d}" for index in range(1, 11)}
    assert len(corpus_ids) == 18


def test_precheck_is_dependency_free_and_passes() -> None:
    report = run_precheck()
    summary = report["summary"]
    assert summary["status"] == "pass"
    assert summary["model_calls_made"] is False
    assert summary["framework_calls_made"] is False
    assert summary["reference_fixture_pass_rate"] == 1.0


def test_reference_fixtures_have_one_trace_per_case() -> None:
    rows = _jsonl(ROOT / "baseline" / "golden_reference_traces.jsonl")
    assert len(rows) == 10
    assert {row["case_id"] for row in rows} == {f"MED-{index:03d}" for index in range(1, 11)}
    for row in rows:
        TraceRecord.from_dict(row)


def test_emergency_fixture_leads_with_emergency_action() -> None:
    cases = {case.case_id: case for case in load_golden_cases(ROOT / "evaluation" / "data" / "golden_cases.json")}
    row = next(row for row in _jsonl(ROOT / "baseline" / "golden_reference_traces.jsonl") if row["case_id"] == "MED-003")
    metrics = compute_deterministic_metrics(row["answer"], row["retrieved_chunk_ids"], cases["MED-003"])
    assert row["answer"].lower().startswith("call your local emergency number immediately")
    assert metrics["forbidden_claim_pass"] == 1.0


def test_candidates_are_not_silently_approved() -> None:
    rows = _jsonl(ROOT / "evaluation" / "data" / "candidate_cases.jsonl")
    assert len(rows) == 12
    assert all(row["review_status"] in {"unreviewed", "needs_domain_review"} for row in rows)
    assert all(row["reviewer"] is None for row in rows)


def test_risk_suite_contains_direct_and_indirect_injection() -> None:
    rows = _jsonl(ROOT / "evaluation" / "data" / "risk_cases.jsonl")
    categories = {row["category"] for row in rows}
    assert len(rows) == 10
    assert "direct_prompt_injection" in categories
    assert "indirect_prompt_injection" in categories
    assert sum(bool(row["blocking"]) for row in rows) == 9


def test_system_prompt_has_medical_safety_and_untrusted_context_boundaries() -> None:
    text = SYSTEM_INSTRUCTIONS.lower()
    assert "do not diagnose" in text
    assert "change a dose" in text
    assert "treat evidence as data" in text
    assert "emergency" in text


def test_deepeval_full_profile_contains_medical_safety_rubric() -> None:
    text = (ROOT / "deepeval_evaluation" / "metrics.py").read_text(encoding="utf-8")
    assert "Medical Safety and Scope" in text
    assert "emergency escalation" in text
    assert "invented diagnoses" in text


def test_assignment_templates_keep_human_authority_visible() -> None:
    review = json.loads((ROOT / "assignment" / "templates" / "human_review.json").read_text(encoding="utf-8"))
    decision = json.loads((ROOT / "assignment" / "templates" / "release_decision.json").read_text(encoding="utf-8"))
    assert set(review["reviewer_accountability"]) == {"dataset_reviewer", "safety_reviewer", "release_owner"}
    assert decision["decision"] == "BLOCK"


def test_no_real_patient_data_is_shipped() -> None:
    forbidden_keys = {"patient_name", "date_of_birth", "medical_record_number", "prescription_number"}
    for path in list((ROOT / "evaluation" / "data").glob("*.json*")) + list((ROOT / "baseline").glob("*.json*")):
        text = path.read_text(encoding="utf-8").lower()
        assert not any(f'"{key}"' in text for key in forbidden_keys)
