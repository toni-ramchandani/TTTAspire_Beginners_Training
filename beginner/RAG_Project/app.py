"""Command-line entry point for the workshop RAG application."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rag.chunking import load_document_chunks
from rag.config import ConfigurationError, Settings
from rag.pipeline import RAGApplication
from rag.providers import ProviderError

PROJECT_ROOT = Path(__file__).resolve().parent

DEMO_QUESTIONS = (
    "I changed phones and cannot complete MFA. How do I regain payroll access?",
    "Can my manager approve a temporary MFA bypass because payroll closes today?",
    "What information must the help desk record in an MFA recovery ticket?",
)


def add_provider_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider",
        choices=("ollama", "openai"),
        help="Override RAG_PROVIDER for this command.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and query a small payroll-MFA RAG application."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "inspect",
        help="Show the deterministic document chunks without calling a model.",
    )

    build = subparsers.add_parser("build", help="Embed the documents and save an index.")
    add_provider_argument(build)

    ask = subparsers.add_parser("ask", help="Retrieve evidence and generate one answer.")
    ask.add_argument("question", help="The payroll-MFA question to answer.")
    ask.add_argument("--top-k", type=int, help="Number of chunks to retrieve.")
    ask.add_argument(
        "--show-context",
        action="store_true",
        help="Print the full retrieved evidence blocks.",
    )
    add_provider_argument(ask)

    demo = subparsers.add_parser("demo", help="Run three supplied questions live.")
    demo.add_argument("--top-k", type=int, help="Number of chunks to retrieve.")
    demo.add_argument("--show-context", action="store_true")
    add_provider_argument(demo)
    return parser


def print_trace(trace: object, trace_path: Path, show_context: bool) -> None:
    # Local import keeps the CLI entry point simple while retaining type-safe models.
    from rag.models import RAGTrace

    if not isinstance(trace, RAGTrace):
        raise TypeError("Expected a RAGTrace.")

    print(f"\nQuestion\n{trace.question}")
    print(f"\nAnswer\n{trace.answer}")
    print("\nRetrieved evidence")
    for position, item in enumerate(trace.retrieved, start=1):
        print(
            f"{position}. {item.chunk.chunk_id} | score={item.score:.4f} | "
            f"{item.chunk.source_file}"
        )
        if show_context:
            print(item.chunk.context_text())
            print()
    print(f"\nTrace saved: {trace_path.relative_to(PROJECT_ROOT)}")


def run(arguments: argparse.Namespace) -> int:
    if arguments.command == "inspect":
        chunks = load_document_chunks(PROJECT_ROOT / "documents")
        print(f"Documents were split into {len(chunks)} chunks:\n")
        for chunk in chunks:
            print(f"- {chunk.chunk_id} | {chunk.source_file} | {chunk.section_title}")
        return 0

    settings = Settings.from_env(PROJECT_ROOT, arguments.provider)
    application = RAGApplication(PROJECT_ROOT, settings)

    if arguments.command == "build":
        index = application.build_index()
        print(
            f"Built {len(index.chunks)} chunks with "
            f"{index.provider}/{index.embedding_model}."
        )
        print(f"Index saved: {application.index_path.relative_to(PROJECT_ROOT)}")
        return 0

    if arguments.command == "ask":
        trace, trace_path = application.ask(arguments.question, arguments.top_k)
        print_trace(trace, trace_path, arguments.show_context)
        return 0

    if arguments.command == "demo":
        for question in DEMO_QUESTIONS:
            trace, trace_path = application.ask(question, arguments.top_k)
            print_trace(trace, trace_path, arguments.show_context)
            print("\n" + "=" * 72)
        return 0

    raise ValueError(f"Unknown command: {arguments.command}")


def main() -> int:
    try:
        return run(build_parser().parse_args())
    except (ConfigurationError, ProviderError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
