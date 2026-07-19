"""Testing-depth token demonstration for Beginner Day 1.

This is deliberately not a tokenizer architecture lesson. It shows why word
and character counts cannot replace model-aware token accounting.
"""

from __future__ import annotations

import tiktoken


SAMPLES = [
    "reset password",
    "reset-password",
    "Reset password 🔐",
    "पासवर्ड रीसेट करें",
]


def main() -> None:
    encoding = tiktoken.get_encoding("o200k_base")
    print("encoding=o200k_base")
    for text in SAMPLES:
        token_ids = encoding.encode(text)
        print(
            {
                "text": text,
                "characters": len(text),
                "whitespace_words": len(text.split()),
                "tokens": len(token_ids),
                "token_ids": token_ids,
            }
        )


if __name__ == "__main__":
    main()

