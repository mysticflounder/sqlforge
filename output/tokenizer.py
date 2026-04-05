from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class TokenKind(StrEnum):
    WORD = "WORD"
    STRING = "STRING"
    NUMBER = "NUMBER"
    OP = "OP"
    PUNCT = "PUNCT"


class Token(BaseModel):
    kind: TokenKind
    value: str


def tokenize_sql(sql: str) -> list[Token]:
    """Tokenize a SQL string into typed tokens.

    Raises ValueError on unterminated strings, unsupported characters,
    or unrecognized input.
    """
    tokens: list[Token] = []
    i = 0
    n = len(sql)

    two_char_ops = {"<>", "!=", "<=", ">="}
    single_char_ops = set("=<>+-*/")
    punct_chars = set("(),;")

    while i < n:
        ch = sql[i]

        # Skip whitespace
        if ch in " \t\n\r":
            i += 1
            continue

        # Single-quoted string literal
        if ch == "'":
            i += 1
            buf: list[str] = []
            while i < n:
                c = sql[i]
                if c == "'":
                    # Check for escaped ''
                    if i + 1 < n and sql[i + 1] == "'":
                        buf.append("'")
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    buf.append(c)
                    i += 1
            else:
                raise ValueError("Unterminated string literal")
            tokens.append(Token(kind=TokenKind.STRING, value="".join(buf)))
            continue

        # Double-quoted identifier
        if ch == '"':
            i += 1
            buf = []
            while i < n:
                c = sql[i]
                if c == '"':
                    if i + 1 < n and sql[i + 1] == '"':
                        buf.append('"')
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    buf.append(c)
                    i += 1
            else:
                raise ValueError("Unterminated double-quoted identifier")
            tokens.append(Token(kind=TokenKind.WORD, value="".join(buf)))
            continue

        # Numbers: digit-started or dot-started (followed by digit)
        if ch.isdigit() or (ch == "." and i + 1 < n and sql[i + 1].isdigit()):
            start = i
            has_dot = False
            if ch == ".":
                has_dot = True
                i += 1
            while i < n and sql[i].isdigit():
                i += 1
            if not has_dot and i < n and sql[i] == ".":
                # Only consume the dot if it's followed by a digit or end
                # (spec: optional one dot)
                has_dot = True
                i += 1
                while i < n and sql[i].isdigit():
                    i += 1
            tokens.append(Token(kind=TokenKind.NUMBER, value=sql[start:i]))
            continue

        # Words / identifiers: letter or underscore start
        if ch.isalpha() or ch == "_":
            start = i
            while i < n and (sql[i].isalnum() or sql[i] == "_"):
                i += 1
            tokens.append(Token(kind=TokenKind.WORD, value=sql[start:i]))
            continue

        # Two-character operators (check before single-char)
        if i + 1 < n and sql[i : i + 2] in two_char_ops:
            tokens.append(Token(kind=TokenKind.OP, value=sql[i : i + 2]))
            i += 2
            continue

        # Single-character operators
        if ch in single_char_ops:
            tokens.append(Token(kind=TokenKind.OP, value=ch))
            i += 1
            continue

        # Punctuation
        if ch in punct_chars:
            tokens.append(Token(kind=TokenKind.PUNCT, value=ch))
            i += 1
            continue

        # Dot as punctuation (when not part of a number)
        if ch == ".":
            tokens.append(Token(kind=TokenKind.PUNCT, value="."))
            i += 1
            continue

        # Unsupported characters
        raise ValueError(f"Unsupported character: {ch!r}")

    return tokens
