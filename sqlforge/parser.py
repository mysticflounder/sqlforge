from enum import StrEnum

from pydantic import BaseModel, field_validator


class ColumnType(StrEnum):
    """SQLite type affinity — exact case-insensitive match only (no substring affinity)."""

    INTEGER = "INTEGER"
    TEXT = "TEXT"
    REAL = "REAL"
    BLOB = "BLOB"
    NUMERIC = "NUMERIC"


class Column(BaseModel):
    """A single column in a CREATE TABLE statement."""

    name: str
    type: ColumnType
    nullable: bool = True
    primary_key: bool = False


class Table(BaseModel):
    """A parsed CREATE TABLE statement."""

    name: str
    columns: list[Column]

    @field_validator("columns")
    @classmethod
    def at_most_one_column_level_primary_key(cls: type["Table"], v: list[Column]) -> list[Column]:
        """Validate that at most one column-level PRIMARY KEY is declared."""
        if sum(1 for c in v if c.primary_key) > 1:
            raise ValueError("table may have at most one column-level PRIMARY KEY")
        return v


def tokenize(sql: str) -> list[str]:
    """Split a SQL string into tokens. Raises ValueError on quoted identifiers."""
    punct = set("(),;.")
    reject = {"'", '"', "`", "["}
    tokens: list[str] = []
    buf: list[str] = []

    for ch in sql:
        if ch in reject:
            raise ValueError(f"unsupported character in SQL: {ch!r}")
        if ch in punct:
            if buf:
                tokens.append("".join(buf))
                buf = []
            tokens.append(ch)
        elif ch.isspace():
            if buf:
                tokens.append("".join(buf))
                buf = []
        else:
            buf.append(ch)

    if buf:
        tokens.append("".join(buf))
    return tokens


def _peek_at(tokens: list[str], i: int) -> str:
    """Return the token at position i, or empty string if out of range."""
    return tokens[i] if i < len(tokens) else ""


def _consume_length_specifier(tokens: list[str], i: int) -> int:
    """Consume and discard a parenthesized length specifier starting at i. Returns new index."""
    i += 1  # skip opening (
    depth = 1
    while depth > 0:
        tok = tokens[i]
        i += 1
        if tok == "(":
            depth += 1
        elif tok == ")":
            depth -= 1
    return i


def _collect_constraint_tokens(tokens: list[str], i: int) -> tuple[list[str], str, int]:
    """Collect constraint tokens until a comma or closing paren delimiter.

    Returns (constraint_tokens, delimiter, new_index). Raises ValueError if ( found in constraints.
    """
    constraint_tokens: list[str] = []
    while _peek_at(tokens, i) not in ("", ",", ")"):
        tok = tokens[i]
        if tok == "(":
            raise ValueError("parenthesized expression in column constraints is not supported")
        constraint_tokens.append(tok)
        i += 1
    delimiter = _peek_at(tokens, i)
    if delimiter:
        i += 1
    return constraint_tokens, delimiter, i


def _scan_not_null(constraint_tokens: list[str]) -> bool:
    """Return True if constraint_tokens contains NOT NULL, False otherwise."""
    for j in range(len(constraint_tokens) - 1):
        if constraint_tokens[j].upper() == "NOT" and constraint_tokens[j + 1].upper() == "NULL":
            return True
    return False


def _scan_primary_key(constraint_tokens: list[str]) -> bool:
    """Return True if constraint_tokens contains PRIMARY KEY, False otherwise."""
    for j in range(len(constraint_tokens) - 1):
        if constraint_tokens[j].upper() == "PRIMARY" and constraint_tokens[j + 1].upper() == "KEY":
            return True
    return False


def parse_create_table(sql: str) -> Table:  # noqa: C901
    """Parse a CREATE TABLE statement. Raises ValueError on unsupported syntax."""
    tokens = tokenize(sql)
    n = len(tokens)
    i = 0

    # Step 1: Expect CREATE
    if not tokens or tokens[0].upper() != "CREATE":
        raise ValueError("expected CREATE TABLE statement")
    i = 1

    # Step 2: Reject TEMP/TEMPORARY
    if _peek_at(tokens, i).upper() in ("TEMP", "TEMPORARY"):
        raise ValueError("TEMP/TEMPORARY tables are not supported")

    # Step 3: Expect TABLE
    if _peek_at(tokens, i).upper() != "TABLE":
        raise ValueError(f"expected 'TABLE', got {_peek_at(tokens, i)!r}")
    i += 1

    # Step 4: Skip IF NOT EXISTS
    if (
        i + 2 < n
        and tokens[i].upper() == "IF"
        and tokens[i + 1].upper() == "NOT"
        and tokens[i + 2].upper() == "EXISTS"
    ):
        i += 3

    # Step 5: Read table name; reject schema prefix
    table_name = tokens[i]
    i += 1
    if _peek_at(tokens, i) == ".":
        raise ValueError("schema prefix in table name is not supported")

    # Step 6: Expect (
    if _peek_at(tokens, i) != "(":
        raise ValueError(f"expected '(', got {_peek_at(tokens, i)!r}")
    i += 1

    # Step 7: Parse columns
    columns: list[Column] = []
    while True:
        if _peek_at(tokens, i) == ")":
            i += 1
            break

        # 7a: column name
        col_name = tokens[i]
        i += 1

        # 7b: type token
        type_tok = tokens[i].upper()
        i += 1
        try:
            col_type = ColumnType(type_tok)
        except ValueError:
            raise ValueError(f"unknown column type: {type_tok!r}") from None

        # 7c: optional length specifier — consume and discard
        if _peek_at(tokens, i) == "(":
            i = _consume_length_specifier(tokens, i)

        # 7d-7g: collect and scan constraints
        constraint_tokens, delimiter, i = _collect_constraint_tokens(tokens, i)

        nullable = not _scan_not_null(constraint_tokens)
        primary_key = _scan_primary_key(constraint_tokens)

        # 7h: INTEGER PRIMARY KEY implies NOT NULL
        if primary_key and col_type == ColumnType.INTEGER:
            nullable = False

        columns.append(
            Column(name=col_name, type=col_type, nullable=nullable, primary_key=primary_key)
        )

        # 7i: trailing comma check
        if delimiter == ",":
            if _peek_at(tokens, i) == ")":
                raise ValueError("trailing comma before closing parenthesis")
        elif delimiter == ")":
            break

    # Step 8: scan remaining tokens for WITHOUT
    for j in range(i, n):
        if tokens[j].upper() == "WITHOUT":
            raise ValueError("WITHOUT ROWID is not supported")

    # Step 9: reject empty column list
    if not columns:
        raise ValueError("table must have at least one column")

    return Table(name=table_name, columns=columns)
