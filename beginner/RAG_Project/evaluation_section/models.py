"""Typed contracts for the governed teaching seed and its validation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evaluation.models import GoldenCase


ALLOWED_SCENARIO_TYPES = {"normal", "edge", "adversarial"}
ALLOWED_SOURCE_TYPES = {"existing_golden", "source_grounded_synthetic"}
ALLOWED_REVIEW_STATUSES = {
    "approved_existing",
    "candidate_requires_human_review",
}


@dataclass(frozen=True)
class Provenance:
    document_id: str
    document_version: str
    chunk_id: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Provenance":
        return cls(
            document_id=str(value["document_id"]).strip(),
            document_version=str(value["document_version"]).strip(),
            chunk_id=str(value["chunk_id"]).strip(),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "document_id": self.document_id,
            "document_version": self.document_version,
            "chunk_id": self.chunk_id,
        }


@dataclass(frozen=True)
class SeedCase:
    golden_case: GoldenCase
    dataset_version: str
    source_type: str
    source_case_id: str | None
    scenario_type: str
    business_critical: bool
    risk_areas: tuple[str, ...]
    review_status: str
    pii_status: str
    provenance: tuple[Provenance, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SeedCase":
        source_case_id = value.get("source_case_id")
        return cls(
            golden_case=GoldenCase.from_dict(value),
            dataset_version=str(value["dataset_version"]).strip(),
            source_type=str(value["source_type"]).strip(),
            source_case_id=(
                str(source_case_id).strip() if source_case_id is not None else None
            ),
            scenario_type=str(value["scenario_type"]).strip(),
            business_critical=bool(value["business_critical"]),
            risk_areas=tuple(str(item).strip() for item in value["risk_areas"]),
            review_status=str(value["review_status"]).strip(),
            pii_status=str(value["pii_status"]).strip(),
            provenance=tuple(
                Provenance.from_dict(item) for item in value["provenance"]
            ),
        )

    @property
    def case_id(self) -> str:
        return self.golden_case.case_id

    def to_dict(self) -> dict[str, Any]:
        case = self.golden_case
        return {
            "case_id": case.case_id,
            "question": case.question,
            "reference": case.reference,
            "required_context_ids": list(case.required_context_ids),
            "context_relevance": dict(case.context_relevance),
            "expected_citation_ids": list(case.expected_citation_ids),
            "required_concepts": [list(group) for group in case.required_concepts],
            "forbidden_claim_patterns": list(case.forbidden_claim_patterns),
            "tags": list(case.tags),
            "dataset_version": self.dataset_version,
            "source_type": self.source_type,
            "source_case_id": self.source_case_id,
            "scenario_type": self.scenario_type,
            "business_critical": self.business_critical,
            "risk_areas": list(self.risk_areas),
            "review_status": self.review_status,
            "pii_status": self.pii_status,
            "provenance": [item.to_dict() for item in self.provenance],
        }
