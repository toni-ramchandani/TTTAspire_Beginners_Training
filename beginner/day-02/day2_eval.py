"""Beginner Day 2: evaluate the five preserved Day 1 outputs with DeepEval."""

from __future__ import annotations

import json
import os
from pathlib import Path

# Set these before importing DeepEval. The workshop uses only local evidence.
os.environ["DEEPEVAL_DISABLE_DOTENV"] = "1"
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"

from deepeval import evaluate
from deepeval.metrics import JsonCorrectnessMetric
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase
from pydantic import BaseModel, ConfigDict, StrictStr


DATA_DIR = Path(__file__).resolve().parents[1] / "day-01" / "lab" / "data"


class OfflineReasonModel(DeepEvalBaseLLM):
    """Prevent a provider call if reason generation is invoked accidentally."""

    def load_model(self) -> "OfflineReasonModel":
        return self

    def generate(self, *args, **kwargs) -> str:
        raise RuntimeError("Reason generation is disabled for this offline lab.")

    async def a_generate(self, *args, **kwargs) -> str:
        raise RuntimeError("Reason generation is disabled for this offline lab.")

    def get_model_name(self) -> str:
        return "offline-reason-generation-disabled"


class HelpdeskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: StrictStr
    urgency: StrictStr
    safe_action: StrictStr
    customer_message: StrictStr


case = json.loads(
    (DATA_DIR / "it_helpdesk_case.json").read_text(encoding="utf-8")
)
runs = [
    json.loads(line)
    for line in (DATA_DIR / "cached_outputs.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
    if line.strip()
]

test_cases = [
    LLMTestCase(
        input=case["input"],
        actual_output=record["text"],
        additional_metadata={"run": run_number},
    )
    for run_number, record in enumerate(runs, start=1)
]

metric = JsonCorrectnessMetric(
    expected_schema=HelpdeskResponse,
    model=OfflineReasonModel(),
    strict_mode=True,
    include_reason=False,
    async_mode=False,
)

evaluation = evaluate(
    test_cases=test_cases,
    metrics=[metric],
    hyperparameters={
        "course_day": 2,
        "fixture": case["case_id"],
        "deepeval_version": "4.1.3",
    },
)

scores: list[int] = []
print("\nDay 2 criterion: exact raw output matches the four-field JSON schema")
for run_number, test_result in enumerate(evaluation.test_results, start=1):
    metric_result = test_result.metrics_data[0]
    score = int(metric_result.score)
    scores.append(score)
    print(
        f"Run {run_number}: "
        f"{'PASS' if metric_result.success else 'FAIL'} "
        f"(score={score})"
    )

print(f"Schema pass rate: {sum(scores)}/{len(scores)} = {sum(scores) / len(scores):.0%}")
print("Product release verdict: not established by this metric alone")
