"""In-memory storage engine for sqlforge.

Provides type coercion (SQLite affinity rules) and row storage with
constraint enforcement on top of Table schemas from the parser module.
"""

from __future__ import annotations

from typing import Any

from .parser import ColumnType, Table


def coerce(value: Any, affinity: ColumnType) -> Any:
    """Apply SQLite type affinity coercion to a single value.

    None passes through unchanged (nullable checks happen elsewhere).
    """
    if value is None:
        return None

    if affinity == ColumnType.INTEGER:
        return _coerce_integer(value)

    if affinity == ColumnType.TEXT:
        if isinstance(value, int | float | bool):
            return str(value)
        return value

    if affinity == ColumnType.REAL:
        if isinstance(value, int) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, float):
            return value
        if isinstance(value, str):
            try:
                return float(value)
            except (ValueError, OverflowError):
                return value
        return value

    if affinity == ColumnType.NUMERIC:
        as_int = _coerce_integer(value)
        if type(as_int) is int:
            return as_int
        # INTEGER rules didn't produce int — try float
        if isinstance(value, str):
            try:
                return float(value)
            except (ValueError, OverflowError):
                return value
        if isinstance(value, float):
            return value
        return value

    # BLOB — no coercion
    return value


def _coerce_integer(value: Any) -> Any:
    """Try to coerce value to int under INTEGER affinity rules."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            pass
        try:
            f = float(value)
            if f.is_integer():
                return int(f)
        except (ValueError, OverflowError):
            pass
        return value
    return value


class Database:
    """In-memory SQLite-like storage engine."""

    def __init__(self) -> None:
        self._tables: dict[str, Table] = {}
        self._rows: dict[str, list[dict[str, Any]]] = {}
        self._rowid_seq: dict[str, int] = {}

    def create_table(self, table: Table) -> None:
        """Register a table schema. Raises ValueError on duplicate name (case-insensitive)."""
        key = table.name.lower()
        if key in self._tables:
            raise ValueError(f"table {table.name!r} already exists")
        self._tables[key] = table
        self._rows[key] = []
        self._rowid_seq[key] = 1

    def drop_table(self, name: str) -> None:
        """Remove a table and all its rows. Raises ValueError if not found."""
        key = name.lower()
        if key not in self._tables:
            raise ValueError(f"no such table: {name!r}")
        del self._tables[key]
        del self._rows[key]
        del self._rowid_seq[key]

    def table_exists(self, name: str) -> bool:
        """Return True if a table with the given name exists (case-insensitive)."""
        return name.lower() in self._tables

    def get_column_names(self, table_name: str) -> list[str]:
        """Return column names in schema order. Raises ValueError if table not found."""
        key = table_name.lower()
        if key not in self._tables:
            raise ValueError(f"no such table: {table_name!r}")
        return [col.name for col in self._tables[key].columns]

    def insert(self, table_name: str, values: dict[str, Any]) -> int:
        """Insert a row and return the rowid. Validates constraints and applies coercion."""
        key = table_name.lower()
        if key not in self._tables:
            raise ValueError(f"no such table: {table_name!r}")

        table = self._tables[key]
        rows = self._rows[key]

        # Build case-insensitive lookup for the values dict
        values_lower = {k.lower(): v for k, v in values.items()}

        # Reject unknown column names
        schema_names = {c.name.lower() for c in table.columns}
        for col_key in values_lower:
            if col_key not in schema_names:
                raise ValueError(f"unknown column: {col_key!r}")

        # Find the INTEGER PRIMARY KEY column (if any)
        ipk_col = None
        for col in table.columns:
            if col.primary_key and col.type == ColumnType.INTEGER:
                ipk_col = col
                break

        # Build the row
        row: dict[str, Any] = {}
        rowid = self._rowid_seq[key]

        for col in table.columns:
            raw = values_lower.get(col.name.lower())

            if col is ipk_col:
                if raw is None:
                    # Auto-assign rowid
                    row[col.name] = rowid
                else:
                    coerced = coerce(raw, ColumnType.INTEGER)
                    if type(coerced) is not int:
                        raise ValueError(
                            f"INTEGER PRIMARY KEY column {col.name!r} requires an integer value"
                        )
                    # Check uniqueness
                    for existing in rows:
                        if existing[col.name] == coerced:
                            raise ValueError(
                                f"duplicate value for PRIMARY KEY column {col.name!r}: {coerced!r}"
                            )
                    row[col.name] = coerced
                    rowid = coerced
            else:
                coerced = coerce(raw, col.type) if raw is not None else None
                # Nullable check
                if coerced is None and not col.nullable:
                    raise ValueError(f"column {col.name!r} is NOT NULL but got NULL")
                # Primary key uniqueness (non-INTEGER PK)
                if col.primary_key and coerced is not None:
                    for existing in rows:
                        if existing[col.name] == coerced:
                            raise ValueError(
                                f"duplicate value for PRIMARY KEY column {col.name!r}: {coerced!r}"
                            )
                row[col.name] = coerced

        rows.append(row)

        # Update rowid sequence
        if ipk_col is not None:
            actual_rowid = row[ipk_col.name]
            self._rowid_seq[key] = max(self._rowid_seq[key], actual_rowid + 1)
        else:
            self._rowid_seq[key] = rowid + 1

        return row[ipk_col.name] if ipk_col is not None else rowid

    def select_all(self, table_name: str) -> list[dict[str, Any]]:
        """Return all rows in insertion order. Raises ValueError if table not found."""
        key = table_name.lower()
        if key not in self._tables:
            raise ValueError(f"no such table: {table_name!r}")
        return [dict(row) for row in self._rows[key]]
