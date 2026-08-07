# DeepEval evaluation of the payroll-MFA RAG

This document covers the DeepEval layer only. The RAG application remains in
`rag/`; the existing Ragas evaluator remains in `evaluation/`. DeepEval has its
own entry point, package, dependencies, outputs, and result prefixes:

```text
deepeval_app.py
deepeval_evaluation/
requirements-deepeval.txt
deepeval_evaluation/results/deepeval-*.json
deepeval_evaluation/results/deepeval-*.csv
```

No DeepEval command invokes Ragas, and no DeepEval score is written into a
`ragas_*` field.

## 1. Install one evaluation layer or both

DeepEval only:

```bash
python -m venv .venv
source .venv/bin/activate             # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-deepeval.txt
cp .env.example .env                  # Windows: Copy-Item .env.example .env
```

Ragas and DeepEval in the same environment:

```bash
pip install -r requirements-all-eval.txt
```

The verified combined environment uses DeepEval 4.1.5, Ragas 0.4.3, the
official Ollama Python client 0.6.2, and Python 3.12.13.

## 2. Understand the test-case mapping

`deepeval_evaluation/adapter.py` maps the already-saved RAG evidence into one
`LLMTestCase`:

| RAG and golden field | DeepEval field | Meaning |
|---|---|---|
| `trace.question` | `input` | User request |
| `trace.answer` | `actual_output` | RAG answer being tested |
| `case.reference` | `expected_output` | Human-approved ideal behavior |
| `trace.retrieved_contexts` | `retrieval_context` | Ordered evidence sent to generation |
| `case.case_id` | `name` and metadata | Stable result join key |

DeepEval does not run retrieval or generation itself. In live mode the existing
`RAGApplication` runs first. In trace mode DeepEval evaluates frozen evidence.

## 3. Configure the judge

Ollama:

```dotenv
DEEPEVAL_JUDGE_PROVIDER=ollama
DEEPEVAL_OLLAMA_BASE_URL=http://localhost:11434
DEEPEVAL_OLLAMA_MODEL=gemma3:4b
```

OpenAI:

```dotenv
OPENAI_API_KEY=replace-locally
DEEPEVAL_JUDGE_PROVIDER=openai
DEEPEVAL_OPENAI_MODEL=gpt-5.6
```

The RAG provider and judge provider are independent. A locally generated answer
can be evaluated by OpenAI, or an OpenAI-generated answer can be evaluated by a
local Ollama judge.

## 4. Preflight before a paid or long run

Import and construction check only:

```bash
python deepeval_app.py preflight --judge-provider ollama
```

One structured-output judge call:

```bash
python deepeval_app.py preflight --judge-provider ollama --live
python deepeval_app.py preflight --judge-provider openai --live
```

`--live` verifies the capability required by the LLM-based metrics. It does not
evaluate the eight-case dataset.

## 5. Run one case first

```bash
python deepeval_app.py run \
  --rag-provider ollama \
  --judge-provider ollama \
  --case-id MFA-001 \
  --top-k 3 \
  --metric-profile core \
  --show-answers \
  --show-reasons
```

The command performs this sequence:

1. Validate the golden case and its chunk IDs against the corpus.
2. Run the existing RAG for `MFA-001`.
3. Save the canonical RAG trace under `results/`.
4. Calculate exact ID/ranking and deterministic citation/policy metrics.
5. Create an `LLMTestCase` from the frozen trace.
6. Run the five DeepEval RAG metrics.
7. Save a DeepEval JSON and CSV report under `deepeval_evaluation/results/`.

## 6. Run all cases

Ollama end to end:

```bash
python deepeval_app.py run \
  --rag-provider ollama \
  --judge-provider ollama \
  --top-k 3 \
  --metric-profile core
```

OpenAI end to end:

```bash
python deepeval_app.py run \
  --rag-provider openai \
  --judge-provider openai \
  --top-k 3 \
  --metric-profile core
```

Independent hosted judge for a local RAG:

```bash
python deepeval_app.py run \
  --rag-provider ollama \
  --judge-provider openai \
  --top-k 3 \
  --metric-profile core
```

## 7. Core and full profiles

The core profile contains five framework-native RAG metrics:

| Metric | Primary surface | Inputs |
|---|---|---|
| Answer relevancy | Generator focus | input + actual output |
| Faithfulness | Generator grounding | actual output + retrieval context |
| Contextual precision | Retriever ordering | input + expected output + ranked context |
| Contextual recall | Retriever completeness | expected output + retrieval context |
| Contextual relevancy | Retriever noise | input + retrieval context |

