"""Day 3 lab: run a small retrieval-evidence experiment with Ragas 0.4.3."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ragas import Dataset, experiment
from ragas.metrics import numeric_metric


LAB_DIR = Path(__file__).resolve().parent
DATA_PATH = LAB_DIR / "data" / "retrieval_traces.jsonl"
RESULTS_DIR = LAB_DIR / "results"


@numeric_metric(name="retrieval_id_precision", allowed_values=(0.0, 1.0))
def retrieval_id_precision(
    retrieved_context_ids: list[str], reference_context_ids: list[str]
) -> float:
    """Measure how much retrieved evidence is relevant."""
    retrieved = set(retrieved_context_ids)
    reference = set(reference_context_ids)
    return len(retrieved & reference) / len(retrieved) if retrieved else 0.0


@numeric_metric(name="retrieval_id_recall", allowed_values=(0.0, 1.0))
def retrieval_id_recall(
    retrieved_context_ids: list[str], reference_context_ids: list[str]
) -> float:
    """Measure how much required evidence was retrieved."""
    retrieved = set(retrieved_context_ids)
    reference = set(reference_context_ids)
    return len(retrieved & reference) / len(reference) if reference else 1.0


@experiment()
async def evaluate_retrieval(row: dict[str, Any]) -> dict[str, Any]:
    """Apply both retrieval metrics to one RAG trace."""
    precision = retrieval_id_precision.score(
        retrieved_context_ids=row["retrieved_context_ids"],
        reference_context_ids=row["reference_context_ids"],
    )
    recall = retrieval_id_recall.score(
        retrieved_context_ids=row["retrieved_context_ids"],
        reference_context_ids=row["reference_context_ids"],
    )
    return {
        **row,
        "retrieval_id_precision": precision.value,
        "retrieval_id_recall": recall.value,
    }


def load_dataset() -> Dataset:
    """Load immutable JSONL evidence into a local Ragas dataset."""
    records = [
        json.loads(line)
        for line in DATA_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    dataset = Dataset(
        name="aspire_day3_mfa_retrieval",
        backend="local/csv",
        root_dir=RESULTS_DIR,
    )
    for record in records:
        dataset.append(record)
    dataset.save()
    return dataset


async def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    dataset = load_dataset()
    results = await evaluate_retrieval.arun(
        dataset,
        name="mfa_retrieval_baseline",
    )

    rows = sorted(list(results), key=lambda row: row["trace_id"])
    print("\nDay 3 criterion: retrieval quality against approved context IDs")
    print("Trace                         Precision  Recall   Interpretation")
    print("----------------------------  ---------  -------  ----------------------------")
    for row in rows:
        precision = float(row["retrieval_id_precision"])
        recall = float(row["retrieval_id_recall"])
        print(
            f"{row['trace_id']:<28}  {precision:>9.2f}  {recall:>7.2f}  "
            f"{row['expected_interpretation']}"
        )

    print("\nWhat this proves: retrieval coverage and noise for labelled source IDs.")
    print("What this does not prove: faithfulness, answer correctness, or release readiness.")


if __name__ == "__main__":
    asyncio.run(main())
