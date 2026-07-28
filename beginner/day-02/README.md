# Beginner Day 2 - first executable DeepEval evaluation

Day 2 reuses the exact Day 1 files under `beginner/day-01/lab/data`.
It does not generate new model responses.

## Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r beginner/day-02/requirements.txt
python beginner/day-02/day2_eval.py
```

## macOS or Linux

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r beginner/day-02/requirements.txt
python beginner/day-02/day2_eval.py
```

Expected schema results:

```text
Run 1: PASS
Run 2: PASS
Run 3: FAIL
Run 4: PASS
Run 5: PASS
Schema pass rate: 4/5 = 80%
```

This result proves only schema compliance. It does not establish that the
response is safe, semantically correct, or releasable.
