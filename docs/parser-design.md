# sqlforge: SQL CREATE TABLE Parser — Design Spec

**Date:** 2026-03-17
**Status:** Draft
**Project:** sqlforge (SQLite reference implementation built with specforge)
**Scope:** `parser` module — v1 slice

---

## Overview

A single-module SQLite `CREATE TABLE` parser built as the first slice of sqlforge, a SQLite reference implementation built *using* specforge. The goal is to validate the specforge method on a small, well-bounded problem before tackling the full SQLite engine.

The parser takes a SQL `CREATE TABLE` string and returns structured Pydantic models representing the table schema. It is the foundation for future modules (storage, query execution) and must produce correct data models that downstream code can rely on.

---

## Data Models

Three Pydantic types defined in `parser.py`:

```python
class ColumnType(StrEnum):
    INTEGER = "INTEGER"
    TEXT = "TEXT"
    REAL = "REAL"
    BLOB = "BLOB"
    NUMERIC = "NUMERIC"
```

The five SQLite type affinities. `StrEnum` (Python 3.11+) serializes values as plain strings (e.g. `"INTEGER"`) rather than `<ColumnType.INTEGER: 'INTEGER'>`.

**Important:** v1 uses exact (case-insensitive) matching against these five names only. SQLite's full affinity rules derive type from substrings of arbitrary declared type names (e.g. `VARCHAR` → TEXT, `DOUBLE PRECISION` → REAL). That behavior is out of scope. Unknown type names raise `ValueError`.

```python
class Column(BaseModel):
    name: str           # original case preserved
    type: ColumnType
    nullable: bool = True
    primary_key: bool = False
```

