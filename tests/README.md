# Test Conventions

- Use `unittest` from the Python standard library unless a module explicitly needs another runner.
- Put tests under `tests/` and name files `test_*.py`.
- Run all tests with `uv run python -m unittest discover -s tests`.
- For schema tests, cover both a valid contract example and at least one boundary rejection.
- Do not require Redis, LLM providers, browser tooling, or network access in core unit tests.

