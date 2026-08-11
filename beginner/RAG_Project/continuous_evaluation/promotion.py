"""Create a governed candidate from a reviewed, sanitized online trace."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_LONG_NUMBER = re.compile(r"(?<!\d)(?:\d[ -]?){7,}\d(?!\d)")


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def promote_reviewed_trace(
    *,
    envelope_path: Path,
    review_path: Path,
    output_path: Path,
    case_id: str,
) -> dict[str, Any]:
    envelope = _load_object(envelope_path)
    review = _load_object(review_path)
    if review.get("review_status") != "human_review_complete":
        raise ValueError("review_status must be human_review_complete")
    if review.get("dataset_disposition") != "add_candidate":
        raise ValueError("dataset_disposition must be add_candidate")
    if review.get("human_disposition") not in {
        "confirmed_failure",
        "new_coverage_candidate",
    }:
        raise ValueError(
            "human_disposition must be confirmed_failure or new_coverage_candidate"
        )

    required_lists = (
        "required_context_ids",
        "required_concepts",
        "forbidden_claim_patterns",
        "risk_areas",
        "provenance",
    )
    for field in required_lists:
        if not isinstance(review.get(field), list):
            raise ValueError(f"{field} must be a list")
    for field in ("sanitized_question", "reference"):
        if not isinstance(review.get(field), str) or not review[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
    combined = review["sanitized_question"] + "\n" + review["reference"]
    if _EMAIL.search(combined) or _LONG_NUMBER.search(combined):
        raise ValueError("Possible raw PII remains in the sanitized candidate")

    candidate = {
        "schema_version": "observed-online-candidate-1.0",
        "case_id": case_id,
        "source_type": "observed_online_candidate",
        "review_status": "candidate_requires_domain_approval",
        "traffic_origin": envelope.get("metadata", {}).get("traffic_type"),
        "source_trace_id": envelope.get("trace", {}).get("run_id"),
        "source_request_id": envelope.get("request_id"),
        "question": review["sanitized_question"].strip(),
        "reference": review["reference"].strip(),
        "required_context_ids": review["required_context_ids"],
        "expected_citation_ids": review.get(
            "expected_citation_ids", review["required_context_ids"]
        ),
        "required_concepts": review["required_concepts"],
        "forbidden_claim_patterns": review["forbidden_claim_patterns"],
        "risk_areas": review["risk_areas"],
        "provenance": review["provenance"],
        "human_review": {
            "disposition": review["human_disposition"],
            "component": review.get("component"),
            "severity": review.get("severity"),
            "notes": review.get("notes"),
        },
        "promotion_boundary": (
            "This record is a reviewed candidate, not an approved golden case. "
            "Domain approval and dataset versioning are still required."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(candidate, ensure_ascii=False) + "\n")
    return candidate

