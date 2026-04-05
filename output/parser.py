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
        pks = sum(1 for c in v if c.primary_key)
        if pks > 1:
            raise ValueError("table may have at most one column-level PRIMARY KEY")
        return v


def tokenize(sql: str) -> list[str]:
    """Split a SQL string into tokens. Raises ValueError on quoted identifiers."""
    rejected = {"'", '"', "`", "["}
    punctuation = set("(),;.")
    result: list[str] = []
    word: list[str] = []

    for ch in sql:
        if ch in rejected:
            raise ValueError(f"unsupported character: {ch!r}")
        if ch in punctuation:
            if word:
                result.append("".join(word))
                word = []
            result.append(ch)
        elif ch.isspace():
            if word:
                result.append("".join(word))
                word = []
        else:
            word.append(ch)

    if word:
        result.append("".join(word))
    return result


def _token_at(tokens: list[str], pos: int) -> str:
    """Return token at pos or empty string if out of bounds."""
    return tokens[pos] if pos < len(tokens) else ""


def _skip_length_specifier(tokens: list[str], pos: int) -> int:
    """Skip past a parenthesized length specifier starting at pos. Returns new pos."""
    pos += 1  # skip opening paren
    depth = 1
    while depth > 0:
        t = tokens[pos]
        pos += 1
        if t == "(":
            depth += 1
        elif t == ")":
            depth -= 1
    return pos


def _read_constraints(tokens: list[str], pos: int) -> tuple[list[str], str, int]:
    """Read constraint tokens until a comma or closing paren.

    Returns (constraints, delimiter, new_pos). Raises ValueError on ( in constraints.
    """
    constraints: list[str] = []
    while _token_at(tokens, pos) not in ("", ",", ")"):
        t = tokens[pos]
        if t == "(":
            raise ValueError("parenthesized expression not supported in column constraints")
        constraints.append(t)
        pos += 1
    delim = _token_at(tokens, pos)
    if delim:
        pos += 1
    return constraints, delim, pos


def _has_not_null(constraints: list[str]) -> bool:
    """Return True if NOT NULL sequence appears in constraints."""
    for idx in range(len(constraints) - 1):
        if constraints[idx].upper() == "NOT" and constraints[idx + 1].upper() == "NULL":
            return True
    return False


def _has_primary_key(constraints: list[str]) -> bool:
    """Return True if PRIMARY KEY sequence appears in constraints."""
    for idx in range(len(constraints) - 1):
        if constraints[idx].upper() == "PRIMARY" and constraints[idx + 1].upper() == "KEY":
            return True
    return False


def parse_create_table(sql: str) -> Table:  # noqa: C901
    """Parse a CREATE TABLE statement. Raises ValueError on unsupported syntax."""
    tokens = tokenize(sql)
    total = len(tokens)
    pos = 0

    # Expect CREATE
    if not tokens or tokens[0].upper() != "CREATE":
        raise ValueError("statement must begin with CREATE")
    pos = 1

    # Reject TEMP / TEMPORARY
    if _token_at(tokens, pos).upper() in ("TEMP", "TEMPORARY"):
        raise ValueError("TEMP/TEMPORARY tables are not supported")

    # Expect TABLE
    if _token_at(tokens, pos).upper() != "TABLE":
        raise ValueError(f"expected TABLE, got {_token_at(tokens, pos)!r}")
    pos += 1

    # Optional IF NOT EXISTS
    if (
        pos + 2 < total
        and tokens[pos].upper() == "IF"
        and tokens[pos + 1].upper() == "NOT"
        and tokens[pos + 2].upper() == "EXISTS"
    ):
        pos += 3

    # Table name — reject schema prefix
    table_name = tokens[pos]
    pos += 1
    if _token_at(tokens, pos) == ".":
        raise ValueError("schema-qualified table names are not supported")

    # Expect opening paren
    if _token_at(tokens, pos) != "(":
        raise ValueError(f"expected '(', got {_token_at(tokens, pos)!r}")
    pos += 1

    # Parse column definitions
    columns: list[Column] = []
    while True:
        if _token_at(tokens, pos) == ")":
            pos += 1
            break

        col_name = tokens[pos]
        pos += 1

        raw_type = tokens[pos].upper()
        pos += 1
        try:
            col_type = ColumnType(raw_type)
        except ValueError:
            raise ValueError(f"unsupported column type: {raw_type!r}") from None

        # Discard length specifier if present
        if _token_at(tokens, pos) == "(":
            pos = _skip_length_specifier(tokens, pos)

        # Collect constraints up to , or )
        constraints, delim, pos = _read_constraints(tokens, pos)

        nullable = not _has_not_null(constraints)
        is_pk = _has_primary_key(constraints)

        # INTEGER PRIMARY KEY is implicitly NOT NULL
        if is_pk and col_type == ColumnType.INTEGER:
            nullable = False

        columns.append(Column(name=col_name, type=col_type, nullable=nullable, primary_key=is_pk))

        if delim == ",":
            # Trailing comma check
            if _token_at(tokens, pos) == ")":
                raise ValueError("trailing comma before closing parenthesis")
        elif delim == ")":
            break

    # Reject WITHOUT ROWID
    for j in range(pos, total):
        if tokens[j].upper() == "WITHOUT":
            raise ValueError("WITHOUT ROWID is not supported")

    # Reject empty column list
    if not columns:
        raise ValueError("CREATE TABLE must define at least one column")

    return Table(name=table_name, columns=columns)
