"""DeepEval integration kept separate from the existing Ragas evaluator."""

from __future__ import annotations

import os

# DeepEval loads dotenv files and emits anonymous metric-name telemetry by default.
# This project owns configuration explicitly and keeps evaluation local unless a
# user deliberately configures a hosted provider.
os.environ.setdefault("DEEPEVAL_DISABLE_DOTENV", "1")
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "1")
os.environ.setdefault("DEEPEVAL_NO_INSPECT_PROMPT", "1")


DEEPEVAL_REPORT_SCHEMA_VERSION = "1.0"

