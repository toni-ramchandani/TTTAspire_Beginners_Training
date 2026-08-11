"""Turn per-case metric evidence into bounded, actionable RAG diagnoses."""

from __future__ import annotations

from typing import Any

from .models import SeedCase


def diagnose_case(result: dict[str, Any], seed_case: SeedCase) -> dict[str, Any]:
    retrieval = result["retrieval_metrics"]
    deterministic = result["deterministic_metrics"]
    issues: list[dict[str, str]] = []

    if float(retrieval["required_context_recall_at_k"]) < 1.0:
        issues.append(
            {
                "component": "retrieval",
                "signal": "required context is absent from top-k",
                "action": "inspect query embedding, chunking, index content, ranking, and top-k",
                "value": "avoid changing the generation prompt for missing-evidence failures",
            }
        )
    elif float(retrieval["precision_at_k"]) < 1.0:
        issues.append(
            {
                "component": "retrieval",
                "signal": "required evidence is present with additional judged-irrelevant chunks",
                "action": "inspect ranking and context-budget use before increasing top-k",
                "value": "reduce distracting context without sacrificing required evidence",
            }
        )

    if float(deterministic["forbidden_claim_pass"]) < 1.0:
        issues.append(
            {
                "component": "generation-policy",
                "signal": "a prohibited policy claim matched an approved rule",
                "action": "hold the case, inspect the trace, and review prompt/rule coverage",
                "value": "prevent a severe policy regression from being hidden by averages",
            }
        )

    if float(deterministic["required_concept_coverage"]) < 1.0:
        component = (
            "generation-completeness"
            if float(retrieval["required_context_recall_at_k"]) == 1.0
            else "retrieval-or-generation"
        )
        issues.append(
            {
                "component": component,
                "signal": "one or more required answer concepts are missing",
                "action": "inspect retrieved evidence first, then prompt assembly and answer behavior",
                "value": "route the fix to the component supported by trace evidence",
            }
        )

    if float(deterministic["citation_recall"]) < 1.0:
        issues.append(
            {
                "component": "generation-attribution",
                "signal": "one or more expected evidence citations are missing",
                "action": "inspect citation instructions and whether the expected chunks were retrieved",
                "value": "retain auditable links between policy claims and source evidence",
            }
        )

    semantic_observations = {
        name: outcome.get("value")
        for name, outcome in result.get("ragas_metrics", {}).items()
        if outcome.get("value") is not None
    }
    metric_errors = {
        name: outcome.get("error")
        for name, outcome in result.get("ragas_metrics", {}).items()
        if outcome.get("error")
    }

    if not issues:
        bounded_outcome = "no_failure_observed_by_configured_exact_checks"
    elif any(item["component"] == "generation-policy" for item in issues):
        bounded_outcome = "blocking_policy_failure_observed"
    else:
        bounded_outcome = "diagnostic_issue_observed"

    return {
        "bounded_outcome": bounded_outcome,
        "business_critical": seed_case.business_critical,
        "scenario_type": seed_case.scenario_type,
        "review_status": seed_case.review_status,
        "issues": issues,
        "ragas_observations": semantic_observations,
        "ragas_metric_errors": metric_errors,
        "latency_observation_ms": result["trace"]["total_latency_ms"],
        "limitation": (
            "This diagnosis follows configured evidence rules. It is not proof of overall "
            "correctness, safety, fairness, or production readiness."
        ),
    }
