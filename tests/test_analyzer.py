"""Tests for deterministic repository-analysis rules."""

from collections.abc import Callable

from github_portfolio_reviewer.analyzer import analyze_repository
from github_portfolio_reviewer.models import (
    CheckId,
    CheckStatus,
    RepositorySnapshot,
)


def _strong_readme() -> str:
    body = " ".join(["portfolio"] * 210)
    return f"""# Project

[![CI](https://github.com/example/project/actions/workflows/ci.yml/badge.svg)](#)

![Application screenshot](docs/application.png)

## Installation

Create an environment and install the package.

## Usage examples

Run the Streamlit application and enter a public repository.

{body}
"""


def _statuses(snapshot: RepositorySnapshot) -> dict[CheckId, CheckStatus]:
    return {
        finding.check_id: finding.status for finding in analyze_repository(snapshot)
    }


def test_strong_repository_passes_every_check(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    files = (
        "LICENSE",
        ".gitignore",
        "pyproject.toml",
        "uv.lock",
        "src/project/__init__.py",
        "src/project/api.py",
        "src/project/analyzer.py",
        "tests/test_api.py",
        "tests/test_analyzer.py",
        "pytest.ini",
        ".coveragerc",
        ".github/workflows/ci.yml",
        "docs/architecture.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "CHANGELOG.md",
        "SECURITY.md",
        ".github/dependabot.yml",
    )
    snapshot = make_snapshot(
        description="A detailed project description that clearly explains its portfolio value.",
        topics=("python", "streamlit", "github-api"),
        license_name="MIT License",
        readme=_strong_readme(),
        files=files,
    )

    findings = analyze_repository(snapshot)

    assert len(findings) == len(CheckId)
    assert all(finding.status == CheckStatus.PASS for finding in findings)


def test_minimal_repository_produces_expected_failures(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    statuses = _statuses(make_snapshot(files=("contest.py",)))

    assert statuses[CheckId.README_EXISTS] == CheckStatus.FAIL
    assert statuses[CheckId.TEST_FILES] == CheckStatus.FAIL
    assert statuses[CheckId.CI_WORKFLOW] == CheckStatus.FAIL
    assert statuses[CheckId.NO_SENSITIVE_FILES] == CheckStatus.PASS
    assert statuses[CheckId.SOURCE_LAYOUT] == CheckStatus.PARTIAL


def test_paths_are_case_insensitive_and_both_workflow_suffixes_work(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    snapshot = make_snapshot(
        files=(
            ".GITHUB/WORKFLOWS/CI.YAML",
            "TESTS/TEST_APP.PY",
            "TESTS/TEST_API.PY",
            "DOCS/ARCHITECTURE.MD",
            "SECURITY.MD",
        )
    )
    statuses = _statuses(snapshot)

    assert statuses[CheckId.CI_WORKFLOW] == CheckStatus.PASS
    assert statuses[CheckId.TEST_FILES] == CheckStatus.PASS
    assert statuses[CheckId.DOCS] == CheckStatus.PASS
    assert statuses[CheckId.SECURITY_POLICY] == CheckStatus.PASS


def test_truncated_tree_turns_path_absence_into_partial_evidence(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = analyze_repository(make_snapshot(tree_truncated=True))
    by_id = {finding.check_id: finding for finding in findings}

    assert by_id[CheckId.CI_WORKFLOW].status == CheckStatus.PARTIAL
    assert "truncated" in by_id[CheckId.CI_WORKFLOW].evidence
    assert by_id[CheckId.NO_SENSITIVE_FILES].status == CheckStatus.PARTIAL


def test_sensitive_filename_is_warning_but_env_example_is_safe(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    safe = _statuses(make_snapshot(files=(".env.example",)))
    risky_findings = analyze_repository(
        make_snapshot(files=(".env.example", ".env", "keys/private.pem"))
    )
    risky = next(
        finding
        for finding in risky_findings
        if finding.check_id == CheckId.NO_SENSITIVE_FILES
    )

    assert safe[CheckId.NO_SENSITIVE_FILES] == CheckStatus.PASS
    assert risky.status == CheckStatus.FAIL
    assert "does not confirm" in risky.evidence


def test_readme_section_keywords_without_headings_receive_partial_credit(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    readme = "Installation is easy and usage is demonstrated here. " + "word " * 60
    statuses = _statuses(make_snapshot(readme=readme))

    assert statuses[CheckId.README_INSTALLATION] == CheckStatus.PARTIAL
    assert statuses[CheckId.README_USAGE] == CheckStatus.PARTIAL
    assert statuses[CheckId.README_DETAIL] == CheckStatus.PARTIAL
