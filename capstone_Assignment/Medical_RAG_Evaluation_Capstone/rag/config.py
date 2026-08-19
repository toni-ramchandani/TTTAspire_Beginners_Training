"""Environment-backed application configuration."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when configuration is missing or inconsistent."""


@dataclass(frozen=True)
class Settings:
    """Configuration shared by the CLI, provider, index, and trace."""

    provider: str
    top_k: int
    request_timeout_seconds: float
    openai_api_key: str | None
    openai_chat_model: str
    openai_embedding_model: str
    ollama_base_url: str
    ollama_chat_model: str
    ollama_embedding_model: str

    @classmethod
    def from_env(
        cls,
        project_root: Path,
        provider_override: str | None = None,
    ) -> "Settings":
        load_dotenv(project_root / ".env")

        provider = (provider_override or os.getenv("RAG_PROVIDER", "ollama")).lower()
        if provider not in {"openai", "ollama"}:
            raise ConfigurationError("RAG_PROVIDER must be 'openai' or 'ollama'.")

        try:
            top_k = int(os.getenv("RAG_TOP_K", "3"))
            timeout = float(os.getenv("RAG_REQUEST_TIMEOUT_SECONDS", "120"))
        except ValueError as exc:
            raise ConfigurationError(
                "RAG_TOP_K must be an integer and RAG_REQUEST_TIMEOUT_SECONDS must be numeric."
            ) from exc

        if top_k < 1:
            raise ConfigurationError("RAG_TOP_K must be at least 1.")
        if timeout <= 0:
            raise ConfigurationError("RAG_REQUEST_TIMEOUT_SECONDS must be positive.")

        return cls(
            provider=provider,
            top_k=top_k,
            request_timeout_seconds=timeout,
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-5.6-luna"),
            openai_embedding_model=os.getenv(
                "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
            ),
            ollama_base_url=os.getenv(
                "OLLAMA_BASE_URL", "http://localhost:11434"
            ).rstrip("/"),
            ollama_chat_model=os.getenv("OLLAMA_CHAT_MODEL", "gemma3:4b"),
            ollama_embedding_model=os.getenv(
                "OLLAMA_EMBEDDING_MODEL", "embeddinggemma"
            ),
        )

    @property
    def chat_model(self) -> str:
        return (
            self.openai_chat_model
            if self.provider == "openai"
            else self.ollama_chat_model
        )

    @property
    def embedding_model(self) -> str:
        return (
            self.openai_embedding_model
            if self.provider == "openai"
            else self.ollama_embedding_model
        )

    @property
    def index_filename(self) -> str:
        model_slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", self.embedding_model)
        return f"index-{self.provider}-{model_slug}.json"
