# wordcount seed

Tiny Python CLI used as the FR-1701 lifecycle harness seed.

## Behaviour

- Reads one or more text files.
- Prints line/word/byte counts as ``table`` (default) or
  ``--format json`` output.
- Exits ``0`` on success; non-zero on parser error.

## Build/install hooks the harness exercises

- `python -m build --wheel` → emits `./dist/wordcount-0.1.0-py3-none-any.whl`.
- `pip install dist/wordcount-0.1.0-py3-none-any.whl` → places
  `wordcount` CLI on `PATH` inside the temp host venv.
- `wordcount README.md` → produces expected counts.
