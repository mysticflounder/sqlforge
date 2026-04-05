import pytest
from sqlforge.parser import (
    Column,
    ColumnType,
    Table,
    parse_create_table,
    tokenize,
)

# --- tokenize ---


def test_tokenize_basic():
    assert tokenize("CREATE TABLE foo (id INTEGER)") == [
        "CREATE",
        "TABLE",
        "foo",
        "(",
        "id",
        "INTEGER",
        ")",
    ]


def test_tokenize_punctuation_separate():
    result = tokenize("(a,b);")
    assert "(" in result and "," in result and ")" in result and ";" in result


def test_tokenize_whitespace_and_newlines():
    result = tokenize("CREATE  TABLE\n  foo\n(id  INTEGER)")
    assert "" not in result
    assert result == ["CREATE", "TABLE", "foo", "(", "id", "INTEGER", ")"]


def test_tokenize_period_separate():
    assert tokenize("main.users") == ["main", ".", "users"]


def test_tokenize_preserves_case():
    assert tokenize("Create Table Foo") == ["Create", "Table", "Foo"]


def test_tokenize_rejects_single_quote():
    with pytest.raises(ValueError):
        tokenize("CREATE TABLE foo (name TEXT DEFAULT 'bar')")


def test_tokenize_rejects_double_quote():
    with pytest.raises(ValueError):
        tokenize('CREATE TABLE "foo" (id INTEGER)')


def test_tokenize_rejects_backtick():
    with pytest.raises(ValueError):
        tokenize("CREATE TABLE `foo` (id INTEGER)")


def test_tokenize_rejects_bracket():
    with pytest.raises(ValueError):
        tokenize("CREATE TABLE [foo] (id INTEGER)")


# --- parse_create_table ---


def test_parse_single_column():
    t = parse_create_table("CREATE TABLE users (id INTEGER)")
    assert t.name == "users"
    assert len(t.columns) == 1
    assert t.columns[0].name == "id"
    assert t.columns[0].type == ColumnType.INTEGER
    assert t.columns[0].nullable is True
    assert t.columns[0].primary_key is False


def test_parse_multiple_columns_in_order():
    t = parse_create_table("CREATE TABLE t (id INTEGER, name TEXT, score REAL)")
    assert [c.name for c in t.columns] == ["id", "name", "score"]


def test_parse_not_null():
    t = parse_create_table("CREATE TABLE t (name TEXT NOT NULL)")
    assert t.columns[0].nullable is False