`nullable` defaults to `True` (SQLite's default). The parser sets it `False` when:
- `NOT NULL` is explicitly declared, OR
- `primary_key=True AND type == ColumnType.INTEGER` — `INTEGER PRIMARY KEY` is a rowid alias and SQLite enforces NOT NULL. Other primary key types (`TEXT PRIMARY KEY`, etc.) allow NULL per SQLite's historical behavior and are left `nullable=True` unless explicitly declared `NOT NULL`.

The standalone `NULL` keyword as an explicit constraint (e.g. `id INTEGER PRIMARY KEY NULL`) is silently ignored — it is consumed as an unknown constraint token by step 7g and has no effect on `nullable`. For `INTEGER PRIMARY KEY`, step 7h sets `nullable=False` unconditionally regardless.

```python
class Table(BaseModel):
    name: str               # original case preserved
    columns: list[Column]   # order matches declaration order in SQL

    @field_validator("columns")
    @classmethod
    def at_most_one_column_level_primary_key(cls: type["Table"], v: list[Column]) -> list[Column]:
        """Validate that at most one column-level PRIMARY KEY is declared."""
        if sum(1 for c in v if c.primary_key) > 1:
            raise ValueError("table may have at most one column-level PRIMARY KEY")
        return v
```

Column order in the output list matches declaration order in the SQL statement. The validator fires at model construction time (not during parsing) and raises `ValueError` if more than one column carries `primary_key=True`. This matches SQLite's enforcement: two column-level `PRIMARY KEY` declarations is a syntax error. Composite `PRIMARY KEY (a, b)` via table-level constraint is out of scope for v1 and is not parsed.

---

## Functions

### `tokenize(sql: str) -> list[str]`

Splits a SQL string into a flat list of tokens. Words are delimited by whitespace. The characters `(`, `)`, `,`, `;`, `.` are always emitted as separate single-character tokens.

**Case preservation:** tokens are returned in their original case. The parser is responsible for uppercasing when comparing against keywords and type names.

**Raises `ValueError`** if the input contains any of: `'`, `"`, `` ` ``, `[` — quoted identifiers and string literals are not supported in v1. Callers receive an explicit error rather than silent misparse.

Test cases:
- Basic `CREATE TABLE foo (id INTEGER)` splits correctly
- Punctuation `(`, `)`, `,`, `;`, `.` become separate tokens
- Whitespace and newlines produce no empty tokens
- Mixed-case input is returned as-is (not uppercased)
- Single-quote `'` raises `ValueError`
- Double-quote `"` raises `ValueError`
- Backtick `` ` `` raises `ValueError`
- Opening bracket `[` raises `ValueError`

### `parse_create_table(sql: str) -> Table`

Parses a `CREATE TABLE` statement using `tokenize`, returns a `Table`.

**Token comparison:** all keyword and type comparisons are done case-insensitively (tokens uppercased at comparison sites only). Table and column names are stored in original case.

**Parsing steps:**

1. Expect `CREATE` (case-insensitive). Raise `ValueError` if absent.
2. If next token is `TEMP` or `TEMPORARY`, raise `ValueError` (not supported).
3. Expect `TABLE`.
4. If next three tokens are `IF`, `NOT`, `EXISTS` (case-insensitive), consume and skip all three.
5. Read table name (original case). If the token after it is `.`, raise `ValueError` (schema prefix not supported).
6. Expect `(`.
7. For each column:
   a. Read column name (original case).
   b. Read type token, uppercase for matching against `ColumnType`. Raise `ValueError` if unknown.
   c. If next token is `(`, consume and discard all tokens up to and including the matching `)`. "Matching" means tracking paren depth: increment depth on `(`, decrement on `)`; stop when depth returns to zero. The `,` tokens inside the length specifier (e.g. `NUMERIC(10,2)`) are consumed here and do not terminate the column.
   d. Collect remaining tokens until `,` or `)` (the column or column-list delimiter) as constraint tokens. If `(` is encountered in the constraint section, raise `ValueError`. Note: `DEFAULT (expr)` and `CHECK (expr)` both contain `(` and will therefore raise — they are not silently ignored (see Limitations).
   e. Scan constraint tokens for the consecutive sequence `NOT`, `NULL` (case-insensitive): set `nullable=False`.
   f. Scan constraint tokens for the consecutive sequence `PRIMARY`, `KEY` (case-insensitive): set `primary_key=True`.
   g. All other constraint tokens silently ignored (covers `AUTOINCREMENT`, `ASC`, `DESC`, `ON CONFLICT ...`, `UNIQUE`, bare `DEFAULT value`, `REFERENCES`, etc.).
   h. After setting `primary_key` and `type`: if `primary_key=True AND type == ColumnType.INTEGER`, set `nullable=False`.
   i. When a `,` is consumed as the column delimiter (in step 7d), if the immediately following token is `)`, raise `ValueError` — a trailing comma before the closing paren (e.g. `(id INTEGER,)`) is a syntax error in SQLite.
8. After the column list's closing `)`, scan any remaining tokens. If `WITHOUT` is found (case-insensitive) among these post-paren tokens, raise `ValueError` (`WITHOUT ROWID` changes PRIMARY KEY nullability semantics and is not supported).
9. Raise `ValueError` if column list is empty.

Test cases:
- Single column, basic type
- Multiple columns
- `NOT NULL` sets `nullable=False`
- `INTEGER PRIMARY KEY` sets `primary_key=True, nullable=False`
- `TEXT PRIMARY KEY` sets `primary_key=True, nullable=True` (SQLite allows NULL)
- `TEXT PRIMARY KEY NOT NULL` sets `primary_key=True, nullable=False`
- Both `NOT NULL` and `PRIMARY KEY` on same column (in either order)
- All five `ColumnType` values parse correctly
- `IF NOT EXISTS` — parses identically to without it
- `if not exists` (lowercase) — handled identically
- `create TABLE foo (id integer not null)` (fully lowercase keywords) — parsed correctly; column name `foo` and `id` preserve case
- Type with length specifier `TEXT(100)` — length discarded, type is TEXT
- Type with two-param specifier `NUMERIC(10,2)` — discarded, type is NUMERIC
- Type with length specifier followed by constraint `NUMERIC(10,2) NOT NULL` — length discarded, nullable=False
- `AUTOINCREMENT` after `INTEGER PRIMARY KEY` — silently ignored
- Column names preserve original case (`userId` stored as `userId`, not `USERID`)
- Two columns with `PRIMARY KEY` → `ValueError` (from Table validator at model construction)
- Unknown type raises `ValueError`
- `TEMP TABLE` raises `ValueError`
- `WITHOUT ROWID` raises `ValueError`
- Schema prefix `main.users` raises `ValueError`
- Quoted identifier `"` raises `ValueError`
- Missing `CREATE TABLE` raises `ValueError`
- Empty column list raises `ValueError`
- Trailing comma `(id INTEGER,)` raises `ValueError`
- `DEFAULT (42)` raises `ValueError` (parenthesized DEFAULT not supported)

---

## Dependencies

```yaml
stdlib: [enum]
third_party: [pydantic]
internal: []
```

No external dependencies beyond Pydantic.

---

## Known Limitations (v1)

| Limitation | Behavior |
|---|---|
| Exact type name matching only | `VARCHAR`, `DATETIME`, `BOOLEAN`, etc. raise `ValueError` |
| No quoted identifiers | `'`, `"`, `` ` ``, `[` raise `ValueError` |
| No schema prefix | `main.users` raises `ValueError` |
| No table-level constraints | Composite `PRIMARY KEY (a, b)` not parsed |
| `UNIQUE` silently dropped | No `unique` field on `Column`; constraint ignored |
| `DEFAULT value` (bare) silently dropped | Default values not represented |
| `DEFAULT (expr)` raises `ValueError` | Parenthesized DEFAULT triggers the `(` guard in step 7d |
| `CHECK (expr)` raises `ValueError` | Parenthesized CHECK triggers the `(` guard in step 7d |
| `FOREIGN KEY` silently dropped | — |
| `TEMP` / `TEMPORARY` raises | Not supported |
| `WITHOUT ROWID` raises | Changes nullable semantics; not supported |
| `AUTOINCREMENT` silently dropped | Not represented; changes rowid insertion behavior. Silently ignored regardless of whether it follows `INTEGER PRIMARY KEY` or not. |

---

## Specforge Method Notes

This module will be the first real test of the specforge build/extract cycle:

1. Write the YAML spec from this design doc
2. Run `specforge build` to generate `parser.py`
3. Run `specforge verify` to check all test cases pass
4. If tests fail, retry loop kicks in
5. Run `specforge extract` on the generated code to verify round-trip fidelity

The module is intentionally sized to fit cleanly in specforge's per-function spec format: two functions with well-defined signatures, clear test cases, and no external I/O. Success here validates the method before tackling multi-module storage and query execution.
