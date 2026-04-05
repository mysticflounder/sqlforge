import pytest
from sqlforge.parser import Column, ColumnType, Table
from sqlforge.storage import Database, coerce

# --- coerce: None passthrough ---


def test_coerce_none_integer():
    assert coerce(None, ColumnType.INTEGER) is None


def test_coerce_none_text():
    assert coerce(None, ColumnType.TEXT) is None


# --- coerce: INTEGER affinity ---


def test_coerce_int_to_integer():
    assert coerce(42, ColumnType.INTEGER) == 42
    assert type(coerce(42, ColumnType.INTEGER)) is int


def test_coerce_float_whole_to_integer():
    assert coerce(3.0, ColumnType.INTEGER) == 3
    assert type(coerce(3.0, ColumnType.INTEGER)) is int


def test_coerce_float_fractional_to_integer():
    result = coerce(3.5, ColumnType.INTEGER)
    assert result == 3.5
    assert type(result) is float


def test_coerce_str_int_to_integer():
    assert coerce("42", ColumnType.INTEGER) == 42
    assert type(coerce("42", ColumnType.INTEGER)) is int


def test_coerce_str_float_whole_to_integer():
    assert coerce("3.0", ColumnType.INTEGER) == 3
    assert type(coerce("3.0", ColumnType.INTEGER)) is int


def test_coerce_str_nonnum_to_integer():
    assert coerce("hello", ColumnType.INTEGER) == "hello"


def test_coerce_bytes_to_integer():
    assert coerce(b"\x00", ColumnType.INTEGER) == b"\x00"


# --- coerce: TEXT affinity ---


def test_coerce_int_to_text():
    assert coerce(42, ColumnType.TEXT) == "42"


def test_coerce_float_to_text():
    assert coerce(3.14, ColumnType.TEXT) == "3.14"


def test_coerce_str_to_text():
    assert coerce("hello", ColumnType.TEXT) == "hello"


def test_coerce_bool_to_text():
    assert coerce(True, ColumnType.TEXT) == "True"


def test_coerce_bytes_to_text():
    assert coerce(b"\x00", ColumnType.TEXT) == b"\x00"


# --- coerce: REAL affinity ---


def test_coerce_int_to_real():
    result = coerce(42, ColumnType.REAL)
    assert result == 42.0
    assert type(result) is float


def test_coerce_float_to_real():
    assert coerce(3.14, ColumnType.REAL) == 3.14


def test_coerce_str_float_to_real():
    assert coerce("3.14", ColumnType.REAL) == 3.14


def test_coerce_str_nonnum_to_real():
    assert coerce("hello", ColumnType.REAL) == "hello"


# --- coerce: NUMERIC affinity ---


def test_coerce_int_to_numeric():
    assert coerce(42, ColumnType.NUMERIC) == 42
    assert type(coerce(42, ColumnType.NUMERIC)) is int


def test_coerce_float_whole_to_numeric():
    assert coerce(3.0, ColumnType.NUMERIC) == 3
    assert type(coerce(3.0, ColumnType.NUMERIC)) is int


def test_coerce_float_fractional_to_numeric():
    result = coerce(3.5, ColumnType.NUMERIC)
    assert result == 3.5
    assert type(result) is float


def test_coerce_str_int_to_numeric():
    assert coerce("42", ColumnType.NUMERIC) == 42
    assert type(coerce("42", ColumnType.NUMERIC)) is int


def test_coerce_str_float_to_numeric():
    result = coerce("3.14", ColumnType.NUMERIC)
    assert result == 3.14
    assert type(result) is float


def test_coerce_str_nonnum_to_numeric():
    assert coerce("hello", ColumnType.NUMERIC) == "hello"


# --- coerce: BLOB affinity ---


def test_coerce_int_to_blob():
    assert coerce(42, ColumnType.BLOB) == 42


def test_coerce_str_to_blob():
    assert coerce("hello", ColumnType.BLOB) == "hello"


def test_coerce_bytes_to_blob():
    assert coerce(b"\xff", ColumnType.BLOB) == b"\xff"


