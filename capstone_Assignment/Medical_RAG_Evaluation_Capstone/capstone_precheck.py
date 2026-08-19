"""Dependency-light readiness check for the prebuilt medical capstone assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import fmean

from evaluation.dataset import load_golden_cases, validate_cases_against_corpus
from evaluation.deterministic_metrics import compute_deterministic_metrics
from evaluation.models import TraceRecord
from evaluation.retrieval_metrics import compute_retrieval_metrics
from rag.chunking import load_document_chunks


ROOT = Path(__file__).resolve().parent


def _jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        rows.append(value)
    return rows


def run_precheck() -> dict[str, object]:
    dataset_path = ROOT / "evaluation" / "data" / "golden_cases.json"
    cases = load_golden_cases(dataset_path)
    chunks = load_document_chunks(ROOT / "documents")
    corpus_ids = validate_cases_against_corpus(cases, ROOT / "documents")
    case_index = {case.case_id: case for case in cases}
    traces = _jsonl(ROOT / "baseline" / "golden_reference_traces.jsonl")
    candidates = _jsonl(ROOT / "evaluation" / "data" / "candidate_cases.jsonl")
    risks = _jsonl(ROOT / "evaluation" / "data" / "risk_cases.jsonl")

    failures: list[str] = []
    if len(cases) != 10:
        failures.append(f"Expected 10 governed cases; found {len(cases)}")
    if len(traces) != len(cases):
        failures.append("Reference trace count does not equal governed case count")
    if len(candidates) != 12:
        failures.append(f"Expected 12 candidates; found {len(candidates)}")
    if len(risks) != 10:
        failures.append(f"Expected 10 risk cases; found {len(risks)}")

    trace_ids = {str(row.get("case_id")) for row in traces}
    if trace_ids != set(case_index):
        failures.append("Reference traces do not cover exactly MED-001 through MED-010")

    case_results: list[dict[str, object]] = []
    for payload in traces:
        case_id = str(payload.get("case_id"))
        case = case_index.get(case_id)
        if case is None:
            continue
        trace = TraceRecord.from_dict(payload)
        retrieval = compute_retrieval_metrics(
            trace.retrieved_chunk_ids,
            case.context_relevance,
            case.required_context_ids,
        )
        deterministic = compute_deterministic_metrics(
            trace.answer, trace.retrieved_chunk_ids, case
        )
        passed = (
            retrieval["all_required_contexts_at_k"] == 1.0
            and deterministic["citation_validity"] == 1.0
            and deterministic["citation_recall"] == 1.0
            and deterministic["required_concept_coverage"] == 1.0
            and deterministic["forbidden_claim_pass"] == 1.0
        )
        if not passed:
            failures.append(f"{case_id} reference fixture failed deterministic baseline")
        case_results.append(
            {
                "case_id": case_id,
                "passed": passed,
                "required_context_recall": retrieval["required_context_recall_at_k"],
                "citation_validity": deterministic["citation_validity"],
                "citation_recall": deterministic["citation_recall"],
                "required_concept_coverage": deterministic["required_concept_coverage"],
                "forbidden_claim_pass": deterministic["forbidden_claim_pass"],
            }
        )

    invalid_candidate_statuses = sorted(
        {
            str(row.get("review_status"))
            for row in candidates
            if row.get("review_status") not in {"unreviewed", "needs_domain_review"}
        }
    )
    if invalid_candidate_statuses:
        failures.append("Candidates contain an unauthorized approval status")
    if any(row.get("reviewer") for row in candidates):
        failures.append("Candidate reviewer fields must be blank in the learner seed")

    blocking_risks = sum(bool(row.get("blocking")) for row in risks)
    critical_risks = sum(row.get("severity") == "critical" for row in risks)
    summary = {
        "status": "pass" if not failures else "fail",
        "documents": 3,
        "chunks": len(chunks),
        "corpus_chunk_ids": len(corpus_ids),
        "governed_cases": len(cases),
        "candidate_cases": len(candidates),
        "risk_cases": len(risks),
        "blocking_risks": blocking_risks,
        "critical_risks": critical_risks,
        "reference_fixture_pass_rate": (
            fmean(float(row["passed"]) for row in case_results)
            if case_results else 0.0
        ),
        "framework_calls_made": False,
        "model_calls_made": False,
        "failures": failures,
    }
    return {"summary": summary, "cases": case_results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_precheck()
    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if report["summary"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

