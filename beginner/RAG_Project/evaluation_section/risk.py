"""Safe live risk-screening harness for the existing read-only RAG application."""

from __future__ import annotations

import json
import re
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag.config import Settings
from rag.models import DocumentChunk, RetrievedChunk
from rag.pipeline import RAGApplication, SYSTEM_INSTRUCTIONS, build_generation_prompt


def load_risk_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid risk case at line {line_number}: {exc}") from exc
        cases.append(value)
    ids = [str(case["case_id"]) for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Risk case IDs must be unique.")
    return cases


def _screen(answer: str, case: dict[str, Any]) -> dict[str, Any]:
    required_results: list[dict[str, Any]] = []
    for group in case["required_pattern_groups"]:
        matched = next(
            (
                pattern
                for pattern in group
                if re.search(pattern, answer, flags=re.I | re.M)
            ),
            None,
        )
        required_results.append(
            {"patterns": group, "matched": matched is not None, "match": matched}
        )
    forbidden_matches = [
        pattern
        for pattern in case["forbidden_patterns"]
        if re.search(pattern, answer, flags=re.I | re.M)
    ]
    return {
        "required_groups": required_results,
        "required_pass": all(item["matched"] for item in required_results),
        "forbidden_matches": forbidden_matches,
        "forbidden_pass": not forbidden_matches,
        "screen_pass": all(item["matched"] for item in required_results)
        and not forbidden_matches,
    }


def _controlled_indirect_answer(
    app: RAGApplication, case: dict[str, Any]
) -> tuple[str, int, list[str]]:
    chunk = DocumentChunk(
        chunk_id=f"UNTRUSTED-TRAINING::{case['case_id'].lower()}",
        document_id="UNTRUSTED-TRAINING",
        document_title="Synthetic Untrusted Retrieval Fixture",
        document_version="1.0",
        section_title="Controlled prompt-injection fixture",
        source_file="evaluation_section/data/risk_cases.jsonl",
        text=str(case["context_text"]),
    )
    retrieved = [RetrievedChunk(chunk=chunk, score=1.0)]
    started = time.perf_counter()
    answer = app.provider.generate(
        SYSTEM_INSTRUCTIONS,
        build_generation_prompt(str(case["question"]), retrieved),
    )
    elapsed = round((time.perf_counter() - started) * 1000)
    return answer, elapsed, [chunk.chunk_id]


def _pair_summary(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        if result.get("pair_id"):
            grouped[str(result["pair_id"])].append(result)
    summaries: list[dict[str, Any]] = []
    for pair_id, pair in sorted(grouped.items()):
        if len(pair) != 2:
            summaries.append(
                {"pair_id": pair_id, "comparable": False, "reason": "pair must contain two runs"}
            )
            continue
        left, right = pair
        required_vectors = [
            [item["matched"] for item in result["screen"]["required_groups"]]
            for result in pair
        ]
        parity = (
            left["screen"]["screen_pass"] == right["screen"]["screen_pass"]
            and required_vectors[0] == required_vectors[1]
        )
        summaries.append(
            {
                "pair_id": pair_id,
                "comparable": True,
                "case_ids": [left["case_id"], right["case_id"]],
                "screen_outcome_parity": parity,
                "screen_passes": [
                    left["screen"]["screen_pass"],
                    right["screen"]["screen_pass"],
                ],
                "required_match_vectors": required_vectors,
                "limitation": (
                    "A paired smoke test can reveal inconsistent configured outcomes. "
                    "It does not establish absence of bias or group fairness."
                ),
            }
        )
    return summaries


def run_risk_suite(
    project_root: Path,
    cases_path: Path,
    output_dir: Path,
    provider: str,
    top_k: int,
    case_ids: list[str] | None,
) -> tuple[dict[str, Any], Path]:
    all_cases = load_risk_cases(cases_path)
    if case_ids:
        by_id = {case["case_id"]: case for case in all_cases}
        unknown = sorted(set(case_ids) - set(by_id))
        if unknown:
            raise ValueError("Unknown risk case IDs: " + ", ".join(unknown))
        cases = [by_id[case_id] for case_id in case_ids]
    else:
        cases = all_cases

    app = RAGApplication(project_root, Settings.from_env(project_root, provider))
    results: list[dict[str, Any]] = []
    for case in cases:
        delivery = case["delivery"]
        if delivery == "indirect_controlled_context":
            answer, latency_ms, retrieved_ids = _controlled_indirect_answer(app, case)
            trace_path = None
        else:
            trace, saved_path = app.ask(str(case["question"]), top_k)
            answer = trace.answer
            latency_ms = trace.total_latency_ms
            retrieved_ids = [item.chunk.chunk_id for item in trace.retrieved]
            trace_path = str(saved_path)
        results.append(
            {
                "case_id": case["case_id"],
                "delivery": delivery,
                "category": case["category"],
                "pair_id": case.get("pair_id"),
                "question": case["question"],
                "answer": answer,
                "retrieved_chunk_ids": retrieved_ids,
                "latency_ms": latency_ms,
                "trace_path": trace_path,
                "screen": _screen(answer, case),
                "human_review_required": True,
            }
        )

    now = datetime.now(timezone.utc)
    report = {
        "schema_version": "rag-risk-screen-1.0",
        "run_id": f"risk-{now.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "created_at_utc": now.isoformat(),
        "provider": provider,
        "top_k": top_k,
        "case_count": len(results),
        "results": results,
        "pair_summaries": _pair_summary(results),
        "screen_failure_case_ids": [
            result["case_id"] for result in results if not result["screen"]["screen_pass"]
        ],
        "bounded_claim": (
            "This is a safe, synthetic risk screen over a read-only RAG. Passing cases do not "
            "prove prompt-injection resistance, fairness, legal compliance, or production safety."
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "latest_risk_report.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report, path
