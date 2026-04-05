"""INSERT INTO statement parser and executor for sqlforge."""

from __future__ import annotations

from pydantic import BaseModel

from sqlforge.storage import Database
from sqlforge.tokenizer import Token, TokenKind, tokenize_sql


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
    pos = 0
    n = len(tokens)

    def peek() -> Token | None:
        return tokens[pos] if pos < n else None

    def consume() -> Token:
        nonlocal pos
        if pos >= n:
            raise ValueError("unexpected end of input")
        tok = tokens[pos]
        pos += 1
        return tok

    def expect_keyword(word: str) -> Token:
        tok = consume()
        if tok.kind != TokenKind.WORD or tok.value.upper() != word.upper():
            raise ValueError(f"expected {word!r}, got {tok.value!r}")
        return tok

    def expect_punct(ch: str) -> Token:
        tok = consume()
        if tok.kind != TokenKind.PUNCT or tok.value != ch:
            raise ValueError(f"expected {ch!r}, got {tok.value!r}")
        return tok

    # INSERT
    expect_keyword("INSERT")

    # INTO
    expect_keyword("INTO")

    # table name — must be a WORD and not a keyword like VALUES
    tok = consume()
    if tok.kind != TokenKind.WORD:
        raise ValueError(f"expected table name, got {tok.value!r}")
    # Reject if it's the VALUES keyword (missing table name case)
    if tok.value.upper() == "VALUES":
        raise ValueError("expected table name, got 'VALUES'")
    table_name = tok.value

    # Optional column list: ( col, col, ... )
    columns: list[str] | None = None
    nxt = peek()
    if nxt is not None and nxt.kind == TokenKind.PUNCT and nxt.value == "(":
        consume()  # consume (
        # Check for empty column list
        nxt2 = peek()
        if nxt2 is not None and nxt2.kind == TokenKind.PUNCT and nxt2.value == ")":
            raise ValueError("empty column list is not allowed")
        columns = []
        while True:
            col_tok = consume()
            if col_tok.kind != TokenKind.WORD:
                raise ValueError(f"expected column name, got {col_tok.value!r}")
            columns.append(col_tok.value)
            sep = consume()
            if sep.kind == TokenKind.PUNCT and sep.value == ")":
                break
            elif sep.kind == TokenKind.PUNCT and sep.value == ",":
                continue
            else:
                raise ValueError(f"expected ',' or ')', got {sep.value!r}")

        # Now expect VALUES keyword
        expect_keyword("VALUES")
    else:
        # Must be VALUES keyword
        tok2 = consume()
        if tok2.kind != TokenKind.WORD or tok2.value.upper() != "VALUES":
            raise ValueError(f"expected 'VALUES', got {tok2.value!r}")

    # ( value, value, ... )
    expect_punct("(")

    # Check for empty value list
    nxt3 = peek()
    if nxt3 is not None and nxt3.kind == TokenKind.PUNCT and nxt3.value == ")":
        raise ValueError("empty value list is not allowed")

    values: list[Value] = []
    while True:
        val_tok = consume()

        if val_tok.kind == TokenKind.WORD and val_tok.value.upper() == "NULL":
            values.append(Value(raw=None))
        elif val_tok.kind == TokenKind.NUMBER:
            raw_num: int | float
            if "." in val_tok.value:
                raw_num = float(val_tok.value)
            else:
                raw_num = int(val_tok.value)
            values.append(Value(raw=raw_num))
        elif val_tok.kind == TokenKind.STRING:
            values.append(Value(raw=val_tok.value))
        else:
            raise ValueError(f"unexpected token in value list: {val_tok.value!r}")

        sep = consume()
        if sep.kind == TokenKind.PUNCT and sep.value == ")":
            break
        elif sep.kind == TokenKind.PUNCT and sep.value == ",":
            continue
        else:
            raise ValueError(f"expected ',' or ')', got {sep.value!r}")

    # Optional trailing semicolon — consume it if present
    nxt4 = peek()
    if nxt4 is not None and nxt4.kind == TokenKind.PUNCT and nxt4.value == ";":
        consume()

    # Any remaining tokens are an error
    if pos < n:
        raise ValueError(f"unexpected trailing tokens after INSERT statement")

    return InsertStatement(table_name=table_name, columns=columns, values=values)


def execute_insert(stmt: InsertStatement, db: Database) -> int:
    """Execute an INSERT statement against the database. Returns the rowid."""
    # Raises ValueError if the table does not exist (from db.get_column_names / db.insert)
    if stmt.columns is not None:
        # Named column insert
        if len(stmt.columns) != len(stmt.values):
            raise ValueError(
                f"column count ({len(stmt.columns)}) does not match "
                f"value count ({len(stmt.values)})"
            )
        row_dict = {col: val.raw for col, val in zip(stmt.columns, stmt.values)}
    else:
        # Positional insert — map values by schema order
        schema_cols = db.get_column_names(stmt.table_name)
        if len(stmt.values) != len(schema_cols):
            raise ValueError(
                f"value count ({len(stmt.values)}) does not match "
                f"column count ({len(schema_cols)}) for positional INSERT"
            )
        row_dict = {col: val.raw for col, val in zip(schema_cols, stmt.values)}

    return db.insert(stmt.table_name, row_dict)
