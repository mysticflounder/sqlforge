"""General-purpose SQL tokenizer for sqlforge.

Produces typed tokens (Token with kind and value) from SQL strings.
Handles string literals, numbers, operators, and identifiers — everything
needed for DML statement parsing.
"""

from enum import StrEnum

from pydantic import BaseModel


class TokenKind(StrEnum):
    """Token type classification."""

    WORD = "WORD"
    STRING = "STRING"
    NUMBER = "NUMBER"
    OP = "OP"
    PUNCT = "PUNCT"


class Token(BaseModel):
    """A single lexical token with its kind and value."""

    kind: TokenKind
    value: str


_PUNCT = frozenset("(),;")
_SINGLE_OPS = frozenset("=<>+-*/")
_TWO_CHAR_OPS = frozenset({"<>", "!=", "<=", ">="})
_REJECT = frozenset({"`", "["})


def tokenize_sql(sql: str) -> list[Token]:
    """Tokenize a SQL string into typed tokens.

    Raises ValueError on unterminated strings, unsupported characters,
    or unrecognized input.
    """
    tokens: list[Token] = []
    i = 0
    n = len(sql)

    while i < n:
        ch = sql[i]

        # Whitespace — skip
        if ch.isspace():
            i += 1
            continue

        # Rejected characters
        if ch in _REJECT:
            raise ValueError(f"unsupported character: {ch!r}")

        # String literal
        if ch == "'":
            value, i = _scan_string(sql, i, "'")
            tokens.append(Token(kind=TokenKind.STRING, value=value))
            continue

        # Double-quoted identifier
        if ch == '"':
            value, i = _scan_string(sql, i, '"')
            tokens.append(Token(kind=TokenKind.WORD, value=value))
            continue

        # Number literal (digit, or . followed by digit)
        if ch.isdigit() or (ch == "." and i + 1 < n and sql[i + 1].isdigit()):
            value, i = _scan_number(sql, i)
            tokens.append(Token(kind=TokenKind.NUMBER, value=value))
            continue

        # Two-character operators
        if i + 1 < n and sql[i : i + 2] in _TWO_CHAR_OPS:
            tokens.append(Token(kind=TokenKind.OP, value=sql[i : i + 2]))
            i += 2
            continue

        # Single-character operators
        if ch in _SINGLE_OPS:
            # ! alone is not valid — only != (handled above)
            tokens.append(Token(kind=TokenKind.OP, value=ch))
            i += 1
            continue

        # ! not followed by = is an error
        if ch == "!":
            raise ValueError(f"unexpected character: {ch!r}")

        # Punctuation
        if ch in _PUNCT:
            tokens.append(Token(kind=TokenKind.PUNCT, value=ch))
            i += 1
            continue

        # . as punctuation (not part of a number)
        if ch == ".":
            tokens.append(Token(kind=TokenKind.PUNCT, value=ch))
            i += 1
            continue

        # Word token (identifier or keyword)
        if ch.isalpha() or ch == "_":
            value, i = _scan_word(sql, i)
            tokens.append(Token(kind=TokenKind.WORD, value=value))
            continue

        # Unrecognized
        raise ValueError(f"unexpected character: {ch!r}")

    return tokens


def _scan_string(sql: str, start: int, quote: str) -> tuple[str, int]:
    """Scan a quoted string starting at position start. Returns (value, new_index)."""
    i = start + 1  # skip opening quote
    buf: list[str] = []
    n = len(sql)

    while i < n:
        ch = sql[i]
        if ch == quote:
            # Check for escaped quote (doubled)
            if i + 1 < n and sql[i + 1] == quote:
                buf.append(quote)
                i += 2
            else:
                # End of string
                return "".join(buf), i + 1
        else:
            buf.append(ch)
            i += 1

    raise ValueError(f"unterminated {quote}-quoted string starting at position {start}")


def _scan_number(sql: str, start: int) -> tuple[str, int]:
    """Scan a numeric literal starting at position start. Returns (value, new_index)."""
    i = start
    n = len(sql)
    has_dot = False
    buf: list[str] = []

    while i < n:
        ch = sql[i]
        if ch.isdigit():
            buf.append(ch)
            i += 1
        elif ch == "." and not has_dot:
            has_dot = True
            buf.append(ch)
            i += 1
        else:
            break

    return "".join(buf), i


def _scan_word(sql: str, start: int) -> tuple[str, int]:
    """Scan a word token (identifier/keyword) starting at position start."""
    i = start
    n = len(sql)
    buf: list[str] = []

    while i < n:
        ch = sql[i]
        if ch.isalnum() or ch == "_":
            buf.append(ch)
            i += 1
        else:
            break

    return "".join(buf), i