# --- Database.create_table ---


def _make_table(name: str = "t", columns: list[Column] | None = None) -> Table:
    if columns is None:
        columns = [Column(name="id", type=ColumnType.INTEGER)]
    return Table(name=name, columns=columns)


def test_create_table_exists():
    db = Database()
    db.create_table(_make_table("users"))
    assert db.table_exists("users") is True


def test_create_two_tables():
    db = Database()
    db.create_table(_make_table("a"))
    db.create_table(_make_table("b"))
    assert db.table_exists("a") is True
    assert db.table_exists("b") is True


def test_create_duplicate_raises():
    db = Database()
    db.create_table(_make_table("users"))
    with pytest.raises(ValueError):
        db.create_table(_make_table("users"))


def test_create_duplicate_case_insensitive_raises():
    db = Database()
    db.create_table(_make_table("Users"))
    with pytest.raises(ValueError):
        db.create_table(_make_table("users"))


# --- Database.drop_table ---


def test_drop_table():
    db = Database()
    db.create_table(_make_table("t"))
    db.drop_table("t")
    assert db.table_exists("t") is False


def test_drop_nonexistent_raises():
    db = Database()
    with pytest.raises(ValueError):
        db.drop_table("nope")


def test_drop_then_recreate():
    db = Database()
    db.create_table(_make_table("t"))
    db.drop_table("t")
    db.create_table(_make_table("t"))
    assert db.table_exists("t") is True


# --- Database.table_exists ---


def test_table_exists_false():
    db = Database()
    assert db.table_exists("nope") is False


def test_table_exists_case_insensitive():
    db = Database()
    db.create_table(_make_table("Users"))
    assert db.table_exists("users") is True
    assert db.table_exists("USERS") is True


# --- Database.get_column_names ---


def test_get_column_names():
    db = Database()
    db.create_table(_users_table())
    assert db.get_column_names("users") == ["id", "name", "score"]


def test_get_column_names_case_insensitive():
    db = Database()
    db.create_table(_users_table())
    assert db.get_column_names("USERS") == ["id", "name", "score"]


def test_get_column_names_nonexistent_raises():
    db = Database()
    with pytest.raises(ValueError):
        db.get_column_names("nope")


# --- Database.insert ---


def _users_table() -> Table:
    return Table(
        name="users",
        columns=[
            Column(name="id", type=ColumnType.INTEGER, primary_key=True, nullable=False),
            Column(name="name", type=ColumnType.TEXT),
            Column(name="score", type=ColumnType.REAL),
        ],
    )


def _simple_table() -> Table:
    """Table without INTEGER PRIMARY KEY — just nullable columns."""
    return Table(
        name="items",
        columns=[
            Column(name="label", type=ColumnType.TEXT),
            Column(name="count", type=ColumnType.INTEGER),
        ],
    )


def test_insert_nonexistent_table_raises():
    db = Database()
    with pytest.raises(ValueError):
        db.insert("nope", {"x": 1})


def test_insert_unknown_column_raises():
    db = Database()
    db.create_table(_simple_table())
    with pytest.raises(ValueError):
        db.insert("items", {"label": "a", "nonexistent": 1})


def test_insert_returns_rowid_sequential():
    db = Database()
    db.create_table(_simple_table())
    assert db.insert("items", {"label": "a"}) == 1
    assert db.insert("items", {"label": "b"}) == 2


def test_insert_all_columns():
    db = Database()
    db.create_table(_simple_table())
    db.insert("items", {"label": "widget", "count": 5})
    rows = db.select_all("items")
    assert rows == [{"label": "widget", "count": 5}]


def test_insert_nullable_column_omitted():
    db = Database()
    db.create_table(_simple_table())
    db.insert("items", {"label": "a"})
    rows = db.select_all("items")
    assert rows[0]["count"] is None


def test_insert_non_nullable_omitted_raises():
    table = Table(
        name="t",
        columns=[
            Column(name="val", type=ColumnType.TEXT, nullable=False),
        ],
    )
    db = Database()
    db.create_table(table)
    with pytest.raises(ValueError):
        db.insert("t", {})  # val is NOT NULL, not provided


