# Real-repository validation matrix

The reviewer is tested primarily with deterministic offline fixtures. A small
set of public repositories is also reviewed manually before a ruleset release to
find layout assumptions that synthetic fixtures may miss.

These results are **validation observations, not endorsements or quality
rankings**. Public repositories change over time, so their numeric scores may be
different when the review is repeated. The portfolio-presentation score does
not measure code correctness, maintainer ability, popularity, or hiring value.

## Ruleset 1.3 observations

Observed on 2026-08-04 and rechecked after the monorepo-classification fix using
each repository's default branch.

| Repository | Expected shape | Observed classification | Presentation result |
| --- | --- | --- | ---: |
| `pallets/flask` | Conventional Python project | Software project · High fit | 84/100 |
| `psf/requests` | Conventional Python project | Software project · High fit | 89/100 |
| `django/django` | Large single project with support manifests | Software project · High fit | 76/100 |
| `pydantic/pydantic` | Root project plus `pydantic-core` | Monorepo · Medium fit | 92/100 |
| `freeCodeCamp/freeCodeCamp` | Multi-package repository | Monorepo · Medium fit | 77/100 |
| `EbookFoundation/free-programming-books` | Reference-content collection | Educational/content · Low fit | Not scored |
| `mattpocock/skills` | Skills/content collection | Educational/content · Low fit | Not scored |

## Defect found by the matrix

The first Ruleset 1.3 pass classified `django/django` as a monorepo because it
counted manifests under `docs/` and test fixtures as independent projects. The
classifier now ignores support manifests under documentation, tests, examples,
fixtures, and vendored trees while retaining genuine nested project roots.

Regression fixtures model the relevant Django, Pydantic, and freeCodeCamp path
shapes, so continuous integration verifies the corrected behavior without
depending on GitHub availability or mutable third-party repositories.

## Linked-subdirectory observation

On 2026-08-05, the reviewer analyzed
`HKUDS/CLI-Anything/tree/main/audacity/agent-harness` with linked-folder scope.
The resulting snapshot recorded `audacity/agent-harness`, used 34 relative file
paths, linked back to the same GitHub folder, and classified the scoped project
as a high-fit software project. Its observed presentation score was 41/100; that
number is included only to make this validation run auditable, not to judge the
project or establish a permanent expected score.

## How to repeat the validation

1. Start the Streamlit application.
2. Review each repository in the table using the **General** focus.
3. Record the ruleset version, date, repository type, rubric fit, and score state.
4. Investigate classification changes before updating this document.

Do not make live third-party scores exact continuous-integration assertions.
Doing so would make the test suite depend on network access and changes outside
this project's control.
