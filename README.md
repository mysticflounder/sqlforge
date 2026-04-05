# sqlforge

A SQLite reference implementation built to validate the [specforge](https://github.com/mysticflounder/specforge) extract→build cycle.

Each module is hand-written as a reference implementation, then:
1. A YAML spec is extracted from the code using `specforge extract`
2. A cleanroom implementation is built from the spec alone (no access to the reference)
3. The original test suite is run against the cleanroom output
4. Findings are documented comparing reference vs cleanroom

## Modules

| Module | Description | Tests | Cleanroom |
|--------|-------------|-------|-----------|
| parser | CREATE TABLE parser (tokenize + parse) | 38/38 | 38/38 |
| storage | In-memory storage engine (type coercion, constraints, rowid) | 56/56 | 56/56 |
| tokenizer | General SQL tokenizer (strings, numbers, operators) | 38/38 | 38/38 |

## Project Structure

```
sqlforge/          # Reference implementation (hand-written)
  parser.py        # SQL CREATE TABLE parser
  storage.py       # In-memory storage engine
  tokenizer.py     # General SQL tokenizer
tests/             # Test suite (shared between reference and cleanroom)
  test_parser.py
  test_storage.py
  test_tokenizer.py
specs/             # Extracted specforge YAML specs
  app.yaml
  parser.yaml
  storage.yaml
  tokenizer.yaml
output/            # Cleanroom implementations (built from spec only)
  parser.py
  storage.py
  tokenizer.py
docs/              # Design specifications
  parser-design.md
  storage-design.md
  tokenizer-design.md
FINDINGS.md        # Detailed comparison of reference vs cleanroom
```

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```

## Findings

Both modules achieve **zero behavior gaps** in cleanroom builds. See [FINDINGS.md](FINDINGS.md) for detailed analysis including:
- What the spec extractor captures well vs misses
- Diff analysis between reference and cleanroom implementations
- Implications for spec-driven development

## License

GPL-3.0-or-later
