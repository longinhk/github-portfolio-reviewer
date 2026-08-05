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
        +----> Analyzer ----> Applicability ----> Scoring ----> Suggestions
        |           \________________ domain models ________________/
        |
        +----> Markdown / JSON reporting
```

## Module responsibilities

- `models.py` defines immutable data exchanged between layers.
- `github_client.py` validates and normalizes repository input, then converts
  GitHub JSON into a typed `RepositorySnapshot`. It also owns bounded retries,
  caching, optional default-branch subdirectory scoping, and bucketed text-file
  sampling. Raw dictionaries do not escape this adapter.
- `analyzer.py` applies deterministic checks to README text, metadata, file
  paths, and selected text evidence. It performs no HTTP requests and never
  executes repository code.
- `applicability.py` conservatively classifies software projects, monorepos,
  content repositories, and ambiguous layouts before a numeric score is shown.
- `scoring.py` maps findings to an explicit 100-point portfolio-presentation
  rubric and records the ruleset version.
- `suggestions.py` converts incomplete checks into a prioritized, deduplicated
  action plan. It separates repository changes from manual verification. A
  review focus changes ordering only, not points.
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

### Applicability gate

Ruleset 1.3 keeps one software-project rubric rather than inventing separate
scores for every repository purpose. Deterministic path, manifest, source, test,
content-file, name, description, and topic signals produce a repository type and
rubric fit:

- conventional software projects have high fit and receive a numeric score;
- monorepos and ambiguous layouts have medium fit, retain a whole-repository
  score, and display a caution;
- clear educational or content repositories have low fit, so the numeric score,
  category totals, and software-project recommendations are withheld.

Monorepo detection counts distinct manifest-backed project roots. Manifests in
documentation, tests, examples, fixtures, and vendored support directories do
not create project roots, preventing support tooling from triggering a
whole-repository warning.

The assessment is intentionally conservative. It does not use stars, forks, an
AI model, or repository popularity. An unfamiliar layout becomes medium fit
rather than being confidently misclassified.

### Bounded, category-reserved content inspection

A review requests repository metadata, the preferred README, and the recursive
Git tree. It may then fetch at most ten small, allow-listed text files. Ruleset
1.2 reserves fixed slots for one security policy, one dependency updater, one
`pyproject.toml`, one explicit test configuration, one coverage configuration,
two GitHub workflows, and three test sources. Paths are sorted deterministically
inside each bucket, and unused slots are not borrowed. This prevents a repository
with many workflows, for example, from consuming every test-inspection slot.

The adapter never clones the repository, executes code, downloads arbitrary
binaries, or includes inspected content in exports. Sensitive filenames are
never fetched merely for optional inspection.

The limit controls latency and protects GitHub's unauthenticated API allowance.
A check records evidence confidence separately from pass, partial, or fail:

- `verified` means direct metadata, a path, or inspected content supports the
  outcome;
- `sampled` means a bounded subset supports it while relevant evidence remains;
- `unverified` means a relevant path exists but no usable body was inspected;
- `provisional` means GitHub truncated the tree, so apparent absence is
  uncertain.

Status determines points; confidence communicates evidence completeness without
silently changing the rubric. A clean bounded credential scan is therefore
sampled evidence, not a claim that the entire repository is secret-free.

Suggestion type is also separate from points. Verified defects can produce a
repository-change suggestion. Sampled, unverified, provisional, or explicitly
review-dependent findings produce a zero-point manual-verification step instead
of claiming that a repository change is required.

### Repository URL normalization

The input parser accepts repository-root URLs plus GitHub `/tree/...` and
`/blob/...` URLs. Safe decoded `/tree/` segments are retained as a location
hint. When the user opts into folder scope, the client resolves the hint against
the default branch reported by GitHub, fetches that directory's README, and
relativizes its file evidence. Whole-repository mode remains available and is
the behavior for root, SSH, and `/blob/` inputs. Non-default-branch scope is
rejected rather than silently reviewing another revision. Query strings,
fragments, ports, unrelated GitHub subpages, and traversal-like segments remain
invalid.

Scoped reports intentionally retain parent-repository metadata while limiting
README and file-based checks to the selected folder. Root and scoped snapshots
use separate cache entries.

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
is found can still pass; apparent absence is marked provisional rather than
presented as verified missing evidence.

### Conservative convention and fixture handling

Ruleset 1.2 recognizes common `doc/`, `docs/`, and `documentation/` layouts,
documentation tooling and explicit external-documentation links, plus common
changelog, news, history, release-note, and whats-new conventions. This reduces
false negatives without fetching arbitrary documentation pages.

Certificate, key, or credential-like fixtures under conventional test, fixture,
example, or sample paths are advisory rather than automatic production-secret
failures. Production-like locations still fail and require manual inspection.
Neither result is a security audit.

Contributing guides, codes of conduct, and security policies may be inherited
from a repository owner's default community files. When none appears in the
repository tree, the result is unverified partial evidence and the user is asked
to check manually instead of being told the file is definitely missing.

### Safe portable reports

Markdown and JSON exports are built from an explicit schema rather than directly
serializing the repository snapshot. Tokens, raw README text, the complete file
tree, and inspected contents therefore cannot appear accidentally.

## Extension points

The next useful extension is a snapshot-comparison use case. It should compare
two saved report schemas rather than coupling history to Streamlit state or the
GitHub adapter.

## Scope boundary

This is a student portfolio application, not a production hiring or security
system. The architecture intentionally omits accounts, persistent report
history, payments, an AI service, and arbitrary code execution. Those omissions
keep the project understandable and directly support its purpose: demonstrating
Python design, API integration, deterministic reasoning, testing, and delivery.
