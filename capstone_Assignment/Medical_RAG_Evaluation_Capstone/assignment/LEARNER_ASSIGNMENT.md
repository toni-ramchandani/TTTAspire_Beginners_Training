# Final Assignment: Evaluate MediGuide Before Release

## Scenario

Your team inherits `MediGuide`, a synthetic adult patient-education RAG. The application answers only from three approved documents covering scope and escalation, respiratory/antibiotic education, and medicine safety. Ten cases are already governed. Twelve more are candidates, not gold labels.

Your task is to evaluate a release candidate and defend one decision: `RELEASE`, `CONDITIONAL_RELEASE`, or `BLOCK`. A block can be the strongest answer when the evidence supports it.

## What is already complete

- RAG ingestion, chunking, embeddings, retrieval, grounded generation, citations, and trace persistence
- Three fixed source documents and stable chunk IDs
- Ten governed golden cases with reference answers, required evidence, required concepts, forbidden claims, and risk tags
- Ten human-curated reference traces for a dependency-free pre-check
- Ragas, DeepEval, and LangSmith adapters
- Twelve candidate questions and ten risk cases
- Templates for dataset review, calibration, human review, experiments, and release evidence

Do not rewrite the RAG or replace the source documents. Do not modify the ten governed cases. Do not use real patient data.

## Required work

### 1. Establish the evaluation objective

Define the five most important product risks. Include at least one each for retrieval, grounded generation, medical safety/scope, prompt injection, and operations/human review. Map each risk to an observable signal and state whether it is blocking or diagnostic.

### 2. Audit the governed baseline

Run `python capstone_precheck.py`. Explain what the perfect reference-fixture result proves and what it does not prove. Then run the live RAG against the ten governed cases. Preserve per-case evidence; do not report only averages.

### 3. Curate additional dataset coverage

Review at least six of the twelve candidates. For each, choose `approve`, `reject`, `duplicate`, `needs_domain_review`, or `needs_source_evidence`. Propose at most three additions. Approval requires source chunk IDs, a reference behavior, required concepts, forbidden claims, reviewer identity, and a reason. A model output cannot approve itself.

### 4. Evaluate retrieval and generation separately

Use exact retrieval measures such as Precision@k, Recall@k, required-context recall, MRR, or nDCG where the labels support them. Use deterministic citation and forbidden-claim checks. Use Ragas for selected RAG component metrics and explain the evidence each metric requires.

### 5. Apply DeepEval

Run answer relevancy, faithfulness, contextual precision/recall/relevancy as appropriate. Use the full profile's `Medical Safety and Scope` G-Eval rubric on a reviewed slice. Calibrate judge outputs against human labels; do not treat default thresholds as release policy.

### 6. Use LangSmith as the experiment and trace layer

Run a local experiment first. If hosted access is approved, synchronize the ten governed examples to the separate `medical-education-rag-golden-v1` dataset, run a named baseline and candidate experiment, inspect retrieval and generation spans, add human feedback, and compare the two experiments. Do not upload real patient content.

### 7. Test risk and prompt injection

Run all ten risk cases. Distinguish an attack attempt from an observed unsafe effect. Include one direct injection and one controlled indirect-injection fixture. A confirmed emergency under-escalation, diagnosis, dose change, or unsafe medicine-sharing response is blocking regardless of the average score.

### 8. Make one controlled improvement

Choose one diagnosed component: corpus/data, retrieval, generation prompt, application guard, or evaluator rubric. Make one bounded change. Rerun the new failing slice, all ten governed cases, and all blocking risk cases. Do not change multiple variables together.

### 9. Close the offline-online loop

Use a synthetic canary or production-like synthetic trace. Ordinary traces without references may receive reference-free groundedness, relevancy, citation, safety, latency, and human feedback; do not claim reference correctness. Sanitize any useful observed trace and propose it as a candidate, not an automatically approved golden case.

### 10. Defend the release decision

Submit the completed templates plus case-level reports. Cite the exact cases, traces, evaluator evidence, human dispositions, remaining uncertainty, and next online measurement supporting the decision.

## Minimum commands

```bash
python capstone_precheck.py --output output/precheck.json
python app.py inspect
python eval_app.py run --rag-provider ollama --judge-provider ollama --top-k 3 --metric-profile full
python deepeval_app.py run --rag-provider ollama --judge-provider ollama --top-k 3 --metric-profile full
python langsmith_app.py run --rag-provider ollama --top-k 3 --metric-profile full
python assignment_check.py learner_work
pytest -q
```

Hosted LangSmith writes require explicit confirmation and a separate dataset:

```bash
python langsmith_app.py run --rag-provider ollama --top-k 3 --metric-profile full --hosted --sync-dataset --confirm-hosted --experiment-prefix mediguide-baseline-top3
```

## Evidence pack

Submit:

1. Risk-to-evaluator map
2. Baseline and candidate experiment plan
3. Governed-dataset audit and six candidate decisions
4. Per-case retrieval, deterministic, Ragas, and DeepEval results
5. Human-versus-judge calibration table
6. Direct and indirect injection analysis
7. Three trace diagnoses across data/retrieval, model/evaluator, and application/development
8. One controlled change and rerun comparison
9. Completed human-review record
10. Release decision with blocking evidence, residual risk, and next online measurement

## Scoring

| Area | Points |
|---|---:|
| Risk definition and evaluator selection | 15 |
| Dataset authority, provenance, and curation | 15 |
| Retrieval and generation evaluation | 20 |
| DeepEval/Ragas implementation and interpretation | 15 |
| LangSmith experiments, traces, and human feedback | 10 |
| Security, prompt injection, and medical-safety reasoning | 15 |
| Controlled improvement and regression evidence | 5 |
| Release decision and limitations | 5 |
| **Total** | **100** |

Completion requires 70/100 and no critical reasoning failure. Critical failures include treating candidates as gold, using real patient data, ignoring a confirmed unsafe medical effect because the mean is high, claiming reference correctness on an ordinary online trace, or releasing without recorded human accountability.
