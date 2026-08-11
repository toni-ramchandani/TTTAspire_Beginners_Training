# LangSmith online-evaluation setup

The code package records real nested RAG traces when hosted tracing is enabled. Configure the actual LangSmith online evaluator in the tracing project UI because the evaluator is a hosted project rule with filters, sampling, retention, and spend consequences.

1. Open the `payroll-mfa-rag-observability` tracing project.
2. Open **Evaluators**, then create a **Code Evaluator**.
3. Name it `payroll-mfa-online-deterministic-v1`.
4. Paste `langsmith_online_code_evaluator.py` into the inline editor.
5. Filter to root runs named `payroll_mfa_rag`.
6. Run it on 100% of `synthetic_canary`, `synthetic_security_canary`, and `synthetic_failure_fixture` traffic.
7. Use a risk-adjusted sample for other eligible traffic, plus a small control sample of apparent passes.
8. Test the code against a recent synthetic run before saving it.

For an LLM-as-a-judge evaluator, map question, answer, and retrieved contexts from the root output. Do not map a reference field for ordinary operational traffic. Keep its feedback keys distinct from Ragas and DeepEval results.

Online evaluator execution can extend trace retention and affect cost. Review content capture, redaction, filters, sampling, retention, and spend limits before enabling it on non-synthetic traffic.

Human review can be created with:

```powershell
python continuous_eval_app.py setup-review-queue --confirm-hosted
```

The command creates feedback schemas and a single-run annotation queue. It does not populate the queue or promote traces automatically.

