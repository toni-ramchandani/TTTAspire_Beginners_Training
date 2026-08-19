"""Load Markdown documents and split them at level-two headings."""

from __future__ import annotations

import re
from pathlib import Path

from .models import DocumentChunk

CHUNKER_VERSION = "markdown-section-v1"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "section"


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text

    closing = text.find("\n---\n", 4)
    if closing == -1:
        raise ValueError("Markdown front matter is missing its closing '---'.")

    metadata: dict[str, str] = {}
    for raw_line in text[4:closing].splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        key, separator, value = raw_line.partition(":")
        if not separator:
            raise ValueError(f"Invalid front-matter line: {raw_line!r}")
        metadata[key.strip()] = value.strip().strip('"').strip("'")

    return metadata, text[closing + 5 :]


def split_markdown_document(path: Path) -> list[DocumentChunk]:
    raw_text = path.read_text(encoding="utf-8")
    metadata, body = _split_front_matter(raw_text)

    document_id = metadata.get("document_id", path.stem)
    document_version = metadata.get("version", "unversioned")
    configured_title = metadata.get("title")

    h1_match = re.search(r"^#\s+(.+?)\s*$", body, flags=re.MULTILINE)
    document_title = configured_title or (
        h1_match.group(1) if h1_match else path.stem.replace("_", " ")
    )

    section_matches = list(re.finditer(r"^##\s+(.+?)\s*$", body, flags=re.MULTILINE))
    if not section_matches:
        raise ValueError(f"{path.name} must contain at least one level-two heading.")

    chunks: list[DocumentChunk] = []
    seen_ids: set[str] = set()
    for index, match in enumerate(section_matches):
        section_title = match.group(1).strip()
        start = match.end()
        end = section_matches[index + 1].start() if index + 1 < len(section_matches) else len(body)
        section_text = body[start:end].strip()
        if not section_text:
            continue

        base_id = f"{document_id}::{_slug(section_title)}"
        chunk_id = base_id
        suffix = 2
        while chunk_id in seen_ids:
            chunk_id = f"{base_id}-{suffix}"
            suffix += 1
        seen_ids.add(chunk_id)

        chunks.append(
            DocumentChunk(
                chunk_id=chunk_id,
                document_id=document_id,
                document_title=document_title,
                document_version=document_version,
                section_title=section_title,
                source_file=path.name,
                text=section_text,
            )
        )

    return chunks


def load_document_chunks(documents_dir: Path) -> list[DocumentChunk]:
    paths = sorted(documents_dir.glob("*.md"))
    if not paths:
        raise FileNotFoundError(f"No Markdown documents found in {documents_dir}.")

    chunks: list[DocumentChunk] = []
    for path in paths:
        chunks.extend(split_markdown_document(path))

    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("Chunk IDs must be unique across the document collection.")
    return chunks
