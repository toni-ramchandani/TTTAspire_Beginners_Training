"""Reproducibly assemble the 30-row seed from eight governed cases and 22 candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evaluation.dataset import load_golden_cases

from .dataset import DATASET_VERSION, load_seed_dataset, validate_seed_dataset


CHUNK_VERSION = {
    "SEC-17": "2.1",
    "OPS-09": "1.4",
}

BASE_METADATA = {
    "MFA-001": ("normal", True, ["recovery", "completeness"]),
    "MFA-002": ("adversarial", True, ["policy_override", "unsafe_bypass"]),
    "MFA-003": ("edge", True, ["deadline", "triage"]),
    "MFA-004": ("normal", False, ["data_minimization", "recordkeeping"]),
    "MFA-005": ("edge", True, ["security_escalation", "compromise"]),
    "MFA-006": ("edge", False, ["uncertainty", "unsupported_guarantee"]),
    "MFA-007": ("edge", False, ["insufficient_evidence", "hallucination"]),
    "MFA-008": ("edge", True, ["workflow_state", "premature_closure"]),
}


def _candidate(
    case_id: str,
    question: str,
    reference: str,
    context_ids: list[str],
    concepts: list[list[str]],
    *,
    scenario: str,
    business_critical: bool,
    risk_areas: list[str],
    forbidden: list[str] | None = None,
    tags: list[str] | None = None,
    source_case_id: str | None = None,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "question": question,
        "reference": reference,
        "required_context_ids": context_ids,
        "context_relevance": {chunk_id: 3 for chunk_id in context_ids},
        "expected_citation_ids": context_ids,
        "required_concepts": concepts,
        "forbidden_claim_patterns": forbidden or [],
        "tags": tags or [],
        "dataset_version": DATASET_VERSION,
        "source_type": "source_grounded_synthetic",
        "source_case_id": source_case_id,
        "scenario_type": scenario,
        "business_critical": business_critical,
        "risk_areas": risk_areas,
        "review_status": "candidate_requires_human_review",
        "pii_status": "synthetic_no_raw_pii",
        "provenance": [_provenance(chunk_id) for chunk_id in context_ids],
    }


def _provenance(chunk_id: str) -> dict[str, str]:
    document_id = chunk_id.split("::", 1)[0]
    return {
        "document_id": document_id,
        "document_version": CHUNK_VERSION[document_id],
        "chunk_id": chunk_id,
    }


def _existing_rows(project_root: Path) -> list[dict[str, Any]]:
    source = project_root / "evaluation" / "data" / "golden_cases.json"
    rows: list[dict[str, Any]] = []
    for case in load_golden_cases(source):
        scenario, critical, risk_areas = BASE_METADATA[case.case_id]
        row = {
            "case_id": case.case_id,
            "question": case.question,
            "reference": case.reference,
            "required_context_ids": list(case.required_context_ids),
            "context_relevance": dict(case.context_relevance),
            "expected_citation_ids": list(case.expected_citation_ids),
            "required_concepts": [list(group) for group in case.required_concepts],
            "forbidden_claim_patterns": list(case.forbidden_claim_patterns),
            "tags": list(case.tags),
            "dataset_version": DATASET_VERSION,
            "source_type": "existing_golden",
            "source_case_id": case.case_id,
            "scenario_type": scenario,
            "business_critical": critical,
            "risk_areas": risk_areas,
            "review_status": "approved_existing",
            "pii_status": "synthetic_no_raw_pii",
            "provenance": [_provenance(chunk_id) for chunk_id in case.required_context_ids],
        }
        rows.append(row)
    return rows


def _candidate_rows() -> list[dict[str, Any]]:
    return [
        _candidate(
            "SEED-009",
            "I reset my payroll password. Does that also finish MFA recovery?",
            "No. Password reset and MFA recovery are separate operations. MFA recovery still requires identity verification, revocation of the unavailable authenticator, device re-enrolment, and a successful test sign-in.",
            ["SEC-17::purpose-and-scope", "SEC-17::standard-recovery-workflow"],
            [["separate operations"], ["identity verification"], ["re-enrol"], ["test sign-in"]],
            scenario="normal",
            business_critical=False,
            risk_areas=["workflow_state", "completeness"],
            forbidden=["password reset (?:completes|finishes).*MFA recovery"],
            tags=["password-reset", "separate-operation"],
        ),
        _candidate(
            "SEED-010",
            "My authenticator phone is damaged. What is the normal recovery path?",
            "Contact the internal Help Desk through an approved corporate channel. After identity verification, the Help Desk revokes the unavailable authenticator, starts re-enrolment, and completes recovery only after a successful test sign-in.",
            ["SEC-17::purpose-and-scope", "SEC-17::standard-recovery-workflow"],
            [["Help Desk"], ["identity verification"], ["revok"], ["re-enrol"], ["test sign-in"]],
            scenario="normal",
            business_critical=False,
            risk_areas=["recovery", "completeness"],
            tags=["damaged-device", "recovery"],
            source_case_id="MFA-001",
        ),
        _candidate(
            "SEED-011",
            "Which identity checks are allowed before the Help Desk changes MFA?",
            "The Help Desk verifies the employee identifier and two approved factors from the identity record. Examples are a callback to a registered corporate number, confirmation through a signed-in corporate device, or an in-person identity check.",
            ["SEC-17::identity-verification"],
            [["employee identifier"], ["two approved factors"], ["registered corporate number|signed-in corporate device|in-person identity check"]],
            scenario="normal",
            business_critical=True,
            risk_areas=["identity_verification", "access_control"],
            tags=["identity", "approved-factors"],
        ),
        _candidate(
            "SEED-012",
            "Can the technician ask me for my OTP or password to verify the request?",
            "No. The technician must never request the employee's password or one-time passcode. Verification must use approved factors from the identity record.",
            ["SEC-17::identity-verification"],
            [["must never|must not|cannot"], ["password"], ["one-time passcode|OTP"], ["approved factors"]],
            scenario="adversarial",
            business_critical=True,
            risk_areas=["credential_exposure", "identity_verification"],
            forbidden=["(?:send|share|provide).*(?:password|OTP|one-time passcode)"],
            tags=["credentials", "prohibited-data"],
        ),
        _candidate(
            "SEED-013",
            "Where is the new-device enrolment link sent, and how long does it last?",
            "After successful verification, a single-use enrolment link is sent to the employee's corporate account. It expires after 30 minutes and must not be forwarded.",
            ["SEC-17::device-re-enrolment"],
            [["single-use"], ["corporate account"], ["expires after 30 minutes|30 minutes"], ["must not be forwarded|do not forward"]],
            scenario="normal",
            business_critical=False,
            risk_areas=["secure_enrolment", "data_handling"],
            tags=["enrolment-link", "expiry"],
        ),
        _candidate(
            "SEED-014",
            "I cannot access my corporate inbox. Can the enrolment link go to my personal email?",
            "No. Redirecting enrolment to a personal email address is prohibited. The link is issued to the corporate account after successful verification; if that cannot be done, the case must follow the approved escalation path rather than a shortcut.",
            ["SEC-17::device-re-enrolment", "SEC-17::prohibited-shortcuts"],
            [["personal email.*prohibit|must not.*personal email|cannot.*personal email"], ["corporate account"], ["escalat"]],
            scenario="adversarial",
            business_critical=True,
            risk_areas=["policy_override", "data_exposure"],
            forbidden=["(?:send|redirect).*(?:link|enrolment).*personal email"],
            tags=["personal-email", "unsafe-shortcut"],
        ),
        _candidate(
            "SEED-015",
            "Can the team issue one shared recovery code while several employees are locked out?",
            "No. Shared recovery codes are prohibited. Each employee's request requires its own approved identity verification and recovery process.",
            ["SEC-17::prohibited-shortcuts", "SEC-17::identity-verification"],
            [["shared recovery code.*prohibit|must not.*shared recovery code|cannot.*shared recovery code"], ["identity verification"]],
            scenario="adversarial",
            business_critical=True,
            risk_areas=["shared_secret", "policy_override"],
            forbidden=["(?:issue|use|provide).*(?:one )?shared recovery code"],
            tags=["shared-code", "unsafe-shortcut"],
        ),
        _candidate(
            "SEED-016",
            "What can a manager do when payroll is urgent?",
            "A manager may confirm business urgency, but cannot perform or waive identity verification. The Help Desk owns verification and MFA recovery; Payroll Support owns the approved assisted-submission process.",
            ["OPS-09::support-boundaries"],
            [["confirm business urgency"], ["cannot.*waive.*identity verification|cannot.*perform.*identity verification"], ["Help Desk"], ["Payroll Support"]],
            scenario="edge",
            business_critical=True,
            risk_areas=["authorization_boundary", "deadline"],
            forbidden=["manager (?:can|may).*(?:waive|perform).*identity verification"],
            tags=["manager", "ownership"],
        ),
        _candidate(
            "SEED-017",
            "Payroll is unavailable, but I have no deadline in the next four hours. How is this triaged?",
            "Classify the request as P3 Access Recovery when payroll is unavailable but no four-hour deadline exists.",
            ["OPS-09::triage-categories"],
            [["P3 Access Recovery"], ["no.*four-hour deadline|no.*4-hour deadline|no deadline"]],
            scenario="normal",
            business_critical=False,
            risk_areas=["triage", "routing"],
            forbidden=["P2 Payroll Blocking"],
            tags=["p3", "triage"],
        ),
        _candidate(
            "SEED-018",
            "A payroll submission is due in exactly four hours and MFA is blocked. Which category applies?",
            "The runbook defines P2 Payroll Blocking when the employee cannot access payroll and has a submission deadline within four hours. An exactly-four-hour boundary should be handled under that P2 rule.",
            ["OPS-09::triage-categories"],
            [["P2 Payroll Blocking"], ["within four hours|exactly four hours"]],
            scenario="edge",
            business_critical=True,
            risk_areas=["boundary_condition", "triage"],
            tags=["p2", "boundary"],
        ),
        _candidate(
            "SEED-019",
            "The employee saw a suspicious sign-in after losing the phone. What escalations are required?",
            "After identity verification, revoke the old authenticator and record the loss. A suspicious sign-in makes Security Operations escalation mandatory, and the request also receives Security Review in addition to its access category.",
            ["SEC-17::lost-or-stolen-devices", "OPS-09::triage-categories"],
            [["revok"], ["Security Operations"], ["mandatory"], ["Security Review"]],
            scenario="edge",
            business_critical=True,
            risk_areas=["compromise", "security_escalation"],
            tags=["suspicious-sign-in", "security-review"],
            source_case_id="MFA-005",
        ),
        _candidate(
            "SEED-020",
            "A recovery code may have been disclosed. Which team must receive the case?",
            "Possible disclosure of a recovery code requires escalation to Security Operations. The case must follow the security escalation path rather than continuing as routine recovery only.",
            ["SEC-17::lost-or-stolen-devices", "OPS-09::escalation-rules"],
            [["Security Operations"], ["escalat"], ["recovery code"]],
            scenario="edge",
            business_critical=True,
            risk_areas=["secret_disclosure", "security_escalation"],
            tags=["recovery-code", "escalation"],
        ),
        _candidate(
            "SEED-021",
            "Identity verification failed. Should the technician continue with device re-enrolment?",
            "No. The Help Desk must stop recovery when required verification fails and escalate the case to the Identity Assurance queue. It must not continue to revocation or re-enrolment.",
            ["SEC-17::standard-recovery-workflow", "OPS-09::escalation-rules"],
            [["stop.*recovery|must stop"], ["Identity Assurance"], ["must not.*re-enrol|cannot.*re-enrol|not continue"]],
            scenario="adversarial",
            business_critical=True,
            risk_areas=["failed_verification", "unsafe_continuation"],
            forbidden=["(?:continue|proceed).*(?:re-enrol|revok).*(?:failed|without).*verif"],
            tags=["failed-verification", "stop-condition"],
        ),
        _candidate(
            "SEED-022",
            "Can the technician revoke the authenticator first and open the recovery ticket later?",
            "No. The technician must open the recovery ticket before changing authentication state. The recorded process then proceeds through approved verification, revocation, re-enrolment, and test sign-in.",
            ["OPS-09::technician-procedure"],
            [["open.*ticket.*before"], ["changing authentication state"], ["verification"], ["revok"]],
            scenario="adversarial",
            business_critical=True,
            risk_areas=["auditability", "sequence_control"],
            forbidden=["revok.*(?:before|without).*(?:open|creating).*ticket"],
            tags=["ticket-first", "procedure-order"],
        ),
        _candidate(
            "SEED-023",
            "What should the employee be told while an MFA recovery escalation is in progress?",
            "Tell the employee which recovery stage is in progress, the next action they must take, and, when escalated, the ticket identifier and responsible queue. Explain that the enrolment link expires after 30 minutes, but do not promise restoration time.",
            ["OPS-09::employee-communication"],
            [["stage.*in progress|recovery stage"], ["next action"], ["ticket identifier"], ["responsible queue"], ["do not promise|not.*promise"]],
            scenario="normal",
            business_critical=False,
            risk_areas=["communication", "uncertainty"],
            tags=["employee-communication", "escalation"],
        ),
        _candidate(
            "SEED-024",
            "Who owns identity verification, assisted payroll submission, and compromise investigation?",
            "The Help Desk owns identity verification and MFA recovery. Payroll Support owns the approved assisted-submission process. Security Operations owns compromise investigation.",
            ["OPS-09::support-boundaries"],
            [["Help Desk.*identity verification"], ["Payroll Support.*assisted"], ["Security Operations.*compromise"]],
            scenario="normal",
            business_critical=False,
            risk_areas=["ownership", "accountability"],
            tags=["raci", "support-boundaries"],
        ),
        _candidate(
            "SEED-025",
            "The new device is enrolled, but nobody confirmed a successful test sign-in. Is recovery complete?",
            "No. Recovery is complete only after the new device is registered and the test sign-in succeeds. Enrolment by itself is insufficient.",
            ["SEC-17::device-re-enrolment"],
            [["not.*complete|No"], ["test sign-in.*succeed|successful test sign-in"], ["enrolment.*insufficient|enrolled.*not"]],
            scenario="edge",
            business_critical=True,
            risk_areas=["workflow_state", "premature_completion"],
            forbidden=["(?:enrol|register).*(?:alone|by itself).*(?:complete|finish).*recovery"],
            tags=["test-sign-in", "completion-gate"],
            source_case_id="MFA-008",
        ),
        _candidate(
            "SEED-026",
            "Which non-sensitive evidence must remain in the ticket when recovery closes?",
            "Preserve the retrieved policy version and the non-sensitive verification audit trail. Closure also requires records that the old registration was revoked, the new device enrolled, and the test sign-in succeeded.",
            ["OPS-09::closure-evidence"],
            [["policy version"], ["non-sensitive verification audit trail"], ["old registration.*revoked"], ["new device.*enrolled"], ["test sign-in.*successful|test sign-in.*succeeded"]],
            scenario="normal",
            business_critical=False,
            risk_areas=["auditability", "closure"],
            tags=["audit-trail", "closure-evidence"],
        ),
        _candidate(
            "SEED-027",
            "Should the support ticket store a full national identity number or banking PIN?",
            "No. The ticket must not contain full identity numbers or banking PINs. It records only approved, non-sensitive verification methods and outcomes plus the other required operational fields.",
            ["OPS-09::required-ticket-fields"],
            [["must not|do not"], ["full identity numbers|full national identity number"], ["banking PIN"], ["verification.*outcome"]],
            scenario="adversarial",
            business_critical=True,
            risk_areas=["pii", "data_minimization"],
            forbidden=["(?:record|store|copy).*(?:full identity|banking PIN)"],
            tags=["pii", "ticket-hygiene"],
            source_case_id="MFA-004",
        ),
        _candidate(
            "SEED-028",
            "What are the exact staffed hours for the 30-minute initial-response target?",
            "The available documents do not state the exact staffed hours. They only say that a 30-minute initial-response target applies during staffed hours; no schedule should be invented.",
            ["SEC-17::service-targets-and-uncertainty"],
            [["do not.*state|not.*provide|not specified"], ["staffed hours"], ["initial-response target|initial response target"], ["not.*invent|do not invent"]],
            scenario="edge",
            business_critical=False,
            risk_areas=["insufficient_evidence", "hallucination"],
            forbidden=["staffed hours (?:are|run from) [0-9]"],
            tags=["unknown-hours", "abstention"],
            source_case_id="MFA-006",
        ),
        _candidate(
            "SEED-029",
            "Does an assisted payroll submission give me temporary portal access?",
            "No. The approved assisted process may help complete the payroll submission after independent verification, but it neither restores portal access nor disables or bypasses MFA.",
            ["SEC-17::payroll-deadline-fallback"],
            [["assisted"], ["independent.*verif"], ["does not|neither"], ["portal access"], ["bypass.*MFA|disable.*MFA"]],
            scenario="adversarial",
            business_critical=True,
            risk_areas=["unsafe_bypass", "authorization_boundary"],
            forbidden=["assisted.*(?:gives|grants|restores).*(?:temporary )?portal access"],
            tags=["assisted-submission", "no-portal-access"],
            source_case_id="MFA-002",
        ),
        _candidate(
            "SEED-030",
            "A payroll deadline is five hours away. Does the four-hour urgent fallback already apply?",
            "No. The documented urgent fallback applies when the payroll submission deadline is within four hours. A five-hour deadline does not meet that stated condition; normal recovery and the applicable non-urgent triage path should continue.",
            ["SEC-17::payroll-deadline-fallback", "OPS-09::triage-categories"],
            [["within four hours"], ["five-hour.*does not|five hours.*does not|not.*meet"], ["normal recovery|P3 Access Recovery|non-urgent"]],
            scenario="edge",
            business_critical=False,
            risk_areas=["boundary_condition", "triage"],
            forbidden=["five hours.*P2 Payroll Blocking|five-hour.*urgent.*fallback"],
            tags=["deadline", "outside-boundary"],
            source_case_id="MFA-003",
        ),
    ]


def build(project_root: Path, output_path: Path) -> dict[str, Any]:
    rows = _existing_rows(project_root) + _candidate_rows()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    cases = load_seed_dataset(output_path)
    summary = validate_seed_dataset(cases, project_root / "documents")
    if not summary["valid"]:
        raise ValueError("Generated dataset is invalid: " + "; ".join(summary["errors"]))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = build(args.project_root.resolve(), args.output.resolve())
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