def test_insert_ipk_auto_assigns():
    db = Database()
    db.create_table(_users_table())
    rowid = db.insert("users", {"name": "Alice"})
    assert rowid == 1
    rows = db.select_all("users")
    assert rows[0]["id"] == 1


def test_insert_ipk_explicit_value():
    db = Database()
    db.create_table(_users_table())
    rowid = db.insert("users", {"id": 10, "name": "Alice"})
    assert rowid == 10
    rows = db.select_all("users")
    assert rows[0]["id"] == 10


def test_insert_ipk_duplicate_raises():
    db = Database()
    db.create_table(_users_table())
    db.insert("users", {"id": 1, "name": "Alice"})
    with pytest.raises(ValueError):
        db.insert("users", {"id": 1, "name": "Bob"})


def test_insert_ipk_none_auto_assigns():
    db = Database()
    db.create_table(_users_table())
    rowid = db.insert("users", {"id": None, "name": "Alice"})
    assert rowid == 1


def test_insert_ipk_auto_after_explicit():
    db = Database()
    db.create_table(_users_table())
    db.insert("users", {"id": 5, "name": "Alice"})
    rowid = db.insert("users", {"name": "Bob"})
    assert rowid == 6


def test_insert_text_pk_duplicate_raises():
    table = Table(
        name="codes",
        columns=[
            Column(name="code", type=ColumnType.TEXT, primary_key=True),
        ],
    )
    db = Database()
    db.create_table(table)
    db.insert("codes", {"code": "A"})
    with pytest.raises(ValueError):
        db.insert("codes", {"code": "A"})


def test_insert_text_pk_null_allowed_multiple():
    table = Table(
        name="codes",
        columns=[
            Column(name="code", type=ColumnType.TEXT, primary_key=True),
        ],
    )
    db = Database()
    db.create_table(table)
    db.insert("codes", {"code": None})
    db.insert("codes", {"code": None})  # multiple NULLs allowed
    assert len(db.select_all("codes")) == 2


def test_insert_type_coercion_applied():
    db = Database()
    db.create_table(_simple_table())
    db.insert("items", {"label": 42, "count": "7"})
    rows = db.select_all("items")
    assert rows[0]["label"] == "42"  # int → str (TEXT affinity)
    assert rows[0]["count"] == 7  # str → int (INTEGER affinity)
    assert type(rows[0]["count"]) is int


def test_insert_column_name_case_insensitive():
    db = Database()
    table = Table(
        name="t",
        columns=[Column(name="Name", type=ColumnType.TEXT)],
    )
    db.create_table(table)
    db.insert("t", {"name": "Alice"})
    rows = db.select_all("t")
    assert rows[0]["Name"] == "Alice"  # canonical case from schema


# --- Database.select_all ---


def test_select_nonexistent_raises():
    db = Database()
    with pytest.raises(ValueError):
        db.select_all("nope")


def test_select_empty_table():
    db = Database()
    db.create_table(_simple_table())
    assert db.select_all("items") == []


def test_select_insertion_order():
    db = Database()
    db.create_table(_simple_table())
    db.insert("items", {"label": "c"})
    db.insert("items", {"label": "a"})
    db.insert("items", {"label": "b"})
    labels = [r["label"] for r in db.select_all("items")]
    assert labels == ["c", "a", "b"]


def test_select_returns_canonical_column_names():
    db = Database()
    table = Table(
        name="t",
        columns=[Column(name="MyCol", type=ColumnType.TEXT)],
    )
    db.create_table(table)
    db.insert("t", {"mycol": "v"})
    rows = db.select_all("t")
    assert "MyCol" in rows[0]


def test_select_returns_copies():
    db = Database()
    db.create_table(_simple_table())
    db.insert("items", {"label": "a"})
    rows = db.select_all("items")
    rows[0]["label"] = "MUTATED"
    assert db.select_all("items")[0]["label"] == "a"
