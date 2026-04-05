# sqlforge: In-Memory Storage Engine — Design Spec

**Date:** 2026-04-04
**Status:** Draft
**Project:** sqlforge (SQLite reference implementation built with specforge)
**Scope:** `storage` module — v2 slice (builds on `parser`)

---

## Overview

An in-memory storage engine for sqlforge. Takes `Table` schemas from the parser module and provides row storage with type coercion, constraint enforcement, and rowid management. This is the bridge between parsing (which produces structured schemas) and query execution (which will read/write data).

The module exposes one pure function (`coerce`) and one stateful class (`Database`). Together they implement enough SQLite storage semantics to serve as the foundation for INSERT/SELECT execution in later modules.

---

## Data Models

No new Pydantic models. The `Database` class uses plain dicts for row storage and imports `Table`, `Column`, and `ColumnType` from `parser`.

Internal state (not part of public API):

```python
class Database:
    _tables: dict[str, Table]       # lowercase name → schema
    _rows: dict[str, list[dict[str, Any]]]  # lowercase name → rows in insertion order
    _rowid_seq: dict[str, int]      # lowercase name → next auto-rowid
```

Rows are stored as `dict[str, Any]` where keys are the canonical column names (original case from schema). Values are the coerced Python values (or `None` for NULL).

---

## Functions

### `coerce(value: Any, affinity: ColumnType) -> Any`

Pure function. Applies SQLite type affinity coercion rules to a single value. Returns the coerced value. `None` input always returns `None` (NULL passes through unchanged — nullable checks happen elsewhere).

**Coercion rules by affinity:**

| Affinity | Rule |
|---|---|
| INTEGER | `int` → `int`. `float` with `.is_integer()` → `int`. `str` parseable as `int` → `int`. `str` parseable as `float` where `.is_integer()` → `int`. All others → stored as-is. |
| TEXT | `int`/`float`/`bool` → `str(value)`. `str` → `str`. `bytes` → stored as-is. |
| REAL | `int` → `float`. `float` → `float`. `str` parseable as `float` → `float`. All others → stored as-is. |
| NUMERIC | Try INTEGER rules first. If that doesn't coerce, try `float` (i.e., `str` parseable as `float` → `float`). All others → stored as-is. |
| BLOB | No coercion. All values stored as-is. |

"Stored as-is" means the original Python value is returned unchanged. This matches SQLite's manifest typing — any column can hold any type; affinity just expresses a *preference*.

"Parseable as int" means `int(value)` succeeds (no leading/trailing whitespace tolerance — the caller is responsible for trimming). "Parseable as float" means `float(value)` succeeds.

**Test cases:**

- `coerce(None, INTEGER)` → `None`
- `coerce(42, INTEGER)` → `42` (int)
- `coerce(3.0, INTEGER)` → `3` (int, fractional part is zero)
- `coerce(3.5, INTEGER)` → `3.5` (float, has fractional part — stored as-is)
- `coerce("42", INTEGER)` → `42` (int)
- `coerce("3.0", INTEGER)` → `3` (int, str→float→int)
- `coerce("hello", INTEGER)` → `"hello"` (str, not parseable — stored as-is)
- `coerce(b"\x00", INTEGER)` → `b"\x00"` (bytes — stored as-is)
- `coerce(42, TEXT)` → `"42"` (str)
- `coerce(3.14, TEXT)` → `"3.14"` (str)
- `coerce("hello", TEXT)` → `"hello"` (str)
- `coerce(True, TEXT)` → `"True"` (str)
- `coerce(b"\x00", TEXT)` → `b"\x00"` (bytes — stored as-is)
- `coerce(42, REAL)` → `42.0` (float)
- `coerce(3.14, REAL)` → `3.14` (float)
- `coerce("3.14", REAL)` → `3.14` (float)
- `coerce("hello", REAL)` → `"hello"` (str, not parseable — stored as-is)
- `coerce(42, NUMERIC)` → `42` (int — INTEGER rules applied first)
- `coerce(3.0, NUMERIC)` → `3` (int — float with zero fractional)
- `coerce(3.5, NUMERIC)` → `3.5` (float — INTEGER failed, REAL succeeded)
- `coerce("42", NUMERIC)` → `42` (int — str parseable as int)
- `coerce("3.14", NUMERIC)` → `3.14` (float — str parseable as float)
- `coerce("hello", NUMERIC)` → `"hello"` (stored as-is)
- `coerce(42, BLOB)` → `42` (no coercion)
- `coerce("hello", BLOB)` → `"hello"` (no coercion)
- `coerce(b"\xff", BLOB)` → `b"\xff"` (no coercion)

### `Database` class

#### `Database.__init__(self) -> None`

Initializes an empty database with no tables.

#### `Database.create_table(self, table: Table) -> None`

Registers a table schema. Table name lookup is **case-insensitive** (matching SQLite). Raises `ValueError` if a table with the same name (case-insensitive) already exists.

**Test cases:**

- Create a table, then `table_exists` returns True
- Create two tables with different names — both exist
- Create table with same name (exact case) → `ValueError`
- Create table with same name (different case, e.g., "Users" then "users") → `ValueError`

#### `Database.drop_table(self, name: str) -> None`

Removes a table and all its rows. Table name lookup is case-insensitive. Raises `ValueError` if the table does not exist.

