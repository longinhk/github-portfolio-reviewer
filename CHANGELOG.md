# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
- First-viewport score, status counts, recoverable points, and top actions.
- Status, category, and text filters for repository checks.
- Detailed recommendation issues with target files and current evidence.
- Responsive mobile layouts and specific GitHub API error guidance.
- Bounded inspection of Python tests, project configuration, GitHub Actions,
  Dependabot, security policy, and high-confidence secret patterns.
- Review focuses for General, Python, AI/ML, data-science, and backend internship
  applications without changing the comparable score.
- Stable Markdown and JSON report downloads that exclude raw repository content.
- Five-minute session-local caching and one bounded retry for temporary GitHub
  or connection failures.
- Versioned scoring rules with direct evidence-file links and explicit next
  steps for incomplete checks.
- Clear guarantees that no AI API, model key, or paid inference service is used.
- MIT License approved by the repository owner and recorded under the GitHub
  identity `longinhk`.

### Changed

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
