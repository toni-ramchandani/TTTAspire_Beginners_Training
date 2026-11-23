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
    azure_openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_chat_deployment: str = ""
    azure_openai_embedding_deployment: str = ""

    @classmethod
    def from_env(
        cls,
        project_root: Path,
        provider_override: str | None = None,
    ) -> "Settings":
        load_dotenv(project_root / ".env")

        provider = (provider_override or os.getenv("RAG_PROVIDER", "ollama")).lower()
        if provider not in {"openai", "ollama", "azure"}:
            raise ConfigurationError("RAG_PROVIDER must be 'openai', 'ollama', or 'azure'.")

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

        if provider == "azure":
            required = (
                "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT",
                "AZURE_OPENAI_CHAT_DEPLOYMENT", "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
            )
            missing = [key for key in required if not os.getenv(key, "").strip()]
            if missing:
                raise ConfigurationError("Azure RAG requires: " + ", ".join(missing))
            if not os.environ["AZURE_OPENAI_ENDPOINT"].startswith("https://"):
                raise ConfigurationError("AZURE_OPENAI_ENDPOINT must use HTTPS.")

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
            azure_openai_api_key=os.getenv("AZURE_OPENAI_API_KEY") or None,
            azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT") or None,
            azure_openai_chat_deployment=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", ""),
            azure_openai_embedding_deployment=os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", ""),
        )

    @property
    def chat_model(self) -> str:
        if self.provider == "azure":
            return self.azure_openai_chat_deployment
        return (
            self.openai_chat_model
            if self.provider == "openai"
            else self.ollama_chat_model
        )

    @property
    def embedding_model(self) -> str:
        if self.provider == "azure":
            return self.azure_openai_embedding_deployment
        return (
            self.openai_embedding_model
            if self.provider == "openai"
            else self.ollama_embedding_model
        )

    @property
    def index_filename(self) -> str:
        model_slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", self.embedding_model)
        if self.provider == "azure":
            import hashlib

            endpoint = (self.azure_openai_endpoint or "").rstrip("/")
            resource_id = hashlib.sha256(endpoint.encode()).hexdigest()[:10]
            return f"index-{self.provider}-{resource_id}-{model_slug}.json"
        return f"index-{self.provider}-{model_slug}.json"
