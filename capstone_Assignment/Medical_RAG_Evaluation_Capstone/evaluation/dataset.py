"""Golden-dataset loading and integrity checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from rag.chunking import load_document_chunks

from .models import EvaluationDataError, GoldenCase


def load_golden_cases(path: Path) -> list[GoldenCase]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise EvaluationDataError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, list) or not payload:
        raise EvaluationDataError("The golden dataset must be a non-empty JSON list.")

    cases = [GoldenCase.from_dict(item) for item in payload]
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise EvaluationDataError("Golden case IDs must be unique.")
    questions = [case.question for case in cases]
    if len(questions) != len(set(questions)):
        raise EvaluationDataError("Golden case questions must be unique.")
    return cases


def validate_cases_against_corpus(
    cases: Iterable[GoldenCase], documents_dir: Path
) -> set[str]:
    corpus_ids = {chunk.chunk_id for chunk in load_document_chunks(documents_dir)}
    unknown: list[str] = []
    for case in cases:
        referenced_ids = (
            set(case.context_relevance)
            | set(case.required_context_ids)
            | set(case.expected_citation_ids)
        )
        for chunk_id in sorted(referenced_ids - corpus_ids):
            unknown.append(f"{case.case_id}: {chunk_id}")
    if unknown:
        raise EvaluationDataError(
            "Golden cases reference chunk IDs absent from the corpus: "
            + "; ".join(unknown)
        )
    return corpus_ids


def select_cases(
    cases: list[GoldenCase], requested_case_ids: Iterable[str] | None
) -> list[GoldenCase]:
    requested = list(requested_case_ids or [])
    if not requested:
        return cases
    index = {case.case_id: case for case in cases}
    missing = sorted(set(requested) - set(index))
    if missing:
        raise EvaluationDataError("Unknown case IDs: " + ", ".join(missing))
    return [index[case_id] for case_id in requested]
