# sqlforge: INSERT Statement — Design Spec

**Date:** 2026-04-04
**Status:** Draft
**Project:** sqlforge (SQLite reference implementation)
**Scope:** `insert` module — v4 slice (first integration of tokenizer + storage)

---

## Overview

Parses and executes `INSERT INTO ... VALUES (...)` statements. This is the first module that integrates two existing modules: the general tokenizer for lexing and the storage engine for row insertion. It produces a structured `InsertStatement` from SQL text, then executes it against a `Database`.

Separating parse from execute keeps the modules testable independently and prepares for a future `execute(sql, db)` dispatcher.

---

## Data Models

```python
class Value(BaseModel):
    """A literal value in a SQL statement."""
    
    raw: int | float | str | None
```

Wraps a Python literal. `None` represents SQL NULL. `int` and `float` come from NUMBER tokens. `str` comes from STRING tokens. The `raw` field holds the Python value directly.

```python
class InsertStatement(BaseModel):
    """A parsed INSERT INTO statement."""
    
    table_name: str
    columns: list[str] | None = None
    values: list[Value]
```

`columns` is `None` when the INSERT omits the column list (positional insert). When present, it lists column names in the order specified. `values` is the list of literal values in the VALUES clause, in order.

---

## Functions

### `parse_insert(sql: str) -> InsertStatement`

Parses an INSERT statement using `tokenize_sql` from the tokenizer module.

**Grammar (v1):**

```
INSERT INTO <table_name> [( <col1>, <col2>, ... )] VALUES ( <val1>, <val2>, ... )
```

**Parsing steps:**

1. Tokenize with `tokenize_sql(sql)`.
2. Expect `WORD:INSERT` (case-insensitive). Raise `ValueError` if absent.
3. Expect `WORD:INTO` (case-insensitive). Raise `ValueError` if absent.
4. Read table name: next WORD token. Raise `ValueError` if not a WORD.
5. If next token is `PUNCT:(`:
   a. This is a column list. Consume WORD tokens separated by `PUNCT:,` until `PUNCT:)`.
   b. Each column name is a WORD token (case preserved).
   c. Raise `ValueError` if empty column list.
6. Expect `WORD:VALUES` (case-insensitive). Raise `ValueError` if absent.
7. Expect `PUNCT:(`.
8. Parse values separated by `PUNCT:,` until `PUNCT:)`:
   - `NUMBER` token: parse with `int()` if no `.`, else `float()`.
   - `STRING` token: the string value (already unescaped by tokenizer).
   - `WORD:NULL` (case-insensitive): `None`.
   - Any other token: raise `ValueError`.
9. Raise `ValueError` if empty value list.
10. Raise `ValueError` if there are tokens remaining after the closing `)` (except optional `PUNCT:;`).

**Test cases:**

- `"INSERT INTO t (a) VALUES (1)"` → table_name="t", columns=["a"], values=[Value(raw=1)]
- `"INSERT INTO t VALUES (1, 'hello')"` → columns=None, values=[Value(raw=1), Value(raw="hello")]
- `"INSERT INTO t (a, b) VALUES (1, 2)"` → columns=["a", "b"], values two ints
- `"INSERT INTO t (a) VALUES (3.14)"` → values=[Value(raw=3.14)]
- `"INSERT INTO t (a) VALUES (NULL)"` → values=[Value(raw=None)]
- `"insert into t values (1)"` → case-insensitive keywords
- `"INSERT INTO t (a) VALUES (1);"` → trailing semicolon allowed
- `"INSERT INTO t (a) VALUES ('it''s')"` → string with escaped quote
- Missing INSERT → `ValueError`
- Missing INTO → `ValueError`
- Missing VALUES → `ValueError`
- Missing table name → `ValueError`
- Empty column list `()` → `ValueError`
- Empty value list `VALUES ()` → `ValueError`
- Trailing tokens after `)` → `ValueError`

### `execute_insert(statement: InsertStatement, db: Database) -> int`

Executes a parsed INSERT statement against a Database instance. Returns the rowid.

**Execution steps:**

1. Look up the table schema from `db` (via the storage engine's internal state). The table name lookup is handled by `db.insert()` which is case-insensitive.
2. Build a values dict:
   a. If `statement.columns` is not None: zip column names with values. Raise `ValueError` if the counts don't match.
   b. If `statement.columns` is None: map values positionally to the table's column list (from schema). Raise `ValueError` if the count doesn't match the number of schema columns.
3. Call `db.insert(table_name, values_dict)` and return the rowid.

For step 2b (positional insert), we need the table schema. Since `Database` doesn't expose a `get_table` method, we'll access it through `db.insert()` — but we need the column names to build the dict. We'll add a helper: retrieve column names from the database for positional mapping.

Actually, the cleaner approach: add a `get_columns(table_name: str) -> list[str]` method to Database in the storage module. But that changes another module. Instead, `execute_insert` can accept the column names as a parameter, or we can document that positional inserts require the caller to know the schema.

**Simplest approach for v1:** `execute_insert` takes `statement` and `db`. For positional inserts (no column list), it calls a new `Database.get_column_names(table_name) -> list[str]` method. This requires a small addition to the storage module.

**Test cases:**

- Insert with column list → row stored correctly
- Insert without column list (positional) → row stored correctly
- Column count mismatch (with column list) → `ValueError`
- Value count mismatch (positional) → `ValueError`
- Insert into nonexistent table → `ValueError` (from db.insert)
- NULL into non-nullable column → `ValueError` (from db.insert)
- Type coercion applied (int into TEXT column → "1")
- Multiple inserts → sequential rowids
- Integer primary key auto-assignment via insert

---

## Dependencies

```yaml
stdlib: []
third_party: [pydantic]
internal: [tokenizer, storage]
```

Imports `tokenize_sql`, `Token`, `TokenKind` from tokenizer. Imports `Database` from storage.

---

## Required Change to Storage Module

Add one method to `Database`:

```python
def get_column_names(self, table_name: str) -> list[str]:
    """Return column names for the table in schema order. Raises ValueError if not found."""
```

This is minimal and supports positional INSERT. The method returns the canonical column names from the `Table` schema.

---

## Known Limitations (v1)

| Limitation | Behavior |
|---|---|
| Single row only | No multi-row `INSERT INTO t VALUES (1), (2), (3)` |
| No subquery | No `INSERT INTO t SELECT ...` |
| No DEFAULT keyword | `DEFAULT` in value position raises `ValueError` |
| No expressions | `1 + 2` in value position raises `ValueError` |
| No REPLACE / ON CONFLICT | Not supported |
| No RETURNING clause | Not supported |

---

## Specforge Method Notes

Fourth module and first integration test. This module imports from two other sqlforge modules (tokenizer + storage), testing whether the extract→build cycle works when modules have internal dependencies. The cleanroom build will need the reference tokenizer.py and storage.py as dependency sources.
