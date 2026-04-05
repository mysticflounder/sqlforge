# sqlforge — SQLite Reference Implementation

Validation project for the specforge extract→build cycle.

## Modules

| Module | Reference | Spec | Cleanroom | Tests |
|--------|-----------|------|-----------|-------|
| parser | `sqlforge/parser.py` | `specs/parser.yaml` | `output/parser.py` | 38 |
| storage | `sqlforge/storage.py` | `specs/storage.yaml` | `output/storage.py` | 56 |
| tokenizer | `sqlforge/tokenizer.py` | `specs/tokenizer.yaml` | `output/tokenizer.py` | 38 |
| insert | `sqlforge/insert.py` | `specs/insert.yaml` | `output/insert.py` | 30 |

## Workflow

Per module:
1. Write design spec in `docs/`
2. Hand-write reference implementation in `sqlforge/`
3. `specforge extract` → `specs/<module>.yaml`
4. Cleanroom build from spec only → `output/<module>.py`
5. Verify all tests pass, document in FINDINGS.md

## Development

```bash
# Install
pip install -e ".[dev]"

# Run tests
pytest

# Run tests for a specific module
pytest tests/test_parser.py
pytest tests/test_storage.py
```

## Standards

- Python 3.13 target
- All `open()` calls: `encoding="utf-8"`
- Pydantic v2 for data models
- Tests use `pytest.raises(ValueError)` without `match=` (cleanroom may use different wording)
