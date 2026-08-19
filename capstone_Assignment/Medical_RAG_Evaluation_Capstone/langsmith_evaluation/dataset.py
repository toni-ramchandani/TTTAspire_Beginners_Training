"""Map the existing governed RAG golden cases into LangSmith examples.

This adapter intentionally depends only on ``evaluation/data/golden_cases.json``.
It has no dependency on the Day 4 core-metrics lab or any frozen output dataset.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
from uuid import NAMESPACE_URL, UUID, uuid5

from langsmith.schemas import Example

from evaluation.dataset import (
    load_golden_cases,
    select_cases,
    validate_cases_against_corpus,
)
from evaluation.models import GoldenCase


LOCAL_GOLDEN_DATASET_ID = UUID("7cb7ef8a-d80d-5f0f-9fea-0491601c258d")
GOLDEN_DATASET_VERSION = "medical-education-golden-v1"


def _reference_outputs(case: GoldenCase) -> dict[str, Any]:
    """Preserve the complete governed evaluation contract as reference output."""

    return {
        "answer": case.reference,
        "required_context_ids": list(case.required_context_ids),
        "context_relevance": dict(case.context_relevance),
        "expected_citation_ids": list(case.expected_citation_ids),
        "required_concepts": [list(group) for group in case.required_concepts],
        "forbidden_claim_patterns": list(case.forbidden_claim_patterns),
    }


def _load_cases(
    project_root: Path, requested_case_ids: Iterable[str] | None = None
) -> list[GoldenCase]:
    cases = load_golden_cases(
        project_root / "evaluation" / "data" / "golden_cases.json"
    )
    validate_cases_against_corpus(cases, project_root / "documents")
    return select_cases(cases, requested_case_ids)


def load_golden_examples(
    project_root: Path, requested_case_ids: Iterable[str] | None = None
) -> list[Example]:
    """Build local SDK examples for no-upload dry runs and unit tests."""

    return [
        Example(
            id=uuid5(
                NAMESPACE_URL,
                f"{GOLDEN_DATASET_VERSION}:{case.case_id}",
            ),
            dataset_id=LOCAL_GOLDEN_DATASET_ID,
            inputs={"case_id": case.case_id, "question": case.question},
            outputs=_reference_outputs(case),
            metadata={
                "case_id": case.case_id,
                "tags": list(case.tags),
                "dataset_version": GOLDEN_DATASET_VERSION,
                "source": "evaluation/data/golden_cases.json",
            },
        )
        for case in _load_cases(project_root, requested_case_ids)
    ]


def hosted_example_payloads(project_root: Path) -> list[dict[str, Any]]:
    """Return stable example IDs so repeated synchronization is idempotent."""

    return [
        {
            "id": example.id,
            "inputs": example.inputs,
            "outputs": example.outputs,
            "metadata": example.metadata,
            "split": ["teaching", GOLDEN_DATASET_VERSION],
        }
        for example in load_golden_examples(project_root)
    ]
