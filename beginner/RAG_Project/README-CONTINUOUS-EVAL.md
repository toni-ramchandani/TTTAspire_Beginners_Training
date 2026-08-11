# Continuous RAG Evaluation: Measure, Analyse, Improve

This module extends the existing payroll-MFA RAG. It does not create a second application or a second policy corpus.

## What is implemented

- Four tagged production-like requests: approved canary, unfamiliar request, direct injection, and controlled indirect injection.
- Local canonical traces plus optional hosted LangSmith root, retrieval, and generation spans.
- Reference-free online checks for ordinary traffic.
- Approved-case contract checks only for approved canaries.
- Sampled DeepEval Answer Relevancy, Faithfulness, and policy G-Eval through local Ollama.
- Separate attack-attempt and unsafe-effect signals.
- A guaranteed synthetic failure for trace-level diagnosis.
- A human-review packet and a guarded `OBS-031` candidate-promotion command.
- A paste-ready LangSmith hosted code evaluator and an optional annotation-queue setup command.

The module does not calculate a blended quality score. It never labels the 22 review candidates as golden, and it never auto-promotes an observed trace into `evaluation/data/golden_cases.json`.

## Install

Use Python 3.11 or 3.12 in a fresh virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-continuous.txt
Copy-Item .env.example .env
```

Start Ollama and pull the configured generation, embedding, and judge models:

```powershell
ollama pull gemma3:4b
ollama pull embeddinggemma
```

## Reliable classroom sequence

### 1. Preflight

```powershell
python continuous_eval_app.py preflight
```

This checks the four traffic records, the failure fixture, the eight approved cases, and the optional dependency versions. It makes no model or hosted call.

### 2. Guaranteed failure diagnosis

```powershell
python continuous_eval_app.py fixture
```

Expected evidence:

```text
bounded_outcome: blocking_policy_failure_observed
required_context_recall: 1.0
unsafe_effect_observed: true
```

Both relevant policy chunks were retrieved. The synthetic answer still authorizes a manager-approved bypass. The primary diagnosis is therefore generation-policy, not retrieval.

### 3. Live local traffic

```powershell
python continuous_eval_app.py run `
  --rag-provider ollama `
  --top-k 3
```

This runs the real RAG and deterministic online checks. `LIVE-001` receives approved-canary metrics because it maps to `MFA-001`. `LIVE-002` to `LIVE-004` remain reference-free.

### 4. Add sampled semantic evaluation

```powershell
python continuous_eval_app.py run `
  --rag-provider ollama `
  --judge-provider ollama `
  --top-k 3 `
  --semantic `
  --semantic-sample-rate 1.0
```

The lab uses a sample rate of `1.0` because the traffic file contains only four synthetic requests. In production, canaries and security tests remain 100% selected while ordinary traffic uses stable risk-adjusted sampling.

### 5. Optional hosted trace and feedback

Review the endpoint, tracing project, content capture, retention, and expected evaluator cost first. Then:

```powershell
python continuous_eval_app.py run `
  --rag-provider ollama `
  --semantic `
  --hosted `
  --publish-feedback `
  --confirm-hosted
```

The command will fail closed without the explicit confirmation flag or a real `LANGSMITH_API_KEY`.

For a native LangSmith online project rule, follow `continuous_evaluation/LANGSMITH_UI_SETUP.md` and paste `langsmith_online_code_evaluator.py` into the hosted code-evaluator editor.

### 6. Human review and case 31

Copy `continuous_evaluation/data/review_packet_template.json`, complete the domain review, and change only reviewed fields. Then:

```powershell
python continuous_eval_app.py promote `
  --envelope continuous_evaluation/results/fixture_evaluation.json `
  --review path/to/completed_review.json `
  --case-id OBS-031
```

The output is still `candidate_requires_domain_approval`. Adding it to the governed offline dataset is a separate dataset-version decision.

## Report interpretation

| Evidence | Correct claim |
|---|---|
| Approved canary required-context recall | The deployed path retrieved the case-owned mandatory evidence |
| Ordinary-trace faithfulness | The answer is supported by retrieved context according to the configured judge |
| Ordinary-trace answer relevancy | The response addresses the question according to the configured judge |
| `attack_attempt_detected=true`, `unsafe_effect_observed=false` | An attack was observed; the configured output checks did not observe compromise |
| Regex pass | No configured literal pattern matched; semantic safety is not proven |
| Missing evaluator output | Evaluator execution failure, not a zero-quality model result |

Keep metric ownership explicit:

```text
ragas_*
deepeval_online_*
langsmith_feedback_*
human_*
```

Do not average those families together.

## Primary references

- LangSmith evaluation concepts: https://docs.langchain.com/langsmith/evaluation-concepts
- LangSmith online code evaluators: https://docs.langchain.com/langsmith/online-evaluations-code
- LangSmith online LLM-as-a-judge evaluators: https://docs.langchain.com/langsmith/online-evaluations-llm-as-judge
- LangSmith annotation queues: https://docs.langchain.com/langsmith/annotation-queues
- LangSmith trace-to-dataset workflow: https://docs.langchain.com/langsmith/manage-datasets-in-application
- Ragas Faithfulness: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/
- Ragas Response Relevancy: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/answer_relevance/
- Ragas Context Precision and Utilization: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/context_precision/
- DeepEval G-Eval: https://deepeval.com/docs/metrics-llm-evals
- Ollama Chat API: https://docs.ollama.com/api/chat
- OWASP LLM01 Prompt Injection: https://genai.owasp.org/llmrisk/llm01-prompt-injection/

Created by Toni Ramchandani  
https://www.linkedin.com/in/toni-ramchandani/
