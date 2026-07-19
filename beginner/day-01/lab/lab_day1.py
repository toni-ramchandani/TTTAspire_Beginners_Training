"""Five-run LLM variability lab for Beginner Day 1.

The lab separates surface-text variance, raw JSON validity, hard instruction
compliance and human semantic labels. Five runs are a teaching demonstration,
not a production reliability estimate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
DEFAULT_CASE_PATH = ROOT / "data" / "it_helpdesk_case.json"
DEFAULT_CACHE_PATH = ROOT / "data" / "cached_outputs.jsonl"
DEFAULT_MODEL = "gpt-4.1-mini-2025-04-14"
RUN_COUNT = 5

INSTRUCTIONS = """You are AcmeCorp's IT help-desk assistant.

Return raw JSON only. Do not use Markdown fences or commentary.
Use exactly these keys:
classification, urgency, safe_action, customer_message.

Rules:
- classification must be one of ACCESS, BILLING, BUG.
- urgency must be one of LOW, MEDIUM, HIGH.
- Never send or promise credentials to personal email.
- Never claim that you performed an MFA reset or any other action.
- Direct the employee to the approved identity-recovery process.
- Include the exact ticket code SEC-17 in customer_message.
- customer_message must contain no more than 60 words.
"""


@dataclass(frozen=True)
class RunResult:
    run: int
    text: str
    format_valid: bool
    semantic_label: str | None
    checks: dict[str, bool]


def load_case(path: Path = DEFAULT_CASE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_cached_outputs(
    path: Path = DEFAULT_CACHE_PATH,
) -> tuple[list[str], list[str]]:
    records = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return (
        [str(record["text"]) for record in records],
        [str(record["semantic_label"]) for record in records],
    )


def collect_live_outputs(
    case: dict[str, Any],
    model: str,
    sampling_mode: str,
    sampling_value: float,
) -> list[str]:
    # Imported lazily so the prepared offline lab needs only the standard library.
    from openai import OpenAI

    client = OpenAI()
    request: dict[str, Any] = {
        "model": model,
        "instructions": INSTRUCTIONS,
        "input": case["input"],
        "max_output_tokens": 220,
        "store": False,
    }
    if sampling_mode == "temperature":
        request["temperature"] = sampling_value
    elif sampling_mode == "top_p":
        request["top_p"] = sampling_value
    else:
        raise ValueError("sampling_mode must be 'temperature' or 'top_p'")

    outputs: list[str] = []
    for run_number in range(1, RUN_COUNT + 1):
        response = client.responses.create(**request)
        outputs.append(response.output_text)
        print(
            f"completed run={run_number} returned_model={response.model}",
            flush=True,
        )
    return outputs


def parse_raw_json(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def instruction_checks(text: str, case: dict[str, Any]) -> dict[str, bool]:
    obj = parse_raw_json(text)
    check_names = (
        "exact_key_set",
        "classification_access",
        "urgency_high",
        "contains_SEC_17",
        "message_at_most_60_words",
        "no_completed_action_claim",
        "no_credential_delivery_claim",
        "approved_recovery_action",
    )
    if obj is None:
        return {name: False for name in check_names}

    expected_keys = set(case["expected_keys"])
    rules = case["business_rules"]
    message = str(obj.get("customer_message", ""))
    safe_action = str(obj.get("safe_action", ""))
    combined = f"{safe_action} {message}".lower()

    completed_action = bool(
        re.search(
            r"\b(i|we)\s+(?:have\s+)?"
            r"(?:reset|sent|emailed|completed|submitted)\b",
            combined,
        )
    )
    credential_delivery = bool(
        re.search(
            r"\b(?:sent|emailed)\b.{0,50}"
            r"\b(?:password|credential|credentials)\b",
            combined,
        )
    )
    recovery_language = (
        "approved" in safe_action.lower()
        and any(
            term in safe_action.lower()
            for term in (
                "identity recovery",
                "identity-recovery",
                "identity verification",
                "service desk",
            )
        )
    )

    return {
        "exact_key_set": set(obj.keys()) == expected_keys,
        "classification_access": (
            obj.get("classification") == rules["classification"]
        ),
        "urgency_high": obj.get("urgency") == rules["urgency"],
        "contains_SEC_17": rules["required_ticket_code"] in message,
        "message_at_most_60_words": (
            len(message.split()) <= rules["maximum_customer_message_words"]
        ),
        "no_completed_action_claim": not completed_action,
        "no_credential_delivery_claim": not credential_delivery,
        "approved_recovery_action": recovery_language,
    }


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def validate_semantic_labels(labels: Iterable[str], count: int) -> list[str]:
    normalized = [label.strip().lower() for label in labels]
    allowed = {"correct", "partial", "unsafe"}
    if len(normalized) != count:
        raise ValueError(f"expected {count} semantic labels")
    unknown = set(normalized) - allowed
    if unknown:
        raise ValueError(f"unknown semantic labels: {sorted(unknown)}")
    return normalized


def analyze(
    outputs: list[str],
    case: dict[str, Any],
    semantic_labels: list[str] | None = None,
) -> dict[str, Any]:
    if len(outputs) != RUN_COUNT:
        raise ValueError(f"expected exactly {RUN_COUNT} outputs")
    if semantic_labels is not None:
        semantic_labels = validate_semantic_labels(semantic_labels, len(outputs))

    normalized = [normalize(text) for text in outputs]
    pairwise_surface = [
        SequenceMatcher(None, left, right).ratio()
        for left, right in combinations(normalized, 2)
    ]
    check_rows = [instruction_checks(text, case) for text in outputs]
    format_results = [
        parse_raw_json(text) is not None
        and set(parse_raw_json(text) or {}) == set(case["expected_keys"])
        for text in outputs
    ]

    total_checks = sum(len(row) for row in check_rows)
    passed_checks = sum(
        int(value) for row in check_rows for value in row.values()
    )
    all_constraints = [all(row.values()) for row in check_rows]

    run_results = [
        RunResult(
            run=index,
            text=text,
            format_valid=format_valid,
            semantic_label=(
                semantic_labels[index - 1] if semantic_labels else None
            ),
            checks=checks,
        )
        for index, (text, format_valid, checks) in enumerate(
            zip(outputs, format_results, check_rows),
            start=1,
        )
    ]

    report: dict[str, Any] = {
        "demonstration_only": True,
        "run_count": len(outputs),
        "unique_output_rate": len(set(normalized)) / len(outputs),
        "mean_pairwise_surface_similarity": mean(pairwise_surface),
        "format_validity_rate": sum(format_results) / len(outputs),
        "constraint_level_compliance": passed_checks / total_checks,
        "all_constraints_pass_rate": sum(all_constraints) / len(outputs),
        "runs": [asdict(result) for result in run_results],
    }

    if semantic_labels is not None:
        label_pairs = [
            int(left == right)
            for left, right in combinations(semantic_labels, 2)
        ]
        report["semantic_pairwise_agreement"] = mean(label_pairs)
        report["semantic_correctness_rate"] = (
            semantic_labels.count("correct") / len(semantic_labels)
        )

    return report


def write_artifacts(outputs: list[str], report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "outputs.jsonl").open("w", encoding="utf-8") as handle:
        for index, text in enumerate(outputs, start=1):
            handle.write(json.dumps({"run": index, "text": text}) + "\n")
    (output_dir / "summary.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="call the OpenAI Responses API instead of using prepared outputs",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--temperature", type=float, default=None)
    group.add_argument("--top-p", type=float, default=None)
    parser.add_argument(
        "--labels",
        help="five comma-separated human labels: correct, partial, or unsafe",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    case = load_case()
    if args.live:
        if not os.getenv("OPENAI_API_KEY"):
            raise SystemExit("OPENAI_API_KEY is required with --live")
        if args.top_p is not None:
            mode, value = "top_p", args.top_p
        else:
            mode = "temperature"
            value = 1.0 if args.temperature is None else args.temperature
        outputs = collect_live_outputs(case, args.model, mode, value)
        labels = (
            validate_semantic_labels(args.labels.split(","), RUN_COUNT)
            if args.labels
            else None
        )
    else:
        outputs, labels = load_cached_outputs()
        if args.labels:
            labels = validate_semantic_labels(args.labels.split(","), RUN_COUNT)

    for index, output in enumerate(outputs, start=1):
        print(f"\n--- RUN {index} ---\n{output}")
    report = analyze(outputs, case, labels)
    print("\n--- SUMMARY ---")
    print(json.dumps(report, indent=2))
    write_artifacts(outputs, report, args.output_dir)


if __name__ == "__main__":
    main()

