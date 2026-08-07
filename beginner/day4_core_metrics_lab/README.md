# Day 4 - Core Metrics Simple Lab

This lab scores 20 frozen synthetic payroll-MFA outputs. It does not regenerate the application answers and it does not require Excel.

## 1. Create an environment

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## 2. Select one judge provider

OpenAI is DeepEval's default provider when configured:

```bash
# Windows PowerShell
$env:OPENAI_API_KEY="..."
# macOS/Linux
export OPENAI_API_KEY="..."
deepeval set-openai --model=<model-approved-for-your-account>
deepeval diagnose
```

Gemini:

```bash
# Windows PowerShell
$env:GOOGLE_API_KEY="..."
# macOS/Linux
export GOOGLE_API_KEY="..."
deepeval set-gemini --model=<model-approved-for-your-account>
deepeval diagnose
```

The Python code deliberately does not hard-code a model. This keeps the same test cases and metric configuration while the CLI selects GPT or Gemini. Record the exact provider and model with every result; do not treat scores from different judges as directly interchangeable.

## 3. Start with three cases

```bash
python day4_lab.py --limit 3
```

Run one named case and retain intermediate evidence:

```bash
python day4_lab.py --case D4-004 --verbose
```

## 4. Run the 20-output lab

Answer relevancy and faithfulness only:

```bash
python day4_lab.py
```

Add optional reference-correctness G-Eval:

```bash
python day4_lab.py --with-correctness
```

Compare Faithfulness's default handling of ambiguous/`idk` claims with explicit penalization:

```bash
python day4_lab.py --case D4-011 --case D4-014
python day4_lab.py --case D4-011 --case D4-014 --penalize-ambiguous
```

Outputs are written to `results/day4_results.json` and `results/day4_results.csv`.

## Review rule

A score is the start of investigation, not the end. For each disagreement, inspect the frozen question, output, retrieval context, expected output, extracted statements or claims, judge verdicts, model/version, threshold, and error state. Never turn an evaluator error or a zero-denominator edge into an assumed quality score.
