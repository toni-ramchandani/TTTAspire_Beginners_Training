# Payroll MFA Evaluation Seed v1.0.0

## Purpose

This dataset supports a teaching workflow for evaluation-dataset construction, component-level RAG diagnosis, and basic AI risk screening. It belongs to the synthetic payroll-MFA RAG project and contains no production customer records.

## Composition

- 30 rows in `data/eval_seed_v1.jsonl`
- 8 existing governed `MFA-*` cases with status `approved_existing`
- 22 source-grounded `SEED-*` candidates with status `candidate_requires_human_review`
- 10 normal, 12 edge, and 8 adversarial scenarios
- 18 rows marked business-critical
- Source corpus: `SEC-17` version 2.1 and `OPS-09` version 1.4

Thirty rows are sufficient for a teaching seed dataset. They are not sufficient to claim production coverage, statistical representativeness, or a mature golden dataset.

## Unit of evaluation

Each row represents one user question and its expected evidence contract:

- reference answer;
- required chunk IDs and relevance grades;
- expected citation IDs;
- required answer concepts;
- forbidden policy-claim patterns;
- source, provenance, slice, risk, review, and PII metadata.

The reference is not treated as the only valid wording. Exact string match is not the default correctness oracle.

## Sources and generation

The eight `MFA-*` rows come from the existing governed project dataset. The 22 `SEED-*` rows are controlled, source-grounded variations authored from the two synthetic policy documents. No row was derived from a production log. Synthetic origin is retained explicitly so learners can distinguish generated coverage from observed production demand.

## Review and promotion

Only the eight existing cases retain approved status. A generated candidate becomes golden only after a responsible human reviewer confirms:

1. the question represents a meaningful product behavior;
2. the reference is supported by the cited source version;
3. required and forbidden rules are correct and not over-broad;
4. the slice and severity metadata are justified;
5. the row contains no raw sensitive data;
6. the review decision and reviewer identity are recorded outside this synthetic artifact.

The supplied validator must not auto-promote candidates.

## Hygiene controls

`section_app.py validate-dataset` checks row count, required metadata, unique IDs and normalized questions, allowed enum values, source-chunk existence, provenance completeness, PII-like values, and required slice presence. Near-duplicate detection is a review warning rather than an automatic deletion rule because intentional paraphrases may be useful.

## Known gaps

- No production-log distribution, frequency, or failure prevalence
- No multilingual or accessibility slice
- No real user-language noise beyond controlled variations
- No independently double-annotated labels or inter-rater agreement
- No observed post-deployment failures
- No evidence that 30 rows cover the full payroll-MFA policy space
- Deterministic regular expressions can miss unsafe paraphrases or create false positives

## Intended use

Use the seed to teach dataset governance, run selected RAG experiments, inspect trace evidence, compare controlled changes, and create a review queue. Do not use it as compliance certification, a fairness benchmark, a legal assessment, or a production release gate without additional review and coverage work.

## Versioning

Dataset version: `payroll-mfa-eval-seed-v1.0.0`

- Major: schema or label-semantics change
- Minor: reviewed coverage added without changing existing semantics
- Patch: metadata or non-semantic correction

Any source-policy version change requires affected rows to be revalidated before reuse.
