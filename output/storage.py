from __future__ import annotations

from typing import Any

from sqlforge.parser import Column, ColumnType, Table


def coerce(value: Any, affinity: ColumnType) -> Any:
    """Apply SQLite type affinity coercion to a single value.

    None passes through unchanged (nullable checks happen elsewhere).
    """
    if value is None:
        return None

    if affinity == ColumnType.INTEGER:
        # bytes pass through unchanged
        if isinstance(value, bytes):
            return value
        # bool is a subclass of int in Python — treat as int
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if value == int(value):
                return int(value)
            return value
        if isinstance(value, str):
            # Try int parse first
            try:
                return int(value)
            except ValueError:
                pass
            # Try float parse, then promote to int if whole
            try:
                f = float(value)
                if f == int(f):
                    return int(f)
                return f
            except ValueError:
                pass
            return value
        return value

    if affinity == ColumnType.TEXT:
        # bytes pass through unchanged
        if isinstance(value, bytes):
            return value
        return str(value)

    if affinity == ColumnType.REAL:
        # bytes pass through unchanged
        if isinstance(value, bytes):
            return value
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return value
        return value

    if affinity == ColumnType.NUMERIC:
        # bytes pass through unchanged
        if isinstance(value, bytes):
            return value
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if value == int(value):
                return int(value)
            return value
        if isinstance(value, str):
            # Try int parse first
            try:
                return int(value)
            except ValueError:
                pass
            # Try float parse
            try:
                f = float(value)
                if f == int(f):
                    return int(f)
                return f
            except ValueError:
                pass
            return value
        return value

    if affinity == ColumnType.BLOB:
        # BLOB affinity: no conversion, pass through as-is
        return value

    return value


def _is_integer_primary_key(col: Column) -> bool:
    """Return True if the column is an INTEGER PRIMARY KEY (rowid alias)."""
    return col.primary_key and col.type == ColumnType.INTEGER


class Database:
    """In-memory SQLite-like storage engine."""

    def __init__(self: Any) -> None:
        # _tables: maps canonical name (as provided) -> Table, keyed by lower-case
        self._tables: dict[str, Table] = {}  # lower-case key -> Table
        # _rows: lower-case table name -> list of row dicts (canonical column names)
        self._rows: dict[str, list[dict[str, Any]]] = {}
        # _next_rowid: lower-case table name -> next auto-assign rowid counter
        self._next_rowid: dict[str, int] = {}

    def create_table(self: Any, table: Table) -> None:
        """Register a table schema. Raises ValueError on duplicate name (case-insensitive)."""
        key = table.name.lower()
        if key in self._tables:
            raise ValueError(f"table {table.name!r} already exists")
        self._tables[key] = table
        self._rows[key] = []
        self._next_rowid[key] = 1

    def drop_table(self: Any, name: str) -> None:
        """Remove a table and all its rows. Raises ValueError if not found."""
        key = name.lower()
        if key not in self._tables:
            raise ValueError(f"table {name!r} not found")
        del self._tables[key]
        del self._rows[key]
        del self._next_rowid[key]

    def table_exists(self: Any, name: str) -> bool:
        """Return True if a table with the given name exists (case-insensitive)."""
        return name.lower() in self._tables

    def insert(self: Any, table_name: str, values: dict[str, Any]) -> int:
        """Insert a row and return the rowid. Validates constraints and applies coercion."""
        key = table_name.lower()
        if key not in self._tables:
            raise ValueError(f"table {table_name!r} not found")

        table = self._tables[key]

        # Build a map: lower-case column name -> Column (canonical)
        col_map: dict[str, Column] = {col.name.lower(): col for col in table.columns}

        # Validate all provided column names (case-insensitive)
        for col_name in values:
            if col_name.lower() not in col_map:
                raise ValueError(f"unknown column {col_name!r} in table {table_name!r}")

        # Build a normalized values dict: canonical column name -> value
        # Start with lower-case key lookup from provided values
        provided: dict[str, Any] = {k.lower(): v for k, v in values.items()}

        # Find INTEGER PRIMARY KEY column if present
        ipk_col: Column | None = None
        for col in table.columns:
            if _is_integer_primary_key(col):
                ipk_col = col
                break

        # Determine rowid
        if ipk_col is not None:
            ipk_key = ipk_col.name.lower()
            ipk_value = provided.get(ipk_key)  # None if omitted or explicitly None

            if ipk_value is None:
                # Auto-assign: use next available rowid (max of existing + 1)
                rowid = self._next_rowid[key]
                # Ensure it doesn't collide with any existing explicit value
                existing_ids = {
                    row[ipk_col.name] for row in self._rows[key] if row[ipk_col.name] is not None
                }
                while rowid in existing_ids:
                    rowid += 1
                provided[ipk_key] = rowid
            else:
                rowid = int(ipk_value)
                provided[ipk_key] = rowid
                # Check for duplicate IPK
                existing_ids = {
                    row[ipk_col.name] for row in self._rows[key] if row[ipk_col.name] is not None
                }
                if rowid in existing_ids:
                    raise ValueError(f"UNIQUE constraint failed: {table_name}.{ipk_col.name}")

            # Update next_rowid counter to be max(existing) + 1
            all_ids = {
                row[ipk_col.name] for row in self._rows[key] if row[ipk_col.name] is not None
            }
            all_ids.add(rowid)
            self._next_rowid[key] = max(all_ids) + 1
        else:
            # No IPK: rowid is just sequential insertion count
            rowid = self._next_rowid[key]
            self._next_rowid[key] += 1

        # Build the complete row with canonical names, applying coercion and checking constraints
        row: dict[str, Any] = {}
        for col in table.columns:
            col_key = col.name.lower()
            raw_value = provided.get(col_key)

            # Apply coercion (None passes through coerce unchanged)
            coerced_value = coerce(raw_value, col.type)

            # Nullable constraint check
            if coerced_value is None and not col.nullable:
                # IPK is implicitly NOT NULL but auto-assigned above, so it won't be None here
                raise ValueError(f"NOT NULL constraint failed: {table_name}.{col.name}")

            # Non-IPK primary key uniqueness check (NULL values allowed as duplicates)
            if col.primary_key and not _is_integer_primary_key(col) and coerced_value is not None:
                existing_pk_values = {
                    existing_row[col.name]
                    for existing_row in self._rows[key]
                    if existing_row[col.name] is not None
                }
                if coerced_value in existing_pk_values:
                    raise ValueError(f"UNIQUE constraint failed: {table_name}.{col.name}")

            row[col.name] = coerced_value

        self._rows[key].append(row)
        return rowid

    def select_all(self: Any, table_name: str) -> list[dict[str, Any]]:
        """Return all rows in insertion order. Raises ValueError if table not found."""
        key = table_name.lower()
        if key not in self._tables:
            raise ValueError(f"table {table_name!r} not found")
        # Return copies to prevent mutation of internal state
        return [dict(row) for row in self._rows[key]]
