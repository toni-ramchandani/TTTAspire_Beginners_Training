"""A deliberately small in-memory cosine-similarity index."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .chunking import CHUNKER_VERSION
from .models import DocumentChunk, RetrievedChunk
from .providers import ModelProvider

INDEX_SCHEMA_VERSION = "1.0"


def _normalise_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("Embedding vectors must be non-zero.")
    return matrix / norms


@dataclass
class VectorIndex:
    provider: str
    embedding_model: str
    chunks: list[DocumentChunk]
    embeddings: np.ndarray
    created_at_utc: str

    @classmethod
    def build(
        cls,
        chunks: Sequence[DocumentChunk],
        provider: ModelProvider,
    ) -> "VectorIndex":
        if not chunks:
            raise ValueError("Cannot build an index without chunks.")
        vectors = provider.embed([chunk.embedding_text() for chunk in chunks])
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[0] != len(chunks):
            raise ValueError("Provider returned an invalid embedding matrix.")
        return cls(
            provider=provider.provider_name,
            embedding_model=provider.embedding_model,
            chunks=list(chunks),
            embeddings=_normalise_rows(matrix),
            created_at_utc=datetime.now(timezone.utc).isoformat(),
        )

    def search(self, query_embedding: Sequence[float], top_k: int) -> list[RetrievedChunk]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1.")
        query = np.asarray(query_embedding, dtype=np.float32)
        if query.ndim != 1 or query.shape[0] != self.embeddings.shape[1]:
            raise ValueError(
                "Query embedding dimension does not match the stored index. "
                "Rebuild the index with the active embedding model."
            )
        norm = np.linalg.norm(query)
        if norm == 0:
            raise ValueError("Query embedding must be non-zero.")

        scores = self.embeddings @ (query / norm)
        ranked = sorted(
            range(len(self.chunks)),
            key=lambda index: (-float(scores[index]), self.chunks[index].chunk_id),
        )
        return [
            RetrievedChunk(chunk=self.chunks[index], score=float(scores[index]))
            for index in ranked[: min(top_k, len(ranked))]
        ]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "created_at_utc": self.created_at_utc,
            "provider": self.provider,
            "embedding_model": self.embedding_model,
            "chunker_version": CHUNKER_VERSION,
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "embeddings": self.embeddings.tolist(),
        }
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary_path.replace(path)

    @classmethod
    def load(cls, path: Path) -> "VectorIndex":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != INDEX_SCHEMA_VERSION:
            raise ValueError("Unsupported index schema. Rebuild the index.")
        if payload.get("chunker_version") != CHUNKER_VERSION:
            raise ValueError("The chunker changed. Rebuild the index.")

        chunks = [DocumentChunk.from_dict(item) for item in payload["chunks"]]
        embeddings = np.asarray(payload["embeddings"], dtype=np.float32)
        if embeddings.ndim != 2 or embeddings.shape[0] != len(chunks):
            raise ValueError("Stored index is corrupt or incomplete.")

        return cls(
            provider=payload["provider"],
            embedding_model=payload["embedding_model"],
            chunks=chunks,
            embeddings=_normalise_rows(embeddings),
            created_at_utc=payload["created_at_utc"],
        )
