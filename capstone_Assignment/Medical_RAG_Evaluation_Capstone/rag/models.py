"""Framework-neutral data contracts for chunks, retrieval, and RAG traces."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    document_title: str
    document_version: str
    section_title: str
    source_file: str
    text: str

    def embedding_text(self) -> str:
        """Text sent to the embedding model."""
        return (
            f"Document: {self.document_title}\n"
            f"Section: {self.section_title}\n"
            f"{self.text}"
        )

    def context_text(self) -> str:
        """Evidence block sent to the generation model and later evaluators."""
        return (
            f"[{self.chunk_id}]\n"
            f"Document: {self.document_title} (version {self.document_version})\n"
            f"Section: {self.section_title}\n"
            f"{self.text}"
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DocumentChunk":
        return cls(**value)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: DocumentChunk
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk.chunk_id,
            "document_id": self.chunk.document_id,
            "document_title": self.chunk.document_title,
            "document_version": self.chunk.document_version,
            "section_title": self.chunk.section_title,
            "source_file": self.chunk.source_file,
            "score": round(self.score, 6),
            "text": self.chunk.text,
        }


@dataclass(frozen=True)
class RAGTrace:
    schema_version: str
    run_id: str
    created_at_utc: str
    question: str
    answer: str
    provider: str
    embedding_model: str
    generation_model: str
    top_k: int
    chunker_version: str
    retrieval_latency_ms: int
    generation_latency_ms: int
    total_latency_ms: int
    retrieved: tuple[RetrievedChunk, ...]

    def to_dict(self) -> dict[str, Any]:
        """Emit canonical fields that both Ragas and DeepEval can later consume."""
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "created_at_utc": self.created_at_utc,
            "question": self.question,
            "answer": self.answer,
            "provider": self.provider,
            "embedding_model": self.embedding_model,
            "generation_model": self.generation_model,
            "top_k": self.top_k,
            "chunker_version": self.chunker_version,
            "retrieval_latency_ms": self.retrieval_latency_ms,
            "generation_latency_ms": self.generation_latency_ms,
            "total_latency_ms": self.total_latency_ms,
            "retrieved_chunk_ids": [item.chunk.chunk_id for item in self.retrieved],
            "retrieved_contexts": [
                item.chunk.context_text() for item in self.retrieved
            ],
            "retrieval_scores": [round(item.score, 6) for item in self.retrieved],
            "retrieved_chunks": [item.to_dict() for item in self.retrieved],
        }
