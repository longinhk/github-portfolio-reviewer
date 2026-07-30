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
        +----> Analyzer ----> Scoring ----> Suggestions
        |           \___________ domain models ___________/
        |
        +----> Markdown / JSON reporting
```

## Module responsibilities

- `models.py` defines immutable data exchanged between layers.
- `github_client.py` validates input and converts GitHub JSON into a typed
  `RepositorySnapshot`. It also owns bounded retries, caching, and text-file
  sampling. Raw dictionaries do not escape this adapter.
- `analyzer.py` applies deterministic checks to README text, metadata, file
  paths, and selected text evidence. It performs no HTTP requests and never
  executes repository code.
- `scoring.py` maps findings to an explicit 100-point rubric.
- `suggestions.py` converts incomplete checks into a prioritized, deduplicated
  action plan. A review focus changes ordering only, not points.
- `reporting.py` creates stable Markdown and JSON exports from allow-listed
  report fields. Raw README and file contents are excluded.
- `service.py` coordinates one review use case.
- `app.py` renders inputs and reports. It contains no scoring rules.

## Important decisions

### Deterministic and AI-free

The score and recommendations come from explicit Python rules. The application
does not call an LLM, embedding model, or other AI service, so no AI API key is
needed. Even the AI/ML internship focus is a deterministic suggestion filter.
Keeping one comparable rubric avoids hidden score changes between focuses.

### Bounded content inspection

A review requests repository metadata, the preferred README, and the recursive
Git tree. It may then fetch at most ten small, allow-listed text files such as
`pyproject.toml`, test files, workflows, `SECURITY.md`, and Dependabot
configuration. It never clones the repository, executes code, downloads
arbitrary binaries, or includes inspected content in exports.

The limit controls latency and protects GitHub's unauthenticated API allowance.
When a check cannot verify the specific content it needs, it returns partial
credit instead of pretending the missing evidence failed. A sufficient sampled
signal can still pass while clearly remaining a bounded review.

### Immutable snapshot

All checks analyze the same evidence snapshot. This avoids one check observing a
different repository state from another and makes the core rules easy to test.

### Heuristics stay visible

Each check returns a status and evidence. Scoring is a separate mapping, so a
weight change cannot silently alter detection behavior. The UI presents both
instead of hiding them behind one number.

### Small session-local cache

The Streamlit session reuses a GitHub client, which caches a bounded number of
repository snapshots for five minutes. The cache belongs to that browser
session. Changing the optional GitHub token creates a new client, and only a
one-way token fingerprint is retained for comparison.

### Bounded automatic retries

Temporary connection failures and GitHub `502`, `503`, or `504` responses are
retried once with a short delay. Authentication failures, missing repositories,
and rate limits are never retried automatically because doing so could worsen
the problem or hide a permanent error.

### Truncated trees are incomplete evidence

GitHub can truncate recursive trees for very large repositories. A feature that
is found still passes; an absent path-based feature receives partial credit and
the report is marked provisional.

### Safe portable reports

Markdown and JSON exports are built from an explicit schema rather than directly
serializing the repository snapshot. Tokens, raw README text, the complete file
tree, and inspected contents therefore cannot appear accidentally.

## Extension points

The next useful extension is a snapshot-comparison use case. It should compare
two saved report schemas rather than coupling history to Streamlit state or the
GitHub adapter.
