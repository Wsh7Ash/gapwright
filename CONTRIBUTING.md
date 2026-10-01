# Contributing to gapwright

Thanks for your interest in improving gapwright!

## Development setup

```shell
git clone https://github.com/Wsh7Ash/gapwright.git
cd gapwright
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running tests

```shell
pytest -v
```

Please add tests for any new behavior. The parser, gap math, scoring, and
planner are all pure functions — tests stay fast and deterministic.

## Code style

- Python 3.12+, standard library only for runtime code.
- Type hints on public functions.
- Keep modules focused: `ics.py` (parse), `gaps.py` (geometry),
  `scoring.py` (weights), `planner.py` (fitting + persistence), `cli.py` (UI).

## Pull requests

1. Create a feature branch.
2. Make your change with tests.
3. Ensure `pytest` passes.
4. Update `README.md` / `docs/` if behavior or flags changed.
5. Add a `CHANGELOG.md` entry under "Unreleased".

## Reporting issues

Include the `.ics` snippet or task JSON that misbehaves (redact anything
private — calendar data is sensitive).
