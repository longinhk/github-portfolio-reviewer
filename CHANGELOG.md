# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Ruleset 1.4 commit-pinned evidence: README, tree, and inspected files are read
  from one resolved default-branch revision, which is displayed, exported, and
  used in evidence links.
- Explicit provisional-score semantics and verified, sampled, unverified, and
  provisional evidence counts in the UI and exports.
- Twelve frozen offline benchmark shapes for repository classification, rubric
  fit, score ranges, malformed CI, weak tests, and incomplete GitHub evidence.
- Python 3.13 compatibility testing alongside the protected Python 3.12 quality
  job.
- Ruleset 1.3 deterministic repository-type and rubric-fit assessment. Clear
  educational/content repositories are marked not scored, while monorepos and
  ambiguous layouts display a whole-repository caution.
- Separate repository-change and manual-verification guidance so incomplete
  evidence cannot claim recoverable points or invent a defect.
- Rubric applicability and recommendation kind in JSON and Markdown exports.
- A documented real-repository validation matrix covering conventional
  projects, monorepos, and content repositories.
- Optional default-branch subdirectory reviews for GitHub `/tree/` links, with
  scoped README, file-tree, and inspected evidence.
- Export schema 1.3 records whether a report covers the whole repository or a
  selected subdirectory.
- Ruleset 1.2 evidence-confidence labels: verified, sampled, unverified, and
  provisional.
- Fixed inspection buckets for security policy, dependency updating, project and
  test configuration, coverage, workflows, and test source evidence.
- Repository-root normalization for GitHub branch and file URLs while retaining
  default-branch review behavior.
- Broader documentation and release-history convention recognition.
- Advisory handling for credential-like test and example fixtures, while risky
  production-like paths remain failures requiring manual inspection.
- Explicit student-project scope, honest portfolio claims, required-cost table,
  and current Streamlit Community Cloud deployment guidance.
- GitHub-inspired dark and light themes.
- First-viewport score, status counts, unearned rubric points, and top actions.
- Status, category, and text filters for repository checks.
- Detailed recommendation issues with target files and current evidence.
- Responsive mobile layouts and specific GitHub API error guidance.
- Bounded inspection of Python tests, project configuration, GitHub Actions,
  Dependabot, security policy, and high-confidence secret patterns.
- Review focuses for General, Python, AI/ML, data-science, and backend internship
  applications without changing the comparable score.
- Stable Markdown and JSON report downloads that exclude raw repository content.
- Five-minute process-wide bounded caching and one bounded retry for temporary
  GitHub or connection failures.
- Versioned scoring rules with direct evidence-file links and explicit next
  steps for incomplete checks.
- Clear guarantees that no AI API, model key, or paid inference service is used.
- MIT License approved by the repository owner and recorded under the GitHub
  identity `longinhk`.

### Changed

- Public visitors no longer enter GitHub credentials. An optional token is read
  only from deployment secrets, reducing credential-handling risk.
- The clean credential-pattern result is sampled and receives partial credit;
  it no longer implies that uninspected files or Git history are secret-free.
- README detail, installation, CI, and test-quality checks require stronger
  evidence instead of passing on repeated filler, empty headings, workflow
  filenames, or test names alone.
- API resilience now includes one retry for GitHub 500 responses, shorter
  optional-file timeouts, and early stopping after repeated optional-inspection
  transport failures.
- Evidence links preserve scoped paths and filename casing and point to the
  exact reviewed commit.
- Monorepo detection now ignores manifests inside documentation, tests,
  examples, fixtures, and vendored support trees while retaining genuine nested
  projects.
- Treat absent contributing, code-of-conduct, and security-policy files as
  unverified repository-tree evidence because owner-level defaults are outside
  the current inspection scope.
- Renamed the headline metric to a portfolio-presentation score so it is not
  mistaken for a code-quality, developer-ability, or hiring score.
- Prepared package metadata for version 0.2.0. No 0.2.0 tag, GitHub release, or
  public deployment is claimed in this unreleased section.

## [0.1.0] - 2026-07-26

### Added

- Public GitHub repository metadata and file-tree collection.
- Deterministic analysis across seven portfolio categories and 27 checks.
- Transparent 100-point scoring and prioritized improvement suggestions.
- Offline Pytest suite, Ruff quality checks, GitHub Actions, Dependabot, and
  Streamlit deployment documentation.
