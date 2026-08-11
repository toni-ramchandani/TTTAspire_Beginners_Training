from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Sequence

import numpy as np

from rag.chunking import load_document_chunks, split_markdown_document
from rag.config import Settings
from rag.index import VectorIndex
from rag.models import DocumentChunk
from rag.pipeline import RAGApplication
from rag.providers import OllamaProvider, OpenAIProvider


class FakeProvider:
    provider_name = "ollama"
    embedding_model = "fake-embedding"
    generation_model = "fake-generation"
    vocabulary = ("mfa", "phone", "manager", "ticket", "payroll", "verification")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            vector = [float(lowered.count(term)) for term in self.vocabulary]
            vector.append(1.0)
            vectors.append(vector)
        return vectors

    def generate(self, instructions: str, prompt: str) -> str:
        assert "Answer only from" in instructions
        assert "Evidence blocks:" in prompt
        return "Complete identity verification and re-enrol the device [SEC-17::standard-recovery-workflow]."


def test_supplied_documents_create_unique_section_chunks() -> None:
    project_root = Path(__file__).resolve().parents[1]
    chunks = load_document_chunks(project_root / "documents")

    assert len(chunks) == 15
    assert len({chunk.chunk_id for chunk in chunks}) == len(chunks)
    assert "SEC-17::prohibited-shortcuts" in {chunk.chunk_id for chunk in chunks}
    assert "OPS-09::required-ticket-fields" in {chunk.chunk_id for chunk in chunks}


def test_front_matter_and_heading_become_stable_metadata(tmp_path: Path) -> None:
    document = tmp_path / "policy.md"
    document.write_text(
        "---\ndocument_id: TEST-1\ntitle: Test Policy\nversion: 1.0\n---\n"
        "# Ignored fallback title\n\n## Recovery Path\n\nUse the approved path.\n",
        encoding="utf-8",
    )

    chunks = split_markdown_document(document)

    assert chunks == [
        DocumentChunk(
            chunk_id="TEST-1::recovery-path",
            document_id="TEST-1",
            document_title="Test Policy",
            document_version="1.0",
            section_title="Recovery Path",
            source_file="policy.md",
            text="Use the approved path.",
        )
    ]


def test_cosine_index_returns_the_most_related_chunk() -> None:
    provider = FakeProvider()
    chunks = [
        DocumentChunk("A::mfa", "A", "A", "1", "MFA", "a.md", "phone MFA verification"),
        DocumentChunk("B::ticket", "B", "B", "1", "Ticket", "b.md", "payroll ticket fields"),
    ]
    index = VectorIndex.build(chunks, provider)
    query = provider.embed(["my phone cannot complete MFA verification"])[0]

    result = index.search(query, top_k=1)

    assert result[0].chunk.chunk_id == "A::mfa"
    assert result[0].score > 0.5


def test_end_to_end_pipeline_writes_evaluation_ready_trace(tmp_path: Path) -> None:
    project_root = tmp_path
    (project_root / "documents").mkdir()
    (project_root / "documents" / "policy.md").write_text(
        "---\ndocument_id: SEC-17\ntitle: Test\nversion: 1\n---\n"
        "# Test\n\n## Standard recovery workflow\n\n"
        "Verify identity and re-enrol the employee's phone for MFA.\n",
        encoding="utf-8",
    )
    settings = Settings(
        provider="ollama",
        top_k=1,
        request_timeout_seconds=10,
        openai_api_key=None,
        openai_chat_model="unused",
        openai_embedding_model="unused",
        ollama_base_url="http://localhost:11434",
        ollama_chat_model="fake-generation",
        ollama_embedding_model="fake-embedding",
    )
    application = RAGApplication(project_root, settings, provider=FakeProvider())

    trace, trace_path = application.ask("How do I recover MFA on my phone?")
    persisted = json.loads(trace_path.read_text(encoding="utf-8"))

    assert trace.answer.startswith("Complete identity verification")
    assert persisted["question"] == "How do I recover MFA on my phone?"
    assert persisted["retrieved_chunk_ids"] == ["SEC-17::standard-recovery-workflow"]
    assert persisted["retrieved_contexts"][0].startswith("[SEC-17::")
    assert persisted["provider"] == "ollama"
    assert (project_root / "results" / "latest.json").exists()


