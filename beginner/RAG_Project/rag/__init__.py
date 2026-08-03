"""Small, framework-neutral RAG application used in the Aspire workshop."""

from .config import Settings
from .pipeline import RAGApplication

__all__ = ["RAGApplication", "Settings"]
