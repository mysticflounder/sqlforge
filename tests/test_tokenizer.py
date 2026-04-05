import pytest
from sqlforge.tokenizer import Token, TokenKind, tokenize_sql


def _kinds(tokens: list[Token]) -> list[str]:
    return [t.kind for t in tokens]


def _values(tokens: list[Token]) -> list[str]:
    return [t.value for t in tokens]


# --- basic tokenization ---


def test_select_star():
    tokens = tokenize_sql("SELECT * FROM users")
    assert _kinds(tokens) == [TokenKind.WORD, TokenKind.OP, TokenKind.WORD, TokenKind.WORD]
    assert _values(tokens) == ["SELECT", "*", "FROM", "users"]


def test_insert_statement():
    tokens = tokenize_sql("INSERT INTO t (a, b) VALUES (1, 'hello')")
    assert _values(tokens) == [
        "INSERT", "INTO", "t", "(", "a", ",", "b", ")",
        "VALUES", "(", "1", ",", "hello", ")",
    ]


def test_empty_string():
    assert tokenize_sql("") == []


def test_only_whitespace():
    assert tokenize_sql("   \n\t  ") == []


# --- string literals ---


def test_string_literal():
    tokens = tokenize_sql("'hello'")
    assert len(tokens) == 1
    assert tokens[0].kind == TokenKind.STRING
    assert tokens[0].value == "hello"


def test_string_escaped_quote():
    tokens = tokenize_sql("'it''s'")
    assert tokens[0].value == "it's"


def test_string_empty():
    tokens = tokenize_sql("''")
    assert tokens[0].kind == TokenKind.STRING
    assert tokens[0].value == ""


def test_string_two_separate():
    tokens = tokenize_sql("'a' 'b'")
    assert _kinds(tokens) == [TokenKind.STRING, TokenKind.STRING]
    assert _values(tokens) == ["a", "b"]


def test_string_unterminated_raises():
    with pytest.raises(ValueError):
        tokenize_sql("'hello")


# --- double-quoted identifiers ---


def test_double_quoted_identifier():
    tokens = tokenize_sql('"my column"')
    assert len(tokens) == 1
    assert tokens[0].kind == TokenKind.WORD
    assert tokens[0].value == "my column"


def test_double_quoted_escaped():
    tokens = tokenize_sql('"has""quote"')
    assert tokens[0].value == 'has"quote'


def test_double_quoted_unterminated_raises():
    with pytest.raises(ValueError):
        tokenize_sql('"hello')


# --- number literals ---


def test_number_integer():
    tokens = tokenize_sql("42")
    assert tokens[0].kind == TokenKind.NUMBER
    assert tokens[0].value == "42"


def test_number_decimal():
    tokens = tokenize_sql("3.14")
    assert tokens[0].kind == TokenKind.NUMBER
    assert tokens[0].value == "3.14"


def test_number_leading_dot():
    tokens = tokenize_sql(".5")
    assert tokens[0].kind == TokenKind.NUMBER
    assert tokens[0].value == ".5"


def test_number_large():
    tokens = tokenize_sql("100")
    assert tokens[0].value == "100"


# --- operators ---


def test_op_equals():
    tokens = tokenize_sql("a = 1")
    assert tokens[1].kind == TokenKind.OP
    assert tokens[1].value == "="


def test_op_not_equal_angle():
    tokens = tokenize_sql("a <> b")
    assert tokens[1].value == "<>"


def test_op_not_equal_bang():
    tokens = tokenize_sql("a != b")
    assert tokens[1].value == "!="


def test_op_less_equal():
    tokens = tokenize_sql("a <= b")
    assert tokens[1].value == "<="


def test_op_greater_equal():
    tokens = tokenize_sql("a >= b")
    assert tokens[1].value == ">="


def test_op_less_than():
    tokens = tokenize_sql("a < b")
    assert tokens[1].value == "<"


def test_op_greater_than():
    tokens = tokenize_sql("a > b")
    assert tokens[1].value == ">"


def test_op_arithmetic():
    tokens = tokenize_sql("a + b - c * d / e")
    ops = [t.value for t in tokens if t.kind == TokenKind.OP]
    assert ops == ["+", "-", "*", "/"]


# --- punctuation ---


def test_punct_parens_comma():
    tokens = tokenize_sql("(a, b)")
    assert _kinds(tokens) == [
        TokenKind.PUNCT, TokenKind.WORD, TokenKind.PUNCT,
        TokenKind.WORD, TokenKind.PUNCT,
    ]


def test_punct_dot():
    tokens = tokenize_sql("t.col")
    assert _values(tokens) == ["t", ".", "col"]
    assert tokens[1].kind == TokenKind.PUNCT


def test_punct_semicolon():
    tokens = tokenize_sql(";")
    assert tokens[0].kind == TokenKind.PUNCT
    assert tokens[0].value == ";"


# --- mixed / complex ---


def test_select_where():
    tokens = tokenize_sql("SELECT id, name FROM users WHERE age >= 18")
    assert _values(tokens) == [
        "SELECT", "id", ",", "name", "FROM", "users",
        "WHERE", "age", ">=", "18",
    ]


def test_insert_with_values():
    tokens = tokenize_sql("INSERT INTO t VALUES (1, 'hello', 3.14)")
    assert _values(tokens) == [
        "INSERT", "INTO", "t", "VALUES",
        "(", "1", ",", "hello", ",", "3.14", ")",
    ]


def test_case_preservation():
    tokens = tokenize_sql("Select Id")
    assert _values(tokens) == ["Select", "Id"]


def test_underscore_identifier():
    tokens = tokenize_sql("user_name")
    assert tokens[0].kind == TokenKind.WORD
    assert tokens[0].value == "user_name"


def test_underscore_leading():
    tokens = tokenize_sql("_private")
    assert tokens[0].kind == TokenKind.WORD
    assert tokens[0].value == "_private"


# --- error cases ---


def test_backtick_raises():
    with pytest.raises(ValueError):
        tokenize_sql("`foo`")


def test_bracket_raises():
    with pytest.raises(ValueError):
        tokenize_sql("[foo]")


def test_at_sign_raises():
    with pytest.raises(ValueError):
        tokenize_sql("@")


def test_hash_raises():
    with pytest.raises(ValueError):
        tokenize_sql("#")


# --- data model tests ---


def test_token_kind_values():
    assert TokenKind.WORD == "WORD"
    assert TokenKind.STRING == "STRING"
    assert TokenKind.NUMBER == "NUMBER"
    assert TokenKind.OP == "OP"
    assert TokenKind.PUNCT == "PUNCT"


def test_token_construction():
    t = Token(kind=TokenKind.WORD, value="SELECT")
    assert t.kind == TokenKind.WORD
    assert t.value == "SELECT"
