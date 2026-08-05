"""Ragas judge construction for OpenAI and local Ollama."""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .models import EvaluationDataError

# Disable Ragas' anonymous usage events by default for this evaluation project.
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")


class JudgeConfigurationError(ValueError):
    """Raised when evaluator-provider settings are incomplete or invalid."""


@dataclass(frozen=True)
class JudgeSettings:
    provider: str
    chat_model: str
    embedding_model: str
    api_key: str
    base_url: str | None
    timeout_seconds: float
    max_retries: int
    max_tokens: int

    @classmethod
    def from_env(
        cls, project_root: Path, provider_override: str | None = None
    ) -> "JudgeSettings":
        load_dotenv(project_root / ".env")
        provider = (
            provider_override or os.getenv("RAGAS_JUDGE_PROVIDER", "ollama")
        ).strip().lower()
        if provider not in {"ollama", "openai"}:
            raise JudgeConfigurationError(
                "RAGAS_JUDGE_PROVIDER must be 'ollama' or 'openai'."
            )

        try:
            timeout_seconds = float(
                os.getenv(
                    "RAGAS_REQUEST_TIMEOUT_SECONDS",
                    os.getenv("RAG_REQUEST_TIMEOUT_SECONDS", "180"),
                )
            )
            max_retries = int(os.getenv("RAGAS_MAX_RETRIES", "2"))
            max_tokens = int(os.getenv("RAGAS_MAX_TOKENS", "4096"))
        except ValueError as exc:
            raise JudgeConfigurationError(
                "RAGAS timeout, retry, and token settings must be numeric."
            ) from exc
        if timeout_seconds <= 0 or max_retries < 0 or max_tokens < 256:
            raise JudgeConfigurationError(
                "RAGAS timeout must be positive, retries non-negative, and max tokens >= 256."
            )

        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise JudgeConfigurationError(
                    "OPENAI_API_KEY is required for the OpenAI Ragas judge."
                )
            return cls(
                provider=provider,
                chat_model=os.getenv(
                    "RAGAS_OPENAI_CHAT_MODEL",
                    os.getenv("OPENAI_CHAT_MODEL", "gpt-5.6-luna"),
                ).strip(),
                embedding_model=os.getenv(
                    "RAGAS_OPENAI_EMBEDDING_MODEL",
                    os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
                ).strip(),
                api_key=api_key,
                base_url=None,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                max_tokens=max_tokens,
            )

        native_base_url = os.getenv(
            "RAGAS_OLLAMA_BASE_URL",
            os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        ).rstrip("/")
        compatible_base_url = (
            native_base_url if native_base_url.endswith("/v1") else f"{native_base_url}/v1"
        )
        return cls(
            provider=provider,
            chat_model=os.getenv(
                "RAGAS_OLLAMA_CHAT_MODEL",
                os.getenv("OLLAMA_CHAT_MODEL", "gemma4:latest"),  #dolphin3:latest 
            ).strip(),
            embedding_model=os.getenv(
                "RAGAS_OLLAMA_EMBEDDING_MODEL",
                os.getenv("OLLAMA_EMBEDDING_MODEL", "embeddinggemma"),
            ).strip(),
            api_key="ollama",
            base_url=compatible_base_url,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            max_tokens=max_tokens,
        )


@dataclass(frozen=True)
class JudgeBundle:
    settings: JudgeSettings
    client: Any
    llm: Any
    embeddings: Any


def dependency_versions() -> dict[str, str]:
    packages = (
        "ragas",
        "openai",
        "instructor",
        "langchain",
        "langchain-core",
        "langchain-community",
        "python-dotenv",
        "numpy",
    )
    versions: dict[str, str] = {}
    for package in packages:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "NOT INSTALLED"
    return versions


def build_judge_bundle(settings: JudgeSettings) -> JudgeBundle:
    try:
        from openai import AsyncOpenAI
        from ragas.embeddings.base import embedding_factory
        from ragas.llms import llm_factory
    except (ImportError, ModuleNotFoundError) as exc:
        raise JudgeConfigurationError(
            "Ragas evaluation dependencies are unavailable or incompatible. "
            "Install the tested set with: pip install -r requirements-eval.txt. "
            f"Original error: {exc}"
        ) from exc

    client_kwargs: dict[str, Any] = {
        "api_key": settings.api_key,
        "timeout": settings.timeout_seconds,
        "max_retries": settings.max_retries,
    }
    if settings.base_url:
        client_kwargs["base_url"] = settings.base_url
    # Ragas 0.4 collections metrics expose a synchronous ``score()`` method,
    # but that method executes the metric's async ``ascore()`` pipeline.  The
    # evaluator LLM is therefore called through ``agenerate()`` internally and
    # must be backed by an async provider client.  Ragas' modern embeddings
    # adapter supports the same AsyncOpenAI client and bridges synchronous
    # ``embed_text()`` calls when required by AnswerRelevancy.
    client = AsyncOpenAI(**client_kwargs)

    try:
        llm = llm_factory(
            settings.chat_model,
            provider="openai",
            client=client,
            adapter="instructor",
            max_tokens=settings.max_tokens,
        )
        embeddings = embedding_factory(
            "openai",
            model=settings.embedding_model,
            client=client,
            interface="modern",
        )
    except Exception as exc:
        raise JudgeConfigurationError(
            f"Could not initialize the {settings.provider} Ragas judge: {exc}"
        ) from exc
    return JudgeBundle(settings=settings, client=client, llm=llm, embeddings=embeddings)


def run_preflight(bundle: JudgeBundle, live: bool = False) -> dict[str, Any]:
    """Verify imports and adapter construction; optionally make two small live calls."""

    result: dict[str, Any] = {
        "provider": bundle.settings.provider,
        "chat_model": bundle.settings.chat_model,
        "embedding_model": bundle.settings.embedding_model,
        "base_url": bundle.settings.base_url or "OpenAI default endpoint",
        "dependencies": dependency_versions(),
        "adapter_initialized": True,
        "live_checked": live,
    }
    if not live:
        return result

    from pydantic import BaseModel

    class PreflightOutput(BaseModel):
        status: str

    try:
        vector = bundle.embeddings.embed_text("Ragas evaluator preflight")
        structured = bundle.llm.generate(
            "Return a JSON object whose status field is exactly 'ok'.", PreflightOutput
        )
    except Exception as exc:
        raise EvaluationDataError(
            f"Live judge preflight failed for {bundle.settings.provider}: {exc}"
        ) from exc
    if not isinstance(vector, list) or not vector:
        raise EvaluationDataError("Judge embedding preflight returned no vector.")
    if structured.status.lower() != "ok":
        raise EvaluationDataError(
            "Judge structured-output preflight returned an unexpected status."
        )
    result["embedding_dimensions"] = len(vector)
    result["structured_output"] = structured.status
    return result
