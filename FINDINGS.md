# sqlforge — Extract→Build Cycle Findings

## Module 1: Parser

### Test results

- Spec tests passing in cleanroom verify: 38/38
- Behavior gaps (reference tests that cleanroom fails): none

Both `scripts/run-tests.sh sqlforge` (76 tests total, 38 reference + 38 cleanroom) and the
`specforge verify` subprocess all pass cleanly.

## What the extractor captured well

- **All five public units**: `ColumnType`, `Column`, `Table`, `tokenize`, `parse_create_table` extracted with correct kinds (type vs function).
- **Signatures**: both function signatures captured exactly — `tokenize(sql: str) -> list[str]` and `parse_create_table(sql: str) -> Table`.
- **Dependencies**: stdlib (`enum`) and third-party (`pydantic`) captured. Internal dependency graph (`parse_create_table` requires `Column`, `ColumnType`, `Table`, `tokenize`) captured correctly.
- **Class fields**: `Column` fields (`name`, `type`, `nullable`, `primary_key`) with type annotations extracted. `Table` fields and the `at_most_one_column_level_primary_key` validator method (with signature and `classmethod` decorator) extracted.
- **All 38 tests**: every test linked to the correct unit via `requires` edges. Test signatures captured.
- **ColumnType members**: all five enum values (`INTEGER`, `TEXT`, `REAL`, `BLOB`, `NUMERIC`) captured as `field` members.
- **Short docstrings**: top-level unit descriptions accurately derived from source docstrings.

## What the extractor missed

- **Private helper functions not in spec**: `_peek_at`, `_consume_length_specifier`, `_collect_constraint_tokens`, `_scan_not_null`, `_scan_primary_key` — all absent. This is by design (specforge targets public API surface), but the subagent had to invent its own private helper structure from scratch.
- **Behavioral contracts not in spec**: the extractor captures function signatures and a one-line description, but does not encode the algorithm. The `parse_create_table` spec says only "Parse a CREATE TABLE statement. Raises ValueError on unsupported syntax." — no mention of IF NOT EXISTS handling, schema prefix rejection, length specifier consumption, trailing comma detection, or WITHOUT ROWID rejection. These behaviors were successfully reproduced because they were encoded in the test suite, not the function description.
- **Default field values**: `Column.nullable` defaults to `True` and `Column.primary_key` defaults to `False`. The spec records `type_annotation: bool` for both fields but not the defaults. The subagent inferred the correct defaults from context (test `test_column_defaults` exercises them).
- **`noqa` comment**: `parse_create_table` carries `# noqa: C901` in the reference (complexity suppression). The spec does not capture inline comments, so the cleanroom build does not include it. Not a behavioral gap — just a ruff annotation.
- **Error message wording**: the spec contains no error message strings. The subagent produced functionally equivalent errors with different phrasing (e.g., "statement must begin with CREATE" vs "expected CREATE TABLE statement"). All `pytest.raises(ValueError)` tests pass regardless.
- **Test inline code**: spec TEST units have signatures and `requires` edges but no inline assertion code. The cleanroom build depends on the separately provided `output/test_parser.py` (a verbatim copy of the reference test file with import adjusted). The extractor does not yet round-trip test bodies.

## Key diff observations

All 211 diff lines are **functionally equivalent** — no behavior gaps, no hallucinated features:

| Category | Count | Examples |
|---|---|---|
| Variable name differences | ~40 lines | `buf`/`word`, `i`/`pos`, `n`/`total`, `tok`/`t` |
| Helper function renames | ~15 lines | `_peek_at` → `_token_at`, `_consume_length_specifier` → `_skip_length_specifier`, `_scan_not_null` → `_has_not_null` |
| Comment style | ~10 lines | Step-numbered comments (`# Step 4`) replaced with plain labels |
| Error message wording | ~5 lines | "expected CREATE TABLE statement" vs "statement must begin with CREATE" |
| Intermediate variable | 2 lines | `pks = sum(...)` introduced before `if pks > 1` in validator |

Zero behavior gaps. Zero hallucinated features.

### Implications for the spec writing standard

1. **Tests are the real spec for behavioral contracts.** The `parse_create_table` description is too thin to reproduce behavior from description alone — the 26 parse tests covering IF NOT EXISTS, trailing commas, schema prefixes, WITHOUT ROWID, etc. are what actually constrained the cleanroom build. The spec writing standard should require tests, not just descriptions.

2. **Default values must appear in the spec.** The extractor records `type_annotation` for Pydantic fields but not `default`. A subagent implementing from spec alone would have to guess that `nullable` defaults `True` and `primary_key` defaults `False`. For this module the test suite covered it, but that is a fragile dependency.

3. **Private helper structure is intentionally absent — and that is fine.** The cleanroom subagent invented equivalent private helpers with different names. All 38 tests pass. This confirms that the spec correctly captures the *interface contract* without over-specifying the implementation. The absence of private helpers in the spec is a feature, not a gap.

