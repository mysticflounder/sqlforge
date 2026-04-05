import pytest
from sqlforge.insert import InsertStatement, Value, execute_insert, parse_insert
from sqlforge.parser import Column, ColumnType, Table
from sqlforge.storage import Database


# --- parse_insert ---


def test_parse_with_columns():
    stmt = parse_insert("INSERT INTO t (a) VALUES (1)")
    assert stmt.table_name == "t"
    assert stmt.columns == ["a"]
    assert stmt.values == [Value(raw=1)]


def test_parse_without_columns():
    stmt = parse_insert("INSERT INTO t VALUES (1, 'hello')")
    assert stmt.columns is None
    assert stmt.values == [Value(raw=1), Value(raw="hello")]


def test_parse_multiple_columns():
    stmt = parse_insert("INSERT INTO t (a, b) VALUES (1, 2)")
    assert stmt.columns == ["a", "b"]
    assert len(stmt.values) == 2


def test_parse_float_value():
    stmt = parse_insert("INSERT INTO t (a) VALUES (3.14)")
    assert stmt.values[0].raw == 3.14
    assert type(stmt.values[0].raw) is float


def test_parse_null_value():
    stmt = parse_insert("INSERT INTO t (a) VALUES (NULL)")
    assert stmt.values[0].raw is None


def test_parse_case_insensitive_keywords():
    stmt = parse_insert("insert into t values (1)")
    assert stmt.table_name == "t"
    assert stmt.values == [Value(raw=1)]


def test_parse_trailing_semicolon():
    stmt = parse_insert("INSERT INTO t (a) VALUES (1);")
    assert stmt.table_name == "t"


def test_parse_escaped_string():
    stmt = parse_insert("INSERT INTO t (a) VALUES ('it''s')")
    assert stmt.values[0].raw == "it's"


def test_parse_preserves_table_name_case():
    stmt = parse_insert("INSERT INTO MyTable (a) VALUES (1)")
    assert stmt.table_name == "MyTable"


def test_parse_preserves_column_name_case():
    stmt = parse_insert("INSERT INTO t (MyCol) VALUES (1)")
    assert stmt.columns == ["MyCol"]


def test_parse_missing_insert_raises():
    with pytest.raises(ValueError):
        parse_insert("SELECT * FROM t")


def test_parse_missing_into_raises():
    with pytest.raises(ValueError):
        parse_insert("INSERT t VALUES (1)")


def test_parse_missing_values_raises():
    with pytest.raises(ValueError):
        parse_insert("INSERT INTO t (a) (1)")


def test_parse_missing_table_name_raises():
    with pytest.raises(ValueError):
        parse_insert("INSERT INTO VALUES (1)")


def test_parse_empty_column_list_raises():
    with pytest.raises(ValueError):
        parse_insert("INSERT INTO t () VALUES (1)")


def test_parse_empty_value_list_raises():
    with pytest.raises(ValueError):
        parse_insert("INSERT INTO t (a) VALUES ()")


def test_parse_trailing_tokens_raises():
    with pytest.raises(ValueError):
        parse_insert("INSERT INTO t (a) VALUES (1) extra")


def test_parse_null_case_insensitive():
    stmt = parse_insert("INSERT INTO t (a) VALUES (null)")
    assert stmt.values[0].raw is None


# --- execute_insert ---


def _make_db() -> Database:
    db = Database()
    db.create_table(
        Table(
            name="users",
            columns=[
                Column(name="id", type=ColumnType.INTEGER, primary_key=True, nullable=False),
                Column(name="name", type=ColumnType.TEXT),
                Column(name="score", type=ColumnType.REAL),
            ],
        )
    )
    return db


def test_execute_with_columns():
    db = _make_db()
    stmt = parse_insert("INSERT INTO users (name, score) VALUES ('Alice', 9.5)")
    rowid = execute_insert(stmt, db)
    assert rowid == 1
    rows = db.select_all("users")
    assert rows[0]["name"] == "Alice"
    assert rows[0]["score"] == 9.5


def test_execute_without_columns():
    db = _make_db()
    stmt = parse_insert("INSERT INTO users VALUES (1, 'Bob', 8.0)")
    rowid = execute_insert(stmt, db)
    assert rowid == 1
    rows = db.select_all("users")
    assert rows[0]["id"] == 1
    assert rows[0]["name"] == "Bob"


def test_execute_column_count_mismatch_raises():
    db = _make_db()
    stmt = parse_insert("INSERT INTO users (name) VALUES (1, 2)")
    with pytest.raises(ValueError):
        execute_insert(stmt, db)


def test_execute_positional_count_mismatch_raises():
    db = _make_db()
    stmt = parse_insert("INSERT INTO users VALUES (1, 'Bob')")
    with pytest.raises(ValueError):
        execute_insert(stmt, db)


def test_execute_nonexistent_table_raises():
    db = _make_db()
    stmt = parse_insert("INSERT INTO nope (a) VALUES (1)")
    with pytest.raises(ValueError):
        execute_insert(stmt, db)


def test_execute_null_non_nullable_raises():
    db = _make_db()
    stmt = parse_insert("INSERT INTO users (id, name) VALUES (NULL, 'Alice')")
    # id is NOT NULL (but INTEGER PRIMARY KEY, so NULL auto-assigns)
    # Actually id is IPK so NULL auto-assigns — use a non-nullable non-IPK table
    db.create_table(
        Table(
            name="strict",
            columns=[Column(name="val", type=ColumnType.TEXT, nullable=False)],
        )
    )
    stmt = parse_insert("INSERT INTO strict (val) VALUES (NULL)")
    with pytest.raises(ValueError):
        execute_insert(stmt, db)


def test_execute_type_coercion():
    db = _make_db()
    stmt = parse_insert("INSERT INTO users (name) VALUES (42)")
    execute_insert(stmt, db)
    rows = db.select_all("users")
    assert rows[0]["name"] == "42"  # int coerced to str for TEXT column


def test_execute_multiple_inserts_sequential_rowids():
    db = _make_db()
    stmt1 = parse_insert("INSERT INTO users (name) VALUES ('Alice')")
    stmt2 = parse_insert("INSERT INTO users (name) VALUES ('Bob')")
    assert execute_insert(stmt1, db) == 1
    assert execute_insert(stmt2, db) == 2


def test_execute_ipk_auto_assignment():
    db = _make_db()
    stmt = parse_insert("INSERT INTO users (name) VALUES ('Alice')")
    rowid = execute_insert(stmt, db)
    assert rowid == 1
    rows = db.select_all("users")
    assert rows[0]["id"] == 1


# --- data model tests ---


def test_value_int():
    v = Value(raw=42)
    assert v.raw == 42


def test_value_none():
    v = Value(raw=None)
    assert v.raw is None


def test_insert_statement_defaults():
    stmt = InsertStatement(table_name="t", values=[Value(raw=1)])
    assert stmt.columns is None