**Test cases:**

- Create and drop a table — `table_exists` returns False
- Drop nonexistent table → `ValueError`
- Drop table, then create it again — succeeds (name freed)

#### `Database.table_exists(self, name: str) -> bool`

Returns `True` if a table with the given name (case-insensitive) is registered. Does not raise.

**Test cases:**

- Returns False for nonexistent table
- Returns True after `create_table`
- Case-insensitive: created as "Users", `table_exists("users")` returns True

#### `Database.insert(self, table_name: str, values: dict[str, Any]) -> int`

Inserts a row and returns the rowid. This is the most complex method.

**Table resolution:** Case-insensitive. Raises `ValueError` if table not found.

**Column name resolution:** Case-insensitive against schema column names. Raises `ValueError` if `values` contains a key that doesn't match any schema column. Unrecognized columns are rejected early, before any coercion or storage.

**Processing each schema column:**

1. Look up the value in `values` (case-insensitive key match). If the column is not present in `values`, the value is `None`.
2. **Rowid / INTEGER PRIMARY KEY handling:** If the column is `INTEGER PRIMARY KEY`:
   - If value is `None`: auto-assign the next rowid (current `_rowid_seq` value, then increment).
   - If value is not `None`: coerce via `coerce(value, INTEGER)`. After coercion, if the result is not an `int`, raise `ValueError`. Check uniqueness against existing rows — if duplicate, raise `ValueError`. The rowid becomes this value. Update `_rowid_seq` to `max(current_seq, value + 1)` so auto-assignment never collides.
3. **Coercion:** Apply `coerce(value, column.type)` for non-None values (None stays None).
4. **Nullable check:** If the coerced value is `None` and `column.nullable` is `False`, raise `ValueError`.
5. **Primary key uniqueness (non-INTEGER PRIMARY KEY):** If the column has `primary_key=True` and the type is not `INTEGER`, check that the coerced value is unique among existing rows for that column. `None` values are exempt from uniqueness (SQLite allows multiple NULLs in a unique column). Raise `ValueError` on duplicate.

**Return value:** The rowid. For tables with an INTEGER PRIMARY KEY column, this is the value of that column. For tables without, this is an internal auto-incrementing integer (starting at 1).

**Test cases:**

- Insert into nonexistent table → `ValueError`
- Insert with unknown column name → `ValueError`
- Insert single row, returns rowid 1
- Insert two rows, returns rowids 1, 2
- Insert with all columns specified
- Insert with nullable column omitted — stored as None
- Insert with non-nullable column omitted → `ValueError`
- INTEGER PRIMARY KEY auto-assigns rowid
- INTEGER PRIMARY KEY with explicit value — returns that value
- INTEGER PRIMARY KEY explicit duplicate → `ValueError`
- INTEGER PRIMARY KEY with None — auto-assigns
- INTEGER PRIMARY KEY auto-assign after explicit: insert(id=5), insert(id=None) → gets 6
- TEXT PRIMARY KEY duplicate → `ValueError`
- TEXT PRIMARY KEY with None (nullable TEXT PK) — allowed, multiple NULLs allowed
- Type coercion applied: insert int into TEXT column, select returns str
- Column name case-insensitive: schema has "Name", insert with "name" works
- Unknown column name "nonexistent" → `ValueError`

#### `Database.select_all(self, table_name: str) -> list[dict[str, Any]]`

Returns all rows for the table in insertion order. Each row is a dict mapping canonical column names (original case from schema) to values. Raises `ValueError` if the table does not exist.

Returns a new list with new dicts (not references to internal storage).

**Test cases:**

- Select from nonexistent table → `ValueError`
- Select from empty table → `[]`
- Select returns rows in insertion order
- Select returns canonical column names (schema case, not insert case)
- Returned dicts are copies — mutating them doesn't affect stored data

---

## Dependencies

```yaml
stdlib: []
third_party: []
internal: [parser]   # imports Table, Column, ColumnType
```

No new external dependencies. Only imports from the `parser` module.

---

## Known Limitations (v1)

| Limitation | Behavior |
|---|---|
| In-memory only | No persistence, no file I/O |
| No UPDATE | Rows cannot be modified after insertion |
| No DELETE | Rows cannot be removed (drop_table removes all) |
| No indexes | Primary key uniqueness checked via linear scan |
| No SELECT filtering | `select_all` returns all rows; WHERE is a query-layer concern |
| No rowid exposure for non-PK tables | Internal rowid not accessible without INTEGER PRIMARY KEY |
| No AUTOINCREMENT semantics | Rowid reuse after drop_table is possible (counter resets) |
| No multi-column primary keys | Only single column-level PRIMARY KEY (from parser constraint) |
| Column names in values case-insensitive | SQLite behavior, but some edge cases may differ |

---

## Specforge Method Notes

Second module in the extract→build cycle. Lessons from parser FINDINGS.md applied:

1. **Richer descriptions:** Function/method descriptions include behavioral bullet lists, not just one-line docstrings.
2. **Default values explicit:** All defaults documented in the design spec and should appear in extracted YAML.
3. **Tests encode behavior:** The test suite covers edge cases (auto-rowid, type coercion, case-insensitivity) that descriptions alone cannot capture.
4. **Error messages bare:** Tests use `pytest.raises(ValueError)` without `match=` — cleanroom can use any wording.
