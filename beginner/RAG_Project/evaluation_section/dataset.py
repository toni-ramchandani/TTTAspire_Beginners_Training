"""Build, load, validate, and summarize the 30-row teaching seed dataset."""

from __future__ import annotations

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from evaluation.dataset import validate_cases_against_corpus
from evaluation.models import EvaluationDataError

from .models import (
    ALLOWED_REVIEW_STATUSES,
    ALLOWED_SCENARIO_TYPES,
    ALLOWED_SOURCE_TYPES,
    SeedCase,
)


DATASET_VERSION = "payroll-mfa-eval-seed-v1.0.0"
EXPECTED_ROW_COUNT = 30
EXPECTED_EXISTING_GOLDEN = 8
EXPECTED_CANDIDATES = 22

_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_LONG_NUMBER = re.compile(r"(?<!\d)(?:\d[ -]?){7,}\d(?!\d)")


def load_seed_dataset(path: Path) -> list[SeedCase]:
    cases: list[SeedCase] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        raise
    for line_number, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise TypeError("row is not an object")
            cases.append(SeedCase.from_dict(payload))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise EvaluationDataError(
                f"Invalid seed dataset row {line_number}: {exc}"
            ) from exc
    if not cases:
        raise EvaluationDataError("The seed dataset is empty.")
    return cases


def _normalize_question(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", value.lower()).split())


def _near_duplicate_pairs(cases: list[SeedCase]) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    normalized = [(case.case_id, _normalize_question(case.golden_case.question)) for case in cases]
    for index, (left_id, left) in enumerate(normalized):
        for right_id, right in normalized[index + 1 :]:
            ratio = SequenceMatcher(a=left, b=right).ratio()
            if ratio >= 0.90:
                pairs.append(
                    {"left": left_id, "right": right_id, "similarity": round(ratio, 3)}
                )
    return pairs


def _possible_raw_pii(cases: Iterable[SeedCase]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for case in cases:
        for field_name, text in (
            ("question", case.golden_case.question),
            ("reference", case.golden_case.reference),
        ):
            if _EMAIL.search(text) or _LONG_NUMBER.search(text):
                findings.append({"case_id": case.case_id, "field": field_name})
    return findings


def validate_seed_dataset(
    cases: list[SeedCase], documents_dir: Path, strict_count: bool = True
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    ids = [case.case_id for case in cases]
    questions = [_normalize_question(case.golden_case.question) for case in cases]
    if len(ids) != len(set(ids)):
        errors.append("case_id values must be unique")
    if len(questions) != len(set(questions)):
        errors.append("normalized questions must be unique")
    if strict_count and len(cases) != EXPECTED_ROW_COUNT:
        errors.append(f"expected {EXPECTED_ROW_COUNT} rows, found {len(cases)}")

    for case in cases:
        if case.dataset_version != DATASET_VERSION:
            errors.append(f"{case.case_id}: unexpected dataset_version")
        if case.source_type not in ALLOWED_SOURCE_TYPES:
            errors.append(f"{case.case_id}: invalid source_type")
        if case.scenario_type not in ALLOWED_SCENARIO_TYPES:
            errors.append(f"{case.case_id}: invalid scenario_type")
        if case.review_status not in ALLOWED_REVIEW_STATUSES:
            errors.append(f"{case.case_id}: invalid review_status")
        if not case.risk_areas:
            errors.append(f"{case.case_id}: risk_areas must not be empty")
        if not case.provenance:
            errors.append(f"{case.case_id}: provenance must not be empty")
        if case.pii_status != "synthetic_no_raw_pii":
            errors.append(f"{case.case_id}: pii_status must be synthetic_no_raw_pii")
        provenance_ids = {item.chunk_id for item in case.provenance}
        if not set(case.golden_case.required_context_ids).issubset(provenance_ids):
            errors.append(f"{case.case_id}: provenance omits a required context")
        if case.source_type == "existing_golden" and case.review_status != "approved_existing":
            errors.append(f"{case.case_id}: existing golden must retain approved_existing")
        if (
            case.source_type == "source_grounded_synthetic"
            and case.review_status != "candidate_requires_human_review"
        ):
            errors.append(f"{case.case_id}: synthetic row must remain a review candidate")

    try:
        validate_cases_against_corpus(
            [case.golden_case for case in cases], documents_dir
        )
    except EvaluationDataError as exc:
        errors.append(str(exc))

    scenario_counts = Counter(case.scenario_type for case in cases)
    for required in sorted(ALLOWED_SCENARIO_TYPES):
        if scenario_counts[required] == 0:
            errors.append(f"missing required scenario slice: {required}")
    if not any(case.business_critical for case in cases):
        errors.append("business-critical slice is empty")

    source_counts = Counter(case.source_type for case in cases)
    if strict_count and source_counts["existing_golden"] != EXPECTED_EXISTING_GOLDEN:
        errors.append(
            f"expected {EXPECTED_EXISTING_GOLDEN} existing golden rows, "
            f"found {source_counts['existing_golden']}"
        )
    if strict_count and source_counts["source_grounded_synthetic"] != EXPECTED_CANDIDATES:
        errors.append(
            f"expected {EXPECTED_CANDIDATES} source-grounded candidates, "
            f"found {source_counts['source_grounded_synthetic']}"
        )

    near_duplicates = _near_duplicate_pairs(cases)
    if near_duplicates:
        warnings.append(
            f"{len(near_duplicates)} near-duplicate pair(s) require intentionality review"
        )
    pii_findings = _possible_raw_pii(cases)
    if pii_findings:
        errors.append(f"possible raw PII found in {len(pii_findings)} field(s)")

    return {
        "valid": not errors,
        "dataset_version": DATASET_VERSION,
        "row_count": len(cases),
        "errors": errors,
        "warnings": warnings,
        "source_counts": dict(sorted(source_counts.items())),
        "review_status_counts": dict(
            sorted(Counter(case.review_status for case in cases).items())
        ),
        "scenario_counts": dict(sorted(scenario_counts.items())),
        "business_critical_count": sum(case.business_critical for case in cases),
        "risk_area_counts": dict(
            sorted(Counter(area for case in cases for area in case.risk_areas).items())
        ),
        "near_duplicate_pairs": near_duplicates,
        "possible_raw_pii": pii_findings,
        "bounded_claim": (
            "Thirty rows form a teaching seed dataset. They do not establish "
            "production coverage or a mature golden dataset."
        ),
    }


def select_seed_cases(
    cases: list[SeedCase], case_ids: Iterable[str] | None
) -> list[SeedCase]:
    requested = list(case_ids or [])
    if not requested:
        return cases
    by_id = {case.case_id: case for case in cases}
    unknown = sorted(set(requested) - set(by_id))
    if unknown:
        raise EvaluationDataError("Unknown seed case IDs: " + ", ".join(unknown))
    return [by_id[case_id] for case_id in requested]