def test_application_exposes_internal_retrieve_and_generate_hooks(tmp_path: Path) -> None:
    project_root = tmp_path
    (project_root / "documents").mkdir()
    (project_root / "documents" / "policy.md").write_text(
        "---\ndocument_id: SEC-17\ntitle: Test\nversion: 1\n---\n"
        "# Test\n\n## Standard recovery workflow\n\n"
        "Verify identity and re-enrol the phone for MFA.\n",
        encoding="utf-8",
    )
    settings = Settings(
        provider="ollama",
        top_k=1,
        request_timeout_seconds=10,
        openai_api_key=None,
        openai_chat_model="unused",
        openai_embedding_model="unused",
        ollama_base_url="http://localhost:11434",
        ollama_chat_model="fake-generation",
        ollama_embedding_model="fake-embedding",
    )
    application = RAGApplication(project_root, settings, provider=FakeProvider())

    retrieved = application._retrieve("How do I recover MFA on my phone?", 1)
    answer = application._generate("How do I recover MFA on my phone?", retrieved)

    assert retrieved[0].chunk.chunk_id == "SEC-17::standard-recovery-workflow"
    assert answer.startswith("Complete identity verification")


def test_index_round_trip_preserves_rankings(tmp_path: Path) -> None:
    provider = FakeProvider()
    chunks = [
        DocumentChunk("A::one", "A", "A", "1", "One", "a.md", "manager payroll"),
        DocumentChunk("B::two", "B", "B", "1", "Two", "b.md", "phone MFA"),
    ]
    original = VectorIndex.build(chunks, provider)
    index_path = tmp_path / "index.json"
    original.save(index_path)

    loaded = VectorIndex.load(index_path)
    query = provider.embed(["phone MFA"])[0]

    assert loaded.search(query, 2)[0].chunk.chunk_id == "B::two"
    np.testing.assert_allclose(original.embeddings, loaded.embeddings, atol=1e-6)


def test_openai_adapter_uses_embeddings_and_responses_apis(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeEmbeddingsAPI:
        def create(self, **kwargs):
            calls["embeddings"] = kwargs
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=1, embedding=[0.0, 1.0]),
                    SimpleNamespace(index=0, embedding=[1.0, 0.0]),
                ]
            )

    class FakeResponsesAPI:
        def create(self, **kwargs):
            calls["response"] = kwargs
            return SimpleNamespace(output_text="Grounded answer [SEC-17::test].")

    class FakeOpenAIClient:
        embeddings = FakeEmbeddingsAPI()
        responses = FakeResponsesAPI()

    import openai

    monkeypatch.setattr(
        openai,
        "OpenAI",
        lambda **kwargs: calls.setdefault("client", kwargs) and FakeOpenAIClient(),
    )
    settings = Settings(
        provider="openai",
        top_k=2,
        request_timeout_seconds=10,
        openai_api_key="test-key",
        openai_chat_model="test-chat",
        openai_embedding_model="test-embedding",
        ollama_base_url="http://localhost:11434",
        ollama_chat_model="unused",
        ollama_embedding_model="unused",
    )

    provider = OpenAIProvider(settings)
    vectors = provider.embed(["first", "second"])
    answer = provider.generate("system instruction", "user prompt")

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert answer == "Grounded answer [SEC-17::test]."
    assert calls["embeddings"] == {
        "model": "test-embedding",
        "input": ["first", "second"],
    }
    assert calls["response"] == {
        "model": "test-chat",
        "instructions": "system instruction",
        "input": "user prompt",
    }


def test_ollama_adapter_uses_embed_and_chat_endpoints(monkeypatch) -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    class FakeHTTPResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        requests.append((request.full_url, payload))
        if request.full_url.endswith("/api/embed"):
            return FakeHTTPResponse({"embeddings": [[1.0, 0.0], [0.0, 1.0]]})
        return FakeHTTPResponse({"message": {"content": "Local grounded answer."}})

    monkeypatch.setattr("rag.providers.urlopen", fake_urlopen)
    settings = Settings(
        provider="ollama",
        top_k=2,
        request_timeout_seconds=10,
        openai_api_key=None,
        openai_chat_model="unused",
        openai_embedding_model="unused",
        ollama_base_url="http://localhost:11434",
        ollama_chat_model="local-chat",
        ollama_embedding_model="local-embedding",
    )

    provider = OllamaProvider(settings)
    vectors = provider.embed(["first", "second"])
    answer = provider.generate("system instruction", "user prompt")

    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert answer == "Local grounded answer."
    assert requests[0] == (
        "http://localhost:11434/api/embed",
        {"model": "local-embedding", "input": ["first", "second"]},
    )
    assert requests[1][0] == "http://localhost:11434/api/chat"
    assert requests[1][1]["model"] == "local-chat"
    assert requests[1][1]["stream"] is False
