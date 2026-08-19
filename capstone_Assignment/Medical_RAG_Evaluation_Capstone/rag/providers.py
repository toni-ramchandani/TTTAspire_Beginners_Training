"""OpenAI and Ollama implementations behind one small provider interface."""

from __future__ import annotations

import json
from typing import Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import ConfigurationError, Settings


class ProviderError(RuntimeError):
    """Raised when an embedding or generation provider call fails."""


class ModelProvider(Protocol):
    provider_name: str
    embedding_model: str
    generation_model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    def generate(self, instructions: str, prompt: str) -> str: ...


class OpenAIProvider:
    provider_name = "openai"

    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY is required when the provider is 'openai'. "
                "Copy .env.example to .env and add the key locally."
            )

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ConfigurationError(
                "The 'openai' package is missing. Run: pip install -r requirements.txt"
            ) from exc

        self.embedding_model = settings.openai_embedding_model
        self.generation_model = settings.openai_chat_model
        self._client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.request_timeout_seconds,
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.embeddings.create(
                model=self.embedding_model,
                input=list(texts),
            )
        except Exception as exc:  # SDK exposes several transport/API subclasses.
            raise ProviderError(f"OpenAI embedding request failed: {exc}") from exc

        ordered = sorted(response.data, key=lambda item: item.index)
        embeddings = [item.embedding for item in ordered]
        if len(embeddings) != len(texts):
            raise ProviderError("OpenAI returned a different number of embeddings than inputs.")
        return embeddings

    def generate(self, instructions: str, prompt: str) -> str:
        try:
            response = self._client.responses.create(
                model=self.generation_model,
                instructions=instructions,
                input=prompt,
            )
        except Exception as exc:
            raise ProviderError(f"OpenAI response request failed: {exc}") from exc

        answer = response.output_text.strip()
        if not answer:
            raise ProviderError("OpenAI returned an empty answer.")
        return answer


class OllamaProvider:
    provider_name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.embedding_model = settings.ollama_embedding_model
        self.generation_model = settings.ollama_chat_model
        self._base_url = settings.ollama_base_url
        self._timeout = settings.request_timeout_seconds

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        request = Request(
            f"{self._base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ProviderError(
                f"Ollama returned HTTP {exc.code} for {path}: {detail}"
            ) from exc
        except URLError as exc:
            raise ProviderError(
                "Cannot reach Ollama. Start it locally and confirm OLLAMA_BASE_URL "
                f"({self._base_url}). Original error: {exc.reason}"
            ) from exc
        except (json.JSONDecodeError, TimeoutError) as exc:
            raise ProviderError(f"Invalid or timed-out Ollama response for {path}: {exc}") from exc

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._post(
            "/api/embed",
            {"model": self.embedding_model, "input": list(texts)},
        )
        embeddings = response.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise ProviderError("Ollama returned an invalid embeddings payload.")
        return embeddings  # type: ignore[return-value]

    def generate(self, instructions: str, prompt: str) -> str:
        response = self._post(
            "/api/chat",
            {
                "model": self.generation_model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "options": {"temperature": 0},
            },
        )
        message = response.get("message")
        answer = message.get("content") if isinstance(message, dict) else None
        if not isinstance(answer, str) or not answer.strip():
            raise ProviderError("Ollama returned an empty or invalid chat message.")
        return answer.strip()


def create_provider(settings: Settings) -> ModelProvider:
    if settings.provider == "openai":
        return OpenAIProvider(settings)
    return OllamaProvider(settings)
