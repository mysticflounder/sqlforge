"""INSERT INTO statement parser and executor for sqlforge."""

from __future__ import annotations

from pydantic import BaseModel

from .storage import Database
from .tokenizer import Token, TokenKind, tokenize_sql


class Value(BaseModel):
    """A literal value in a SQL statement."""

    raw: int | float | str | None


class InsertStatement(BaseModel):
    """A parsed INSERT INTO statement."""

    table_name: str
    columns: list[str] | None = None
    values: list[Value]


def parse_insert(sql: str) -> InsertStatement:
    """Parse an INSERT INTO ... VALUES (...) statement.

    Raises ValueError on syntax errors or unsupported features.
    """
    tokens = tokenize_sql(sql)
    n = len(tokens)
    i = 0

    # Step 1: INSERT
    if i >= n or not _match_word(tokens[i], "INSERT"):
        raise ValueError("expected INSERT")
    i += 1

    # Step 2: INTO
    if i >= n or not _match_word(tokens[i], "INTO"):
        raise ValueError("expected INTO")
    i += 1

    # Step 3: table name
    if i >= n or tokens[i].kind != TokenKind.WORD:
        raise ValueError("expected table name")
    table_name = tokens[i].value
    i += 1

    # Step 4: optional column list
    columns: list[str] | None = None
    if i < n and tokens[i] == Token(kind=TokenKind.PUNCT, value="("):
        i += 1  # skip (
        columns = []
        while True:
            if i >= n:
                raise ValueError("unterminated column list")
            if tokens[i] == Token(kind=TokenKind.PUNCT, value=")"):
                i += 1
                break
            if tokens[i].kind != TokenKind.WORD:
                raise ValueError(f"expected column name, got {tokens[i].value!r}")
            columns.append(tokens[i].value)
            i += 1
            # expect , or )
            if i < n and tokens[i] == Token(kind=TokenKind.PUNCT, value=","):
                i += 1
        if not columns:
            raise ValueError("empty column list")

    # Step 5: VALUES
    if i >= n or not _match_word(tokens[i], "VALUES"):
        raise ValueError("expected VALUES")
    i += 1

    # Step 6: ( value list )
    if i >= n or tokens[i] != Token(kind=TokenKind.PUNCT, value="("):
        raise ValueError("expected '(' after VALUES")
    i += 1

    values: list[Value] = []
    while True:
        if i >= n:
            raise ValueError("unterminated value list")
        if tokens[i] == Token(kind=TokenKind.PUNCT, value=")"):
            i += 1
            break
        values.append(_parse_value(tokens[i]))
        i += 1
        # expect , or )
        if i < n and tokens[i] == Token(kind=TokenKind.PUNCT, value=","):
            i += 1

    if not values:
        raise ValueError("empty value list")

    # Step 7: check for trailing tokens (allow optional ;)
    if i < n:
        if tokens[i] == Token(kind=TokenKind.PUNCT, value=";"):
            i += 1
        if i < n:
            raise ValueError(f"unexpected token after INSERT statement: {tokens[i].value!r}")

    return InsertStatement(table_name=table_name, columns=columns, values=values)


def execute_insert(statement: InsertStatement, db: Database) -> int:
    """Execute a parsed INSERT statement against a Database. Returns the rowid."""
    column_names = statement.columns
    if column_names is None:
        # Positional insert — map by schema column order
        column_names = db.get_column_names(statement.table_name)
        if len(statement.values) != len(column_names):
            raise ValueError(
                f"expected {len(column_names)} values, got {len(statement.values)}"
            )
    else:
        if len(statement.columns) != len(statement.values):
            raise ValueError(
                f"column count ({len(statement.columns)}) does not match "
                f"value count ({len(statement.values)})"
            )

    values_dict = {col: val.raw for col, val in zip(column_names, statement.values)}
    return db.insert(statement.table_name, values_dict)


def _match_word(token: Token, keyword: str) -> bool:
    """Check if a token is a WORD matching the keyword (case-insensitive)."""
    return token.kind == TokenKind.WORD and token.value.upper() == keyword.upper()


def _parse_value(token: Token) -> Value:
    """Parse a single value token into a Value."""
    if token.kind == TokenKind.NUMBER:
        if "." in token.value:
            return Value(raw=float(token.value))
        return Value(raw=int(token.value))
    if token.kind == TokenKind.STRING:
        return Value(raw=token.value)
    if token.kind == TokenKind.WORD and token.value.upper() == "NULL":
        return Value(raw=None)
    raise ValueError(f"unexpected token in value position: {token.value!r}")
