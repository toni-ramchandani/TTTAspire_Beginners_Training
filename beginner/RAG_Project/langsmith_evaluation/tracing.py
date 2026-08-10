"""Real nested tracing for the existing non-LangChain RAG application."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

from langsmith import traceable

from rag.models import RAGTrace, RetrievedChunk
from rag.pipeline import RAGApplication, SYSTEM_INSTRUCTIONS, build_generation_prompt

from .settings import LangSmithSettings


def _document_view(
    retrieved: list[RetrievedChunk], capture_content: bool
) -> list[dict[str, Any]]:
    """Use the LangSmith retriever document shape without changing RAG objects."""

    return [
        {
            "page_content": (
                item.chunk.text if capture_content else "[content redacted]"
            ),
            "type": "Document",
            "metadata": {
                "chunk_id": item.chunk.chunk_id,
                "document_id": item.chunk.document_id,
                "document_version": item.chunk.document_version,
                "section_title": item.chunk.section_title,
                "score": round(item.score, 6),
            },
        }
        for item in retrieved
    ]


def _trace_result(value: tuple[RAGTrace, Path]) -> dict[str, Any]:
    trace, trace_path = value
    return {
        "answer": trace.answer,
        "run_id": trace.run_id,
        "retrieved_chunk_ids": [item.chunk.chunk_id for item in trace.retrieved],
        "retrieval_latency_ms": trace.retrieval_latency_ms,
        "generation_latency_ms": trace.generation_latency_ms,
        "total_latency_ms": trace.total_latency_ms,
        "canonical_trace_path": str(trace_path),
    }


class LangSmithRAGApplication(RAGApplication):
    """Instrument the real RAG steps while retaining the canonical local trace.

    The base class still owns retrieval, generation, timings, and JSON trace
    persistence. This subclass only wraps those actual boundaries with LangSmith
    spans. It neither rebuilds the RAG nor depends on LangChain.
    """

    def __init__(
        self,
        *args: Any,
        langsmith_settings: LangSmithSettings,
        langsmith_client: Any | None = None,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.langsmith_settings = langsmith_settings
        self._langsmith_run_ids: dict[str, str] = {}
        self._langsmith_run_ids_lock = Lock()
        common = {
            "project_name": langsmith_settings.project_name,
            "tags": ["payroll-mfa", "rag", self.provider.provider_name],
        }
        if langsmith_client is not None:
            common["client"] = langsmith_client

        def retrieve_step(question: str, top_k: int) -> list[RetrievedChunk]:
            return super(LangSmithRAGApplication, self)._retrieve(question, top_k)

        self._retrieve_step = traceable(
            name="payroll_mfa_retrieve",
            run_type="retriever",
            metadata={
                "provider": self.provider.provider_name,
                "embedding_model": self.provider.embedding_model,
            },
            process_inputs=lambda values: {
                "query": (
                    values.get("question")
                    if langsmith_settings.capture_content
                    else "[question redacted]"
                ),
                "top_k": values.get("top_k"),
            },
            process_outputs=lambda items: _document_view(
                items, langsmith_settings.capture_content
            ),
            **common,
        )(retrieve_step)

        def generate_step(
            question: str, retrieved: list[RetrievedChunk]
        ) -> str:
            return super(LangSmithRAGApplication, self)._generate(
                question, retrieved
            )

        def generation_inputs(values: dict[str, Any]) -> dict[str, Any]:
            question = str(values.get("question", ""))
            retrieved = values.get("retrieved") or []
            if not langsmith_settings.capture_content:
                return {
                    "messages": [
                        {"role": "system", "content": "[instructions redacted]"},
                        {"role": "user", "content": "[question and context redacted]"},
                    ],
                    "retrieved_chunk_ids": [
                        item.chunk.chunk_id for item in retrieved
                    ],
                }
            return {
                "messages": [
                    {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                    {
                        "role": "user",
                        "content": build_generation_prompt(question, retrieved),
                    },
                ]
            }

        self._generate_step = traceable(
            name="payroll_mfa_generate",
            run_type="llm",
            metadata={
                "ls_provider": self.provider.provider_name,
                "ls_model_name": self.provider.generation_model,
            },
            process_inputs=generation_inputs,
            process_outputs=lambda answer: {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": (
                                answer
                                if langsmith_settings.capture_content
                                else "[answer redacted]"
                            ),
                        }
                    }
                ]
            },
            **common,
        )(generate_step)

        def ask_step(
            question: str, top_k: int | None = None, run_tree: Any | None = None
        ) -> tuple[RAGTrace, Path]:
            trace, trace_path = super(LangSmithRAGApplication, self).ask(
                question, top_k
            )
            if run_tree is not None:
                with self._langsmith_run_ids_lock:
                    self._langsmith_run_ids[trace.run_id] = str(run_tree.id)
            return trace, trace_path

        self._ask_step = traceable(
            name="payroll_mfa_rag",
            run_type="chain",
            metadata={
                "rag_provider": self.provider.provider_name,
                "generation_model": self.provider.generation_model,
                "embedding_model": self.provider.embedding_model,
                "chunker_version": "heading-v1",
            },
            process_inputs=lambda values: {
                "question": (
                    values.get("question")
                    if langsmith_settings.capture_content
                    else "[question redacted]"
                ),
                "top_k": values.get("top_k"),
            },
            process_outputs=_trace_result,
            **common,
        )(ask_step)

    def _retrieve(self, question: str, top_k: int) -> list[RetrievedChunk]:
        return self._retrieve_step(question, top_k)

    def _generate(self, question: str, retrieved: list[RetrievedChunk]) -> str:
        return self._generate_step(question, retrieved)

    def ask(self, question: str, top_k: int | None = None) -> tuple[RAGTrace, Path]:
        return self._ask_step(question, top_k)

    def langsmith_run_id(self, canonical_run_id: str) -> str | None:
        """Return the LangSmith root span ID associated with one local trace."""

        with self._langsmith_run_ids_lock:
            return self._langsmith_run_ids.get(canonical_run_id)