The full profile adds `Policy Correctness [GEval]`, a use-case-specific judge
that compares the answer with the approved reference and penalizes unsafe
shortcuts, invented details, unsupported guarantees, and material omissions.

```bash
python deepeval_app.py run \
  --rag-provider ollama \
  --judge-provider openai \
  --metric-profile full
```

## 8. Evaluate a saved trace

```bash
python deepeval_app.py trace \
  --trace results/latest.json \
  --case-id MFA-001 \
  --judge-provider ollama \
  --metric-profile core
```

The question must exactly match the selected golden case. Use
`--allow-question-mismatch` only for a deliberate paraphrase experiment; it can
otherwise pair an answer with the wrong reference.

An offline sample trace is included so the deterministic report path can be
verified without an Ollama server or OpenAI key:

```bash
python deepeval_app.py trace \
  --trace deepeval_evaluation/data/sample_mfa001_trace.json \
  --case-id MFA-001 \
  --skip-deepeval \
  --show-answers
```

The file is explicitly marked as an offline sample. Its deterministic values
are reproducible, but it is not evidence of a live DeepEval semantic score.

## 9. Deterministic-only mode

Live RAG followed only by exact checks:

```bash
python deepeval_app.py run \
  --rag-provider ollama \
  --top-k 3 \
  --skip-deepeval
```

Completely model-free evaluation of an existing trace:

```bash
python deepeval_app.py trace \
  --trace results/latest.json \
  --case-id MFA-001 \
  --skip-deepeval
```

In this mode `deepeval_metrics` is empty, semantic attempts are zero, and the
CSV contains no `deepeval_<metric>` columns. It is useful for validating dataset
integrity, retrieval arithmetic, citations, required concepts, and forbidden
claims. It is not evidence that semantic evaluation passed.

## 10. Thresholds and exit codes

Every metric threshold defaults to `0.70` as an explicit diagnostic starting
point. This is not a validated release boundary. Calibrate each threshold
against human labels, analyze false passes/failures, and version the final values.

```dotenv
DEEPEVAL_THRESHOLD_ANSWER_RELEVANCY=0.70
DEEPEVAL_THRESHOLD_FAITHFULNESS=0.70
DEEPEVAL_THRESHOLD_CONTEXTUAL_PRECISION=0.70
DEEPEVAL_THRESHOLD_CONTEXTUAL_RECALL=0.70
DEEPEVAL_THRESHOLD_CONTEXTUAL_RELEVANCY=0.70
DEEPEVAL_THRESHOLD_POLICY_CORRECTNESS=0.70
```

By default a threshold failure is recorded but does not fail the process. Once
thresholds are calibrated, add `--enforce-thresholds` for CI:

```bash
python deepeval_app.py run \
  --rag-provider ollama \
  --judge-provider openai \
  --enforce-thresholds
```

Exit codes:

| Code | Meaning |
|---:|---|
| 0 | Run completed; no enforced failure |
| 1 | At least one DeepEval case failed and thresholds were enforced |
| 2 | Configuration, dataset, trace, or provider setup error |
| 3 | One or more metric executions failed |

`--allow-metric-errors` changes code 3 to 0 for exploratory work. It does not
convert errors into scores and must not be used to claim an evaluation passed.

## 11. Read the CSV correctly

Each row is one golden case. The important groups are:

- `retrieval_*`: deterministic ID/ranking mathematics shared with the Ragas run.
- `deterministic_*`: exact citation, concept, and forbidden-claim checks.
- `deepeval_<metric>`: judge score.
- `deepeval_<metric>_threshold`: threshold used for that score.
- `deepeval_<metric>_passed`: framework pass/fail result.
- `deepeval_<metric>_reason`: judge explanation.
- `deepeval_<metric>_error`: evaluator failure, not a quality score.

A blank score paired with an error must never be interpreted as zero. A low
numeric score means the judge completed and assessed poor quality. Those are
different failure classes and require different fixes.

## 12. Ragas and DeepEval are not interchangeable

Ragas remains useful for RAG-focused experiments, claim-level metrics, and
framework-specific score analysis. DeepEval adds a broader test abstraction,
metric thresholds, pass/fail semantics, Pytest-style use, custom G-Eval/DAG
criteria, and component or agent evaluation beyond RAG.

Even similarly named metrics are not numerically interchangeable. Their prompt
templates, decomposition steps, model adapters, retry behavior, and aggregation
details differ. Compare trends within one pinned framework and judge setup; do
not average Ragas and DeepEval scores or treat `0.8` from one as equivalent to
`0.8` from the other.
