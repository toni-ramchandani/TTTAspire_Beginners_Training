"""Testing-depth token demonstration for Beginner Day 1.

This is deliberately not a tokenizer architecture lesson. It shows why word
and character counts cannot replace model-aware token accounting.
"""

from __future__ import annotations

import tiktoken

try:
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError:  # Keep a readable fallback before dependencies are installed.
    Console = None  # type: ignore[assignment,misc]


SAMPLES = [
    "reset password",
    "reset-password",
    "Reset password 🔐",
    "पासवर्ड रीसेट करें",
]


def token_rows(encoding: tiktoken.Encoding) -> list[dict[str, object]]:
    """Return the comparison data independently of its terminal presentation."""
    rows: list[dict[str, object]] = []
    for text in SAMPLES:
        token_ids = encoding.encode(text)
        rows.append(
            {
                "text": text,
                "characters": len(text),
                "whitespace_words": len(text.split()),
                "tokens": len(token_ids),
                "token_ids": token_ids,
            }
        )
    return rows


def render_rich(rows: list[dict[str, object]], encoding_name: str) -> None:
    """Render token comparisons as a compact, trainer-friendly Rich table."""
    if Console is None:
        raise RuntimeError("Rich is not available")

    console = Console()
    console.print()
    console.print(
        Panel.fit(
            "[bold]Why words and characters cannot predict model tokens[/bold]\n"
            "[dim]Compare spacing, punctuation, emoji, and multilingual text.[/dim]",
            title="[bold cyan]Tokenization comparison[/bold cyan]",
            subtitle=f"[dim]encoding: {encoding_name}[/dim]",
            border_style="bright_cyan",
            padding=(1, 2),
        )
    )

    table = Table(
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=True,
        expand=True,
    )
    table.add_column("Input text", ratio=3)
    table.add_column("Characters", justify="right", style="blue")
    table.add_column("Words", justify="right", style="yellow")
    table.add_column("Tokens", justify="right", style="bold magenta")
    table.add_column("Token IDs", ratio=3, style="dim cyan")

    for row in rows:
        table.add_row(
            Text(str(row["text"]), style="bold"),
            str(row["characters"]),
            str(row["whitespace_words"]),
            str(row["tokens"]),
            ", ".join(str(token_id) for token_id in row["token_ids"]),
        )

    console.print()
    console.print(table)
    console.print(
        "[dim]Provider-reported usage remains authoritative for completed API requests.[/dim]"
    )


def render_plain(rows: list[dict[str, object]], encoding_name: str) -> None:
    """Retain the original output when Rich has not been installed."""
    print(f"encoding={encoding_name}")
    for row in rows:
        print(row)


def main() -> None:
    encoding_name = "o200k_base"
    encoding = tiktoken.get_encoding(encoding_name)
    rows = token_rows(encoding)
    if Console is not None:
        render_rich(rows, encoding_name)
    else:
        render_plain(rows, encoding_name)


if __name__ == "__main__":
    main()
