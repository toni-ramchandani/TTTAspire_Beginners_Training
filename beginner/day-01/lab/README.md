# Day 1 five-run variance lab

This lab compares five outputs across four separate dimensions:

1. surface-text variance;
2. human semantic labels;
3. hard instruction compliance;
4. raw JSON validity.

Five runs are a teaching demonstration, not a production reliability estimate.

## Offline trainer-safe run

```bash
python lab_day1.py
```

This uses the prepared fixture and writes `outputs/outputs.jsonl` plus
`outputs/summary.json`.

## Tests

```bash
python -m unittest discover -s tests -v
```

The offline lab and tests use only Python's standard library.

## Live run

```bash
python -m pip install -r requirements.txt
export OPENAI_API_KEY="..."
python lab_day1.py --live --temperature 1.0
```

The default model is the pinned snapshot `gpt-4.1-mini-2025-04-14` because it
supports the sampling control demonstrated here. Confirm availability and
pricing on delivery day.

To test top-p, omit temperature:

```bash
python lab_day1.py --live --top-p 0.8
```

Never set both controls in this exercise. If live outputs are manually reviewed,
pass the labels explicitly:

```bash
python lab_day1.py --live --temperature 1.0 \
  --labels correct,correct,partial,unsafe,correct
```

## Token demonstration

```bash
python token_demo.py
```

The displayed local count is a tokenizer demonstration. Provider-reported usage
remains the authoritative count for a completed API request.

