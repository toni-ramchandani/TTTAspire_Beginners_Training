---
document_id: OPS-09
title: Payroll MFA Help-Desk Runbook
version: 1.4
status: CURRENT
effective_date: 2026-07-01
owner: Payroll Support Operations
classification: Synthetic training document
---

# Payroll MFA Help-Desk Runbook

This fictional runbook is supplied only for the workshop RAG application. It converts the SEC-17 policy into an operational support procedure.

## Triage categories

Classify an MFA request as `P2 Payroll Blocking` when the employee cannot access payroll and has a submission deadline within four hours. Classify it as `P3 Access Recovery` when payroll is unavailable but no four-hour deadline exists. Use `Security Review` in addition to the access category when the device is stolen, an unexpected MFA prompt occurred, or compromise is suspected.

## Required ticket fields

Record the employee identifier, corporate contact channel, affected payroll function, deadline if any, device-loss status, verification methods attempted, verification outcome, old-authenticator revocation status, re-enrolment outcome, retrieved policy version, and every escalation made. Do not copy passwords, OTP values, full identity numbers, banking PINs, or recovery secrets into the ticket.

## Technician procedure

Open the recovery ticket before changing authentication state. Confirm the request through an approved corporate channel, perform the two-factor identity check defined by SEC-17, record only the verification method and outcome, revoke the old registration, send the single-use enrolment link to the corporate account, and observe or confirm a successful test sign-in. If a step fails, record the failure and follow the escalation rules instead of improvising a shortcut.

## Escalation rules

Escalate failed identity verification to the Identity Assurance queue. Escalate a payroll deadline within four hours to Payroll Support after creating the recovery ticket. Escalate suspicious prompts, stolen devices with compromise indicators, or exposed recovery codes to Security Operations. A payroll escalation may enable an assisted payroll submission, but it must not be described as temporary portal access.

## Employee communication

Tell the employee which recovery stage is in progress, what action they must take next, and that the enrolment link expires after 30 minutes. If an escalation is required, provide the ticket identifier and the responsible queue. Do not promise a restoration time. State that the 30-minute figure is an initial-response target during staffed hours, not an access-restoration guarantee.

## Closure evidence

Close the MFA recovery only after recording the old registration as revoked, the new device as enrolled, and the test sign-in as successful. An assisted payroll submission may close the urgent payroll task but does not close an unfinished MFA recovery. Preserve the policy version and the non-sensitive verification audit trail in the ticket.

## Support boundaries

The Help Desk owns identity verification, authenticator revocation, re-enrolment, and the recovery ticket. Payroll Support owns the approved assisted-submission process. Security Operations owns compromise investigation. A manager may confirm business urgency but cannot perform or waive identity verification.
