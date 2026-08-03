---
document_id: SEC-17
title: Payroll MFA Recovery Policy
version: 2.1
status: CURRENT
effective_date: 2026-07-01
owner: Identity and Access Management
classification: Synthetic training document
---

# Payroll MFA Recovery Policy

This fictional policy is supplied only for the workshop RAG application. It does not describe any real employer's controls.

## Purpose and scope

This policy applies when an employee cannot complete multi-factor authentication (MFA) for the employee payroll portal. It covers a replaced, lost, stolen, damaged, or reset authenticator device. A payroll password reset and an MFA recovery are separate operations; completing one does not automatically complete the other.

## Standard recovery workflow

The employee must contact the internal Help Desk through an approved corporate channel. The Help Desk first verifies identity, then revokes the unavailable authenticator, and finally starts device re-enrolment. The employee must complete the new enrolment before normal payroll access is restored. If any required verification fails, the Help Desk must stop the recovery and escalate the case.

## Identity verification

Before changing MFA, the Help Desk must verify the employee identifier and two approved factors from the identity record. Approved factors may include a callback to a registered corporate number, confirmation through the signed-in corporate device, or an in-person identity check. The technician must never request the employee's password, one-time passcode, full national identity number, or personal banking PIN.

## Device re-enrolment

After successful verification, the Help Desk revokes the old authenticator registration and issues a single-use enrolment link to the employee's corporate account. The link expires after 30 minutes and must not be forwarded. The employee registers the new device and completes a test sign-in. Recovery is complete only after the test sign-in succeeds.

## Payroll deadline fallback

If the employee has a payroll submission deadline within four hours and device re-enrolment cannot be completed, the Help Desk creates an urgent Payroll Support ticket. Payroll Support may help the employee submit the required payroll change through an approved assisted process after independently verifying the request. This fallback does not disable or bypass MFA and does not restore portal access.

## Prohibited shortcuts

A manager's approval is not a substitute for employee identity verification. Technicians and managers must not disable MFA, issue a shared recovery code, accept an OTP sent by the employee, redirect enrolment to a personal email address, or promise access before the test sign-in succeeds. Urgency does not remove these controls.

## Lost or stolen devices

When a device is reported lost or stolen, the old authenticator registration must be revoked as soon as identity is verified. The Help Desk records the loss in the ticket and advises the employee to report suspected device compromise to Security Operations. Security escalation is mandatory if the employee reports an unexpected MFA prompt, a suspicious sign-in, or possible disclosure of a recovery code.

## Service targets and uncertainty

During staffed hours, the Help Desk targets an initial response within 30 minutes for payroll-blocking MFA incidents. This is an operational target, not a guaranteed restoration time. Restoration depends on successful identity verification, provider availability, device readiness, and completion of the test sign-in. The documents do not establish a universal restoration SLA.
