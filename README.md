# Aspire Systems — LLM Evaluation Training

Trainer-ready, evidence-backed learning assets for the Aspire Systems LLM
Evaluation curriculum.

## Current module

- [`beginner/day-01/index.html`](beginner/day-01/index.html) — standalone
  Technical Story Engine for **GenAI & LLM Foundations for QA**.
- [`beginner/day-01/lab/`](beginner/day-01/lab/) — runnable five-run variance
  lab with an offline fallback and deterministic tests.

The HTML is dependency-free and can be opened directly in a browser. The lab
supports Python 3.11+.

Both teaching assets follow the same Maya–Arun incident spine: incident →
request evidence → sampling hypothesis → source map → oracle design → workflow
trace → evidence contract → five-run investigation → release verdict. Each HTML
scene contains the same story beat and supporting resources as the narration.

## Delivery boundary

Day 1 introduces testing-relevant tokenization, sampling, system variability,
test oracles and QA failure surfaces. It deliberately does not teach DeepEval,
Ragas, LLM-as-a-judge, production statistics or transformer architecture.
The runnable lab also does not claim to implement retrieval or execute tools;
those are taught as explicit production evidence surfaces.
