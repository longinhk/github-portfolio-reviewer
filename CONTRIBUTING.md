# Contributing

## Local setup

Use Python 3.12 or newer and install the project in an isolated environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Before submitting a change

Run all local quality checks:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

Tests must not call the real GitHub API. Inject a fake session or client and add
cases for both success and expected failures. Analyzer changes must remain
deterministic and must never execute code from the reviewed repository.

## Pull requests

Keep changes focused. Explain the user-visible behavior, important design
tradeoffs, and how the change was tested. If a scoring weight changes, preserve
the 100-point total, increment the ruleset version, and update the rubric
documentation. Do not add an AI service dependency to scoring or core report
generation.
