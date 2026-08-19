"""Small, framework-neutral RAG application used in the Aspire workshop.

Imports are lazy so dataset and corpus validation can run before optional
runtime/provider dependencies are installed.
"""

from typing import Any

__all__ = ["RAGApplication", "Settings"]


def __getattr__(name: str) -> Any:
    if name == "Settings":
        from .config import Settings

        return Settings
    if name == "RAGApplication":
        from .pipeline import RAGApplication

        return RAGApplication
    raise AttributeError(name)
