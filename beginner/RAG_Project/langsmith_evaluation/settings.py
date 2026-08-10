"""Environment-backed LangSmith configuration with explicit hosted boundaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from rag.config import ConfigurationError


LANGSMITH_SDK_VERSION = "0.10.17"


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(
        f"{name} must be one of true/false, 1/0, yes/no, or on/off."
    )


@dataclass(frozen=True)
class LangSmithSettings:
    """Settings for tracing and local or hosted LangSmith experiments."""

    api_key: str | None
    endpoint: str
    workspace_id: str | None
    project_name: str
    dataset_name: str
    tracing_enabled: bool
    capture_content: bool
    max_concurrency: int

    @classmethod
    def from_env(cls, project_root: Path) -> "LangSmithSettings":
        load_dotenv(project_root / ".env")
        try:
            max_concurrency = int(os.getenv("LANGSMITH_MAX_CONCURRENCY", "2"))
        except ValueError as exc:
            raise ConfigurationError(
                "LANGSMITH_MAX_CONCURRENCY must be an integer."
            ) from exc
        if max_concurrency < 0:
            raise ConfigurationError(
                "LANGSMITH_MAX_CONCURRENCY must be zero or greater."
            )

        endpoint = os.getenv(
            "LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"
        ).rstrip("/")
        if not endpoint.startswith(("https://", "http://")):
            raise ConfigurationError(
                "LANGSMITH_ENDPOINT must be an HTTP or HTTPS URL."
            )

        return cls(
            api_key=os.getenv("LANGSMITH_API_KEY") or None,
            endpoint=endpoint,
            workspace_id=os.getenv("LANGSMITH_WORKSPACE_ID") or None,
            project_name=os.getenv(
                "LANGSMITH_PROJECT", "payroll-mfa-rag-observability"
            ),
            dataset_name=os.getenv(
                "LANGSMITH_DATASET", "payroll-mfa-rag-golden-v1"
            ),
            tracing_enabled=_boolean("LANGSMITH_TRACING", False),
            capture_content=_boolean("LANGSMITH_CAPTURE_CONTENT", False),
            max_concurrency=max_concurrency,
        )

    def require_hosted(self) -> None:
        if not self.api_key:
            raise ConfigurationError(
                "LANGSMITH_API_KEY is required for hosted tracing, dataset sync, "
                "experiments, comparison, feedback, and re-evaluation. A local "
                "dry run with upload_results=False does not require it."
            )

    def client(self):
        """Construct the SDK client only when a hosted operation is requested."""

        self.require_hosted()
        from langsmith import Client

        return Client(
            api_url=self.endpoint,
            api_key=self.api_key,
            workspace_id=self.workspace_id,
            hide_inputs=not self.capture_content,
            hide_outputs=not self.capture_content,
        )
