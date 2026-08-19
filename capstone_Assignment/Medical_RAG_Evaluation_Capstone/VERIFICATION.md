# Verification Record

Verified on 2026-08-18.

## Completed without model or hosted calls

- `python capstone_precheck.py --output output/precheck.json`
  - 3 documents, 18 stable chunks
  - 10 governed cases, 12 candidates, 10 risk cases
  - 10/10 curated reference fixtures passed deterministic checks
- `pytest -q`
  - 11 focused tests passed
- `python app.py inspect`
  - all expected chunk IDs listed
- `python eval_app.py list-cases`
  - MED-001 through MED-010 loaded
- Ragas 0.4.3 preflight
  - adapter initialized, no live call
- DeepEval 4.1.5 preflight
  - adapter initialized, no live call
- LangSmith 0.10.17 local preflight
  - 10 cases, separate dataset/project names, no hosted access
- One saved MED-001 fixture evaluated through both the Ragas and DeepEval CLIs with semantic judges deliberately skipped

## PDF verification

- 26 A4 pages
- all pages rendered to PNG and visually reviewed
- embedded DejaVu fonts
- no empty, clipped, or overflow pages found
- source links and internal content checked

## Deliberately not claimed

- No live Ollama or OpenAI generation was run in this environment.
- No live Ragas or DeepEval judge score was produced.
- No hosted LangSmith dataset, trace, feedback, or experiment was created.
- No clinical validation or deployment suitability is claimed.

Those are intentional learner tasks and require the learner's configured runtime, approved hosted access, and human domain/safety review.
