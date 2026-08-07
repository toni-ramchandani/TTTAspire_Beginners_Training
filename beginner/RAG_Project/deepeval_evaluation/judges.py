"""DeepEval judge construction for OpenAI and local Ollama."""

from __future__ import annotations

import os
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


class DeepEvalConfigurationError(ValueError):
    """Raised when DeepEval settings are missing or invalid."""


@dataclass(frozen=True)
class DeepEvalJudgeSettings:
    provider: str
    model_name: str
    api_key: str | None
    base_url: str | None
    timeout_seconds: float
    max_concurrent: int

    @classmethod
    def from_env(
        cls, project_root: Path, provider_override: str | None = None
    ) -> "DeepEvalJudgeSettings":
        # DeepEval dotenv autoload is disabled. The application deliberately loads
        # one known file and never prints its values.
        load_dotenv(project_root / ".env", override=False)
        provider = (
            provider_override or os.getenv("DEEPEVAL_JUDGE_PROVIDER", "ollama")
        ).strip().lower()
        if provider not in {"ollama", "openai"}:
            raise DeepEvalConfigurationError(
                "DEEPEVAL_JUDGE_PROVIDER must be 'ollama' or 'openai'."
            )

        try:
            timeout_seconds = float(
                os.getenv(
                    "DEEPEVAL_REQUEST_TIMEOUT_SECONDS",
                    os.getenv("RAG_REQUEST_TIMEOUT_SECONDS", "180"),
                )
            )
            max_concurrent = int(os.getenv("DEEPEVAL_MAX_CONCURRENT", "4"))
        except ValueError as exc:
            raise DeepEvalConfigurationError(
                "DeepEval timeout and concurrency settings must be numeric."
            ) from exc
        if timeout_seconds <= 0 or max_concurrent < 1:
            raise DeepEvalConfigurationError(
                "DeepEval timeout must be positive and max concurrency at least 1."
            )

        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise DeepEvalConfigurationError(
                    "OPENAI_API_KEY is required for the OpenAI DeepEval judge."
                )
            return cls(
                provider=provider,
                model_name=os.getenv("DEEPEVAL_OPENAI_MODEL", "gpt-4o-mini").strip(),
                api_key=api_key,
                base_url=None,
                timeout_seconds=timeout_seconds,
                max_concurrent=max_concurrent,
            )

        return cls(
            provider=provider,
            model_name=os.getenv(
                "DEEPEVAL_OLLAMA_MODEL",
                os.getenv("OLLAMA_CHAT_MODEL", "gemma3:4b"),
            ).strip(),
            api_key=None,
            base_url=os.getenv(
                "DEEPEVAL_OLLAMA_BASE_URL",
                os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            ).rstrip("/"),
            timeout_seconds=timeout_seconds,
            max_concurrent=max_concurrent,
        )


@dataclass(frozen=True)
class DeepEvalJudgeBundle:
    settings: DeepEvalJudgeSettings
    model: Any


def dependency_versions() -> dict[str, str]:
    packages = (
        "deepeval",
        "ollama",
        "openai",
        "pydantic",
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


def build_judge_bundle(settings: DeepEvalJudgeSettings) -> DeepEvalJudgeBundle:
    try:
        from deepeval.models import GPTModel, OllamaModel
    except (ImportError, ModuleNotFoundError) as exc:
        raise DeepEvalConfigurationError(
            "DeepEval dependencies are unavailable. Install the tested set with: "
            "pip install -r requirements-deepeval.txt"
        ) from exc

    # These documented environment overrides apply to DeepEval's retry/timeout
    # layer. Constructor arguments still identify the provider and model explicitly.
    os.environ.setdefault(
        "DEEPEVAL_PER_ATTEMPT_TIMEOUT_SECONDS_OVERRIDE",
        str(settings.timeout_seconds),
    )
    os.environ.setdefault(
        "DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE",
        str(settings.timeout_seconds * 3),
    )

    try:
        if settings.provider == "openai":
            model = GPTModel(
                model=settings.model_name,
                api_key=settings.api_key,
                temperature=0,
            )
        else:
            model = OllamaModel(
                model=settings.model_name,
                base_url=settings.base_url,
                temperature=0,
            )
    except Exception as exc:
        raise DeepEvalConfigurationError(
            f"Could not initialize the {settings.provider} DeepEval judge: {exc}"
        ) from exc
    return DeepEvalJudgeBundle(settings=settings, model=model)


def run_preflight(bundle: DeepEvalJudgeBundle, live: bool = False) -> dict[str, Any]:
    """Verify imports/model construction and optionally one structured model call."""

    result: dict[str, Any] = {
        "framework": "deepeval",
        "provider": bundle.settings.provider,
        "model": bundle.settings.model_name,
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
        generated, _cost = bundle.model.generate(
            "Return a JSON object whose status field is exactly 'ok'.",
            schema=PreflightOutput,
        )
    except Exception as exc:
        raise DeepEvalConfigurationError(
            f"Live DeepEval judge preflight failed for {bundle.settings.provider}: {exc}"
        ) from exc
    if not isinstance(generated, PreflightOutput) or generated.status.lower() != "ok":
        raise DeepEvalConfigurationError(
            "The DeepEval judge did not return the required structured output."
        )
    result["structured_output"] = generated.status
    return result

