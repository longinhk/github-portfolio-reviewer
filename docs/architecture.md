# Architecture

The application uses a small clean-architecture boundary: HTTP and Streamlit
depend on the core review models, while repository analysis does not depend on
either external library.

```text
Streamlit UI (app.py)
        |
        v
Application service (service.py)
        |
        +----> GitHub API adapter (github_client.py) ----> GitHub REST API
        |
        v
Analyzer ----> Scoring ----> Suggestions
        \___________ domain models ___________/
```

## Module responsibilities

- `models.py` defines immutable data exchanged between layers.
- `github_client.py` validates input and converts GitHub JSON into a typed
  `RepositorySnapshot`. Raw dictionaries do not escape this adapter.
- `analyzer.py` applies deterministic checks to README text, metadata, and file
  paths. It performs no HTTP requests.
- `scoring.py` maps findings to an explicit 100-point rubric.
- `suggestions.py` converts incomplete checks into a prioritized, deduplicated
  action plan.
- `service.py` coordinates one review use case.
- `app.py` renders inputs and reports. It contains no scoring rules.

## Important decisions

### Three API requests per review

A normal review requests repository metadata, the preferred README, and the
recursive Git tree. Fetching every source file would consume rate limits,
increase latency, and turn a basic portfolio review into a code-scanning
product. Empty repositories need only metadata and the README check.

### Immutable snapshot

All checks analyze the same evidence snapshot. This avoids one check observing a
different repository state from another and makes the core rules easy to test.

### Heuristics stay visible

Each check returns a status and evidence. Scoring is a separate mapping, so a
weight change cannot silently alter detection behavior. The UI presents both
instead of hiding them behind one number.

### No automatic retries

Retries can make GitHub rate limits worse and produce surprising delays in an
interactive application. Expected API failures produce a clear message, and the
user decides when to retry.

### Truncated trees are incomplete evidence

GitHub can truncate recursive trees for very large repositories. A feature that
is found still passes; an absent path-based feature receives partial credit and
the report is marked provisional.

## Extension points

The next useful improvement would be an opt-in content analyzer for a small,
bounded set of configuration files. It should extend `RepositorySnapshot`
without allowing Requests or GitHub response dictionaries into the analyzer.