4. **Error message text should not be tested.** If any test had used `match=` on error messages, the cleanroom build would have failed on wording differences alone. The test suite correctly uses bare `pytest.raises(ValueError)` throughout.

5. **The extractor description field is underutilized.** For `tokenize` and `parse_create_table`, the description is a single sentence copied from the docstring. Richer descriptions (listing supported/unsupported syntax, naming the five `ColumnType` values, describing the length specifier behavior) would reduce how much the subagent has to infer from tests alone. A future spec writing standard should provide a description template with a "behaviors" bullet list.

---

## Module 2: Storage Engine

### Test results

- Spec tests passing in cleanroom verify: 56/56
- Behavior gaps: none
- Cleanroom passed on first attempt (no retries needed)

Full suite: `scripts/run-tests.sh sqlforge` runs 132 tests (38 parser + 38 parser cleanroom + 56 storage).

### What the extractor captured well

- **Both public units**: `coerce` (function) and `Database` (type with 6 methods) extracted with correct kinds.
- **All method signatures**: `insert(self, table_name: str, values: dict[str, Any]) -> int`, `select_all(self, table_name: str) -> list[dict[str, Any]]`, etc. — all captured exactly.
- **Method docstrings**: one-line descriptions for each method preserved ("Register a table schema. Raises ValueError on duplicate name (case-insensitive).").
- **Internal dependency**: `Database` requires `coerce` captured. External dependencies `ColumnType` and `Table` from parser captured.
- **All 56 tests**: every test linked to the correct unit (`coerce` or `Database`) via `requires` edges.

### What the extractor missed

- **Private helper not in spec**: `_coerce_integer` (reference) — absent by design. Cleanroom inlined the logic and invented `_is_integer_primary_key` instead.
- **Internal state not in spec**: `_tables`, `_rows`, `_rowid_seq` dicts not captured. The cleanroom invented equivalent state (`_tables`, `_rows`, `_next_rowid`) with the same structure.
- **Coercion rules not in descriptions**: the `coerce` docstring says "Apply SQLite type affinity coercion" but doesn't enumerate the per-affinity rules. The 27 coerce tests fully constrain the behavior.
- **Insert algorithm not described**: the spec says "Insert a row and return the rowid. Validates constraints and applies coercion." — no mention of case-insensitive column lookup, INTEGER PRIMARY KEY auto-assignment, or primary key uniqueness. All inferred from the 18 insert tests.

### Key diff observations

348 diff lines, cleanroom is 248 lines vs reference 195 (28% larger). All differences are **functionally equivalent**:

| Category | Examples |
|---|---|
| Code structure | Reference extracts `_coerce_integer` helper for reuse in INTEGER+NUMERIC. Cleanroom inlines logic in each branch — more verbose, same behavior. |
| Helper invention | Reference: `_coerce_integer`. Cleanroom: `_is_integer_primary_key`. Different decomposition, same result. |
| Internal naming | `_rowid_seq` vs `_next_rowid` |
| Error messages | "no such table" vs "table not found"; "duplicate value for PRIMARY KEY" vs "UNIQUE constraint failed" |
| Float comparison | Reference uses `.is_integer()`, cleanroom uses `value == int(value)` — equivalent for finite floats |
| IPK flow | Reference handles IPK inline during column loop. Cleanroom pre-processes IPK before the column loop. |
| Import scope | Reference imports only `ColumnType, Table`. Cleanroom also imports `Column` (uses it in helper function type hint). |
| Bool handling in REAL | Reference excludes bool from int-to-float path. Cleanroom converts bool to float. Both produce correct results since tests don't cover `coerce(True, REAL)` explicitly. |

Zero behavior gaps. Zero hallucinated features.

### New insights (beyond parser findings)

1. **Stateful classes work well in extract→build.** The `Database` class with mutable internal state was successfully reproduced from signatures and tests alone. The cleanroom invented equivalent internal state structures independently.

2. **Code reuse vs duplication is a style choice.** The reference's `_coerce_integer` helper saves ~30 lines by sharing logic between INTEGER and NUMERIC affinity. The cleanroom duplicated the logic. Both are correct — the spec correctly leaves this as an implementation choice.

3. **Test coverage drives cleanroom quality.** The 56 tests (27 coerce + 29 database) provided enough behavioral constraints that the cleanroom passed on the first attempt. The parser module (with 38 tests and more complex parsing logic) also passed first try. This suggests the test-to-code ratio matters more than description richness.

4. **Method descriptions are adequate for classes.** Unlike the parser where the single-function description was "too thin," the per-method descriptions on `Database` (e.g., "Register a table schema. Raises ValueError on duplicate name (case-insensitive)") gave enough context for the cleanroom to implement correct behavior. The `(case-insensitive)` parenthetical was particularly valuable.
