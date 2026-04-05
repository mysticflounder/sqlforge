# sqlforge: General SQL Tokenizer — Design Spec

**Date:** 2026-04-04
**Status:** Draft
**Project:** sqlforge (SQLite reference implementation)
**Scope:** `tokenizer` module — v3 slice (enables INSERT/SELECT parsing)

---

## Overview

A general-purpose SQL tokenizer that handles the full lexical surface needed for DML statements (INSERT, SELECT, UPDATE, DELETE). The parser module's `tokenize()` only handles CREATE TABLE — it rejects quotes, doesn't parse string/number literals, and doesn't recognize operators.

This module produces typed tokens (`Token` with `kind` and `value`) instead of raw strings. The parser module keeps its own `tokenize()` unchanged; future modules (INSERT parser, SELECT parser, expression evaluator) use this tokenizer.

---

## Data Models

```python
class TokenKind(StrEnum):
    WORD = "WORD"           # keywords, identifiers: SELECT, users, id
    STRING = "STRING"       # string literals: 'hello', 'it''s'
    NUMBER = "NUMBER"       # numeric literals: 42, 3.14, -7 (sign is separate OP)
    OP = "OP"               # operators: =, <>, !=, <=, >=, <, >, +, -, *, /
    PUNCT = "PUNCT"         # structural: ( ) , ; .
```

`StrEnum` for clean serialization.

```python
class Token(BaseModel):
    kind: TokenKind
    value: str
```

`Token` is a Pydantic `BaseModel` so it participates in specforge extraction and validation. `value` stores the original text for WORD, STRING (without outer quotes, with escaped quotes resolved), NUMBER (as written), OP (the operator characters), and PUNCT (the single character).

---

## Functions

### `tokenize_sql(sql: str) -> list[Token]`

Splits a SQL string into a list of typed tokens. Scans character by character, left to right.

**Token recognition rules (in priority order):**

1. **Whitespace**: skip (spaces, tabs, newlines). Never produces a token.

2. **String literals** (`'`): Consume everything from the opening `'` to the closing `'`. SQLite uses `''` (two single quotes) as an escape for a literal single quote inside a string. The token value is the content between the outer quotes with `''` resolved to `'`. Raises `ValueError` on unterminated string (EOF before closing quote).

3. **Double-quoted identifiers** (`"`): Consume from `"` to `"`. Same `""` escape rule. Produces a `WORD` token (the identifier name without quotes, `""` resolved to `"`). Raises `ValueError` on unterminated.

4. **Number literals**: A digit (`0-9`) or a `.` followed by a digit starts a number. Consume digits, at most one `.`, then more digits. The token value is the text as written (e.g., `"42"`, `"3.14"`, `".5"`). Does not handle scientific notation (`1e10`) — out of scope for v1.

5. **Two-character operators**: Check the current character and the next:
   - `<>` → OP
   - `!=` → OP
   - `<=` → OP
   - `>=` → OP

6. **Single-character operators**: `=`, `<`, `>`, `+`, `-`, `*`, `/` → OP

7. **Punctuation**: `(`, `)`, `,`, `;`, `.` → PUNCT. Note: `.` only becomes PUNCT if rule 4 (number) didn't match (i.e., `.` not followed by a digit).

8. **Word tokens**: A letter or `_` starts a word. Consume letters, digits, and `_`. The token value preserves original case. Keywords are recognized by consumers, not the tokenizer.

9. **Backtick** (`` ` ``) and **bracket** (`[`): Raise `ValueError` — not supported in v1 (same as parser module).

10. **Any other character**: Raise `ValueError` with the unrecognized character.

**Test cases:**

*Basic tokenization:*
- `"SELECT * FROM users"` → `[WORD:SELECT, OP:*, WORD:FROM, WORD:users]`
- `"INSERT INTO t (a, b) VALUES (1, 'hello')"` → correct token sequence
- Empty string → `[]`
- Only whitespace → `[]`

*String literals:*
- `"'hello'"` → `[STRING:hello]`
- `"'it''s'"` → `[STRING:it's]` (escaped quote)
- `"''"` → `[STRING:]` (empty string)
- `"'a' 'b'"` → `[STRING:a, STRING:b]` (two separate strings)
- Unterminated `"'hello"` → `ValueError`

*Double-quoted identifiers:*
- `'"my column"'` → `[WORD:my column]`
- `'"has""quote"'` → `[WORD:has"quote]`
- Unterminated `'"hello'` → `ValueError`

*Number literals:*
- `"42"` → `[NUMBER:42]`
- `"3.14"` → `[NUMBER:3.14]`
- `".5"` → `[NUMBER:.5]`
- `"100"` → `[NUMBER:100]`

*Operators:*
- `"a = 1"` → `[WORD:a, OP:=, NUMBER:1]`
- `"a <> b"` → `[WORD:a, OP:<>, WORD:b]`
- `"a != b"` → `[WORD:a, OP:!=, WORD:b]`
- `"a <= b"` → `[WORD:a, OP:<=, WORD:b]`
- `"a >= b"` → `[WORD:a, OP:>=, WORD:b]`
- `"a < b"` → `[WORD:a, OP:<, WORD:b]`
- `"a > b"` → `[WORD:a, OP:>, WORD:b]`
- `"a + b - c * d / e"` → correct OP tokens

*Punctuation:*
- `"(a, b)"` → `[PUNCT:(, WORD:a, PUNCT:,, WORD:b, PUNCT:)]`
- `"t.col"` → `[WORD:t, PUNCT:., WORD:col]`
- `";"` → `[PUNCT:;]`

*Mixed:*
- `"SELECT id, name FROM users WHERE age >= 18"` → full correct token sequence
- `"INSERT INTO t VALUES (1, 'hello', 3.14)"` → full correct token sequence
- Case preservation: `"Select Id"` → `[WORD:Select, WORD:Id]`
- Underscore in identifiers: `"user_name"` → `[WORD:user_name]`
- Identifier starting with underscore: `"_private"` → `[WORD:_private]`

*Error cases:*
- Backtick `` "`foo`" `` → `ValueError`
- Bracket `"[foo]"` → `ValueError`
- Unrecognized character `"@"` → `ValueError`
- `"#"` → `ValueError`

---

## Dependencies

```yaml
stdlib: [enum]
third_party: [pydantic]
internal: []
```

No dependency on the parser module. This is intentionally independent — the tokenizer is a leaf module that future parsers will consume.

---

## Known Limitations (v1)

| Limitation | Behavior |
|---|---|
| No scientific notation | `1e10` tokenizes as `NUMBER:1`, `WORD:e10` |
| No hex literals | `0xFF` tokenizes as `NUMBER:0`, `WORD:xFF` |
| No negative number tokens | `-7` is `OP:-, NUMBER:7` (consumer handles unary minus) |
| No backtick identifiers | `` ` `` raises `ValueError` |
| No bracket identifiers | `[` raises `ValueError` |
| No block comments | `/* ... */` not recognized |
| No line comments | `-- ...` not recognized (the `--` parses as `OP:-, OP:-`) |
| No blob literals | `X'FF'` tokenizes as `WORD:X, STRING:FF` |
| No COLLATE sequences | Handled by consumers, not tokenizer |

---

## Specforge Method Notes

Third module in the extract→build cycle. This module is simpler than storage (no stateful class, just enum + model + one function) but has rich edge cases in string/number parsing that test how well specs convey lexical rules.
