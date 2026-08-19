"""Validate the structure of a learner evidence pack without grading clinical truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_FILES = {
    "risk_map.json": ("top_risks", "blocking_rules", "selected_signals"),
    "candidate_review.json": ("reviews",),
    "experiment_plan.json": ("baseline", "candidate", "controlled_change"),
    "human_review.json": ("reviews", "reviewer_accountability"),
    "release_decision.json": ("decision", "blocking_evidence", "residual_risk"),
}


def validate(work_dir: Path) -> dict[str, object]:
    errors: list[str] = []
    evidence: dict[str, object] = {}
    for name, fields in REQUIRED_FILES.items():
        path = work_dir / name
        if not path.exists():
            errors.append(f"Missing {name}")
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{name} is invalid JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{name} must contain a JSON object")
            continue
        missing = [field for field in fields if field not in value]
        if missing:
            errors.append(f"{name} missing fields: {', '.join(missing)}")
        evidence[name] = value

    decision = evidence.get("release_decision.json")
    if isinstance(decision, dict) and decision.get("decision") not in {
        "RELEASE", "CONDITIONAL_RELEASE", "BLOCK"
    }:
        errors.append("release_decision.json decision must be RELEASE, CONDITIONAL_RELEASE, or BLOCK")

    candidate_review = evidence.get("candidate_review.json")
    if isinstance(candidate_review, dict):
        for index, review in enumerate(candidate_review.get("reviews", []), 1):
            if not isinstance(review, dict):
                errors.append(f"candidate review {index} must be an object")
                continue
            if review.get("decision") == "approved" and not all(
                review.get(field) for field in ("reviewer", "reason", "source_chunk_ids")
            ):
                errors.append(
                    f"candidate review {index} cannot be approved without reviewer, reason, and source_chunk_ids"
                )

    return {
        "status": "pass" if not errors else "fail",
        "work_dir": str(work_dir),
        "files_found": sorted(evidence),
        "errors": errors,
        "note": "Structural pass is not a clinical, metric-quality, or release approval.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_dir", type=Path)
    args = parser.parse_args()
    report = validate(args.work_dir)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