def test_parse_integer_primary_key_implies_not_null():
    t = parse_create_table("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    assert t.columns[0].primary_key is True
    assert t.columns[0].nullable is False


def test_parse_text_primary_key_nullable_true():
    t = parse_create_table("CREATE TABLE t (code TEXT PRIMARY KEY)")
    assert t.columns[0].primary_key is True
    assert t.columns[0].nullable is True


def test_parse_text_primary_key_not_null():
    t = parse_create_table("CREATE TABLE t (code TEXT PRIMARY KEY NOT NULL)")
    assert t.columns[0].primary_key is True
    assert t.columns[0].nullable is False


def test_parse_constraints_either_order():
    t = parse_create_table("CREATE TABLE t (id INTEGER PRIMARY KEY NOT NULL)")
    assert t.columns[0].primary_key is True
    assert t.columns[0].nullable is False


def test_parse_all_five_types():
    t = parse_create_table("CREATE TABLE t (a INTEGER, b TEXT, c REAL, d BLOB, e NUMERIC)")
    assert [c.type for c in t.columns] == [
        ColumnType.INTEGER,
        ColumnType.TEXT,
        ColumnType.REAL,
        ColumnType.BLOB,
        ColumnType.NUMERIC,
    ]


def test_parse_if_not_exists():
    t = parse_create_table("CREATE TABLE IF NOT EXISTS users (id INTEGER)")
    assert t.name == "users"


def test_parse_if_not_exists_lowercase():
    t = parse_create_table("create table if not exists users (id integer)")
    assert t.name == "users"
    assert t.columns[0].type == ColumnType.INTEGER


def test_parse_fully_lowercase_preserves_names():
    t = parse_create_table("create TABLE foo (userId integer not null)")
    assert t.name == "foo"
    assert t.columns[0].name == "userId"
    assert t.columns[0].nullable is False


def test_parse_length_specifier_discarded():
    t = parse_create_table("CREATE TABLE t (name TEXT(100))")
    assert t.columns[0].type == ColumnType.TEXT


def test_parse_two_param_specifier_discarded():
    t = parse_create_table("CREATE TABLE t (price NUMERIC(10,2))")
    assert t.columns[0].type == ColumnType.NUMERIC


def test_parse_length_specifier_with_constraint():
    t = parse_create_table("CREATE TABLE t (price NUMERIC(10,2) NOT NULL)")
    assert t.columns[0].type == ColumnType.NUMERIC
    assert t.columns[0].nullable is False


def test_parse_autoincrement_ignored():
    t = parse_create_table("CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT)")
    assert t.columns[0].primary_key is True
    assert t.columns[0].nullable is False


def test_parse_preserves_name_case():
    t = parse_create_table("CREATE TABLE MyTable (userId INTEGER, firstName TEXT)")
    assert t.name == "MyTable"
    assert t.columns[0].name == "userId"
    assert t.columns[1].name == "firstName"


def test_parse_duplicate_primary_key_raises():
    with pytest.raises(ValueError):
        parse_create_table("CREATE TABLE t (a INTEGER PRIMARY KEY, b TEXT PRIMARY KEY)")


def test_parse_unknown_type_raises():
    with pytest.raises(ValueError):
        parse_create_table("CREATE TABLE t (name VARCHAR(255))")


def test_parse_temp_raises():
    with pytest.raises(ValueError):
        parse_create_table("CREATE TEMP TABLE t (id INTEGER)")


def test_parse_without_rowid_raises():
    with pytest.raises(ValueError):
        parse_create_table("CREATE TABLE t (id INTEGER PRIMARY KEY) WITHOUT ROWID")


def test_parse_schema_prefix_raises():
    with pytest.raises(ValueError):
        parse_create_table("CREATE TABLE main.users (id INTEGER)")


def test_parse_missing_create_table_raises():
    with pytest.raises(ValueError):
        parse_create_table("INSERT INTO foo VALUES (1)")


def test_parse_empty_column_list_raises():
    with pytest.raises(ValueError):
        parse_create_table("CREATE TABLE t ()")


def test_parse_trailing_comma_raises():
    with pytest.raises(ValueError):
        parse_create_table("CREATE TABLE t (id INTEGER,)")


def test_parse_default_with_parens_raises():
    with pytest.raises(ValueError):
        parse_create_table("CREATE TABLE t (score INTEGER DEFAULT (42))")


# --- data model tests ---


def test_column_type_values():
    assert ColumnType.INTEGER == "INTEGER"
    assert ColumnType.TEXT == "TEXT"
    assert ColumnType.REAL == "REAL"
    assert ColumnType.BLOB == "BLOB"
    assert ColumnType.NUMERIC == "NUMERIC"


def test_column_defaults():
    col = Column(name="id", type=ColumnType.INTEGER)
    assert col.nullable is True
    assert col.primary_key is False


def test_table_rejects_duplicate_primary_keys():
    with pytest.raises(ValueError):
        Table(
            name="t",
            columns=[
                Column(name="a", type=ColumnType.INTEGER, primary_key=True),
                Column(name="b", type=ColumnType.TEXT, primary_key=True),
            ],
        )


def test_table_allows_no_primary_key():
    t = Table(
        name="t",
        columns=[
            Column(name="a", type=ColumnType.INTEGER),
            Column(name="b", type=ColumnType.TEXT),
        ],
    )
    assert len(t.columns) == 2
