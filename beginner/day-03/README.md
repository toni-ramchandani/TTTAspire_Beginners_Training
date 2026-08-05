# Day 3 - First Ragas retrieval experiment

This lab evaluates three stored retrieval traces. It makes no model or embedding
calls and requires no API key.

## Setup and run

```bash
python3.12 -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python day3_ragas_experiment.py
```

Expected metric pairs:

- `TRACE-1-clean`: precision `1.00`, recall `1.00`
- `TRACE-2-missed-policy`: precision `0.00`, recall `0.00`
- `TRACE-3-noisy`: precision `0.50`, recall `1.00`

Ragas writes the governed dataset and structured experiment result under
`results/datasets/` and `results/experiments/`.

The lab proves retrieval coverage and noise only. It does not score the generated
answer, faithfulness, business correctness, safety, or release readiness.

The LangChain pins are intentional. Ragas 0.4.3 imports an integration path that
is absent from newer LangChain Community releases, so pinning only `ragas` is not
a reproducible environment as of August 2026.
