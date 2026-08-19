# MediGuide Medical RAG Evaluation Capstone

This is an isolated final assignment for the 10-day beginner LLM-evaluation course. It reuses the same RAG and evaluation architecture in a new medical patient-education domain without modifying the existing payroll/incident project.

MediGuide is intentionally not a diagnostic or treatment chatbot. Its fixed synthetic corpus covers adult patient education for emergency escalation, respiratory/antibiotic principles, and medicine-label/disposal safety. Real patient data is prohibited.

## Architecture

```text
versioned medical documents
  -> Markdown section chunks
  -> embeddings and vector index
  -> top-k retrieval
  -> grounded generation with chunk citations
  -> canonical trace
  -> exact checks + Ragas + DeepEval
  -> LangSmith experiment/trace/feedback
  -> human review
  -> controlled change and release decision
```

## Prepared assets

```text
documents/                              3 source-of-truth documents
evaluation/data/golden_cases.json       10 governed cases
evaluation/data/candidate_cases.jsonl   12 unapproved candidates
evaluation/data/risk_cases.jsonl        10 controlled risk cases
baseline/golden_reference_traces.jsonl  deterministic reference fixtures
assignment/LEARNER_ASSIGNMENT.md        complete learner brief
assignment/templates/                   evidence-pack templates
assignment/instructor/ANSWER_KEY.md      instructor-only key
capstone_precheck.py                     verifies prepared assets, no model calls
assignment_check.py                      validates learner-pack structure
```

The RAG, Ragas, DeepEval, and LangSmith modules are copied into this folder so the capstone is portable and cannot mutate the earlier project.

## Setup

Python 3.11 or 3.12 is recommended.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-all-eval.txt
cp .env.example .env           # Windows: Copy-Item .env.example .env
```

For local Ollama:

```bash
ollama pull gemma3:4b
ollama pull embeddinggemma
```

## Start with the pre-check

```bash
python capstone_precheck.py --output output/precheck.json
python app.py inspect
pytest -q
```

The pre-check evaluates curated reference fixtures only. It must not be reported as the live model baseline.

## Run the application

```bash
python app.py build --provider ollama
python app.py ask "Do antibiotics help an ordinary cold?" --provider ollama --top-k 3 --show-context
```

## Ragas experiment

```bash
python eval_app.py preflight --judge-provider ollama
python eval_app.py run --rag-provider ollama --judge-provider ollama --top-k 3 --metric-profile full --show-answers
```

## DeepEval experiment

```bash
python deepeval_app.py preflight --judge-provider ollama
python deepeval_app.py run --rag-provider ollama --judge-provider ollama --top-k 3 --metric-profile full --show-answers
```

The full profile includes a narrow `Medical Safety and Scope` G-Eval criterion in addition to RAG metrics. Its default threshold is a diagnostic starting point, not a clinical release threshold.

## LangSmith

Local evaluation does not upload results:

```bash
python langsmith_app.py preflight
python langsmith_app.py run --rag-provider ollama --top-k 3 --metric-profile full --experiment-prefix mediguide-local-baseline
```

Hosted synchronization and experiments are separate external writes. Confirm the endpoint, workspace, dataset name, content-retention policy, and absence of patient data before running:

```bash
python langsmith_app.py run --rag-provider ollama --top-k 3 --metric-profile full --hosted --sync-dataset --confirm-hosted --experiment-prefix mediguide-baseline-top3
```

The default hosted dataset is `medical-education-rag-golden-v1`; it is not the earlier payroll dataset.

## Learner work folder

Copy, do not edit, the templates:

```bash
mkdir learner_work
cp assignment/templates/*.json learner_work/
cp assignment/templates/*.csv learner_work/
```

Validate the structure before submission:

```bash
python assignment_check.py learner_work
```

This check validates structure and authority fields. It does not grade medical truth, evaluator quality, or the release decision.

## Safety and limitations

- Synthetic education and evaluation only; not for diagnosis, treatment, or deployment
- No real patient data in prompts, traces, datasets, reports, or hosted tools
- Small English-only dataset with no demonstrated fairness or clinical validity
- Human clinical/safety review remains mandatory at dataset, evaluator, incident, and release gates
- A blocking unsafe case overrides improved aggregate scores
