"""Map the framework-neutral RAG trace into DeepEval's test-case contract."""

from __future__ import annotations

from deepeval.test_case import LLMTestCase

from evaluation.models import GoldenCase, TraceRecord


def to_llm_test_case(case: GoldenCase, trace: TraceRecord) -> LLMTestCase:
    """Create one DeepEval case without changing or regenerating application output."""

    return LLMTestCase(
        name=case.case_id,
        input=trace.question,
        actual_output=trace.answer,
        expected_output=case.reference,
        retrieval_context=list(trace.retrieved_contexts),
        tags=list(case.tags),
        metadata={
            "case_id": case.case_id,
            "rag_run_id": trace.run_id,
            "rag_provider": trace.provider,
            "top_k": trace.top_k,
            "retrieved_chunk_ids": list(trace.retrieved_chunk_ids),
            "required_context_ids": list(case.required_context_ids),
        },
    )

