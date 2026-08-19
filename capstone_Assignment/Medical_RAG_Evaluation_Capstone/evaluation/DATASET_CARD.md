# MediGuide Golden Dataset Card

## Purpose

`medical-education-golden-v1` is a governed ten-case evaluation contract for a synthetic adult patient-education RAG. It tests retrieval, grounded generation, citation integrity, safe scope, emergency escalation, antibiotic education, and medicine-safety boundaries.

## Authority

The three versioned Markdown documents in `documents/` are the fixed application source of truth for this assignment. They summarize cited CDC, FDA, MedlinePlus, and WHO material but are not a clinical guideline or a deployable medical product. The reference answers were derived from those documents and must be reviewed by a qualified domain/safety reviewer before any real-world use.

## Status

- 10 cases are pre-approved for the classroom baseline.
- 12 rows in `candidate_cases.jsonl` are not golden cases.
- Learners may propose additions but code cannot confer clinical approval.
- Real patient data is prohibited.

## Required review fields for promotion

`candidate_id`, final `case_id`, question, reference, source document version, supporting chunk IDs, required concepts, forbidden claims, risk slice, reviewer identity, decision, reason, and review timestamp.

## Known limits

The dataset is small, English-only, adult-oriented, synthetic, and deliberately narrow. It does not establish clinical safety, demographic fairness, product-specific medicine correctness, or suitability for deployment.
