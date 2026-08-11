# Outcome-driven section: dataset -> RAG diagnosis -> risk evidence

This section extends the existing RAG, Ragas, DeepEval, and LangSmith project. It does not import, copy, or require the separate core-metrics replay package.

## Outcomes

1. Build and validate a 30-row versioned teaching seed without mislabeling generated rows as golden.
2. Run selected rows through the actual RAG and separate retrieval, answer, citation, policy, and latency evidence.
3. Convert metric observations into bounded component diagnoses rather than one overall RAG score.
4. Execute safe direct-injection, controlled indirect-injection, and paired-behavior smoke tests over synthetic data.
5. Retain evidence that can support review, experiment, release, rollback, and future-regression decisions.

## Commands

```powershell
python section_app.py build-dataset
python section_app.py validate-dataset
```

Run a small deterministic live diagnostic set first:

```powershell
python section_app.py evaluate-rag `
  --rag-provider ollama `
  --top-k 3 `
  --skip-ragas `
  --case-id MFA-001 `
  --case-id MFA-002 `
  --case-id SEED-021 `
  --case-id SEED-028 `
  --case-id SEED-029 `
  --case-id SEED-030
```

Add the existing Ragas judge only after inspecting retrieval and exact-check failures:

```powershell
python section_app.py evaluate-rag `
  --rag-provider ollama `
  --judge-provider ollama `
  --top-k 3 `
  --metric-profile core `
  --case-id MFA-001 `
  --case-id MFA-002 `
  --case-id SEED-021 `
  --case-id SEED-028 `
  --case-id SEED-029 `
  --case-id SEED-030
```

Run the safe synthetic risk screen deliberately:

```powershell
python section_app.py risk-screen `
  --rag-provider ollama `
  --top-k 3 `
  --confirm-live
```

## Evidence interpretation

| Observation | Supported diagnosis | Primary action |
|---|---|---|
| Required chunk absent | Retrieval failure | Inspect index, chunking, query, ranking, top-k |
| Required chunk present; concept absent | Generation or prompt-assembly omission | Inspect assembled evidence and answer behavior |
| Forbidden policy rule matches | Blocking policy-output failure | Hold case; inspect trace and rule coverage |
| Expected citation absent | Attribution failure | Inspect citation instruction and retrieved IDs |
| Model-based metric errors | Evaluator execution failure | Fix judge/runtime; do not convert error to zero |
| High latency with correct evidence | Operational observation | Compare retrieval and generation spans before tuning |

The runner does not calculate one composite RAG score. Severe business-critical failures remain visible even when means improve.

## Boundaries

- The 22 generated rows require human promotion before being called golden.
- The risk suite has no real credentials, PII, external tools, or side effects.
- Controlled indirect-injection cases test the generation boundary with a fixed untrusted context; they do not claim end-to-end retrieval prevalence.
- Paired smoke tests can reveal inconsistent configured behavior but cannot prove fairness.
- Governance references inform evidence discipline; they do not turn the lab into a legal-compliance assessment.
