"""Tests for deterministic repository-analysis rules."""

from collections.abc import Callable

from github_portfolio_reviewer.analyzer import analyze_repository
from github_portfolio_reviewer.models import (
    CheckId,
    CheckStatus,
    RepositorySnapshot,
    RepositoryTextFile,
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


def _inspected(path: str, content: str) -> RepositoryTextFile:
    return RepositoryTextFile(path=path, content=content)


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
        inspected_files=(
            _inspected(
                "pyproject.toml",
                "[project]\nname = 'project'\n"
                "[tool.pytest.ini_options]\ntestpaths = ['tests']\n"
                "[tool.coverage.run]\nbranch = true\n",
            ),
            _inspected(
                "tests/test_api.py",
                "def test_api_success():\n    assert response_code() == 200\n",
            ),
            _inspected(
                "tests/test_analyzer.py",
                "def test_empty_input():\n    assert analyze('') == []\n",
            ),
            _inspected("pytest.ini", "[pytest]\ntestpaths = tests\n"),
            _inspected(".coveragerc", "[run]\nbranch = True\n"),
            _inspected(
                ".github/workflows/ci.yml",
                "permissions: read-all\nsteps:\n"
                "  - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
                "  - run: pytest --cov=project\n",
            ),
            _inspected(
                "SECURITY.md",
                "# Security policy\n\nReport a vulnerability privately by email to "
                "security@example.com. We will acknowledge and investigate every report.",
            ),
            _inspected(
                ".github/dependabot.yml",
                "version: 2\nupdates:\n  - package-ecosystem: pip\n"
                "    directory: /\n    schedule:\n      interval: weekly\n",
            ),
        ),
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


def test_test_support_modules_do_not_count_as_test_cases(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    statuses = _statuses(
        make_snapshot(files=("tests/__init__.py", "tests/conftest.py"))
    )

    assert statuses[CheckId.TEST_FILES] == CheckStatus.FAIL
    assert statuses[CheckId.TEST_QUALITY] == CheckStatus.FAIL


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
    assert statuses[CheckId.SECURITY_POLICY] == CheckStatus.PARTIAL


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


def test_test_quality_uses_ast_without_executing_code(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    files = ("tests/test_api.py", "tests/test_service.py")
    strong = make_snapshot(
        files=files,
        inspected_files=(
            _inspected(
                files[0],
                "def test_success():\n    assert call_api() == 200\n",
            ),
            _inspected(
                files[1],
                "def test_failure():\n    assert call_api() == 500\n",
            ),
        ),
    )
    placeholders = make_snapshot(
        files=files,
        inspected_files=(
            _inspected(files[0], "def test_success():\n    pass\n"),
            _inspected(files[1], "def test_failure():\n    assert True\n"),
        ),
    )

    strong_finding = next(
        finding
        for finding in analyze_repository(strong)
        if finding.check_id == CheckId.TEST_QUALITY
    )

    assert strong_finding.status == CheckStatus.PASS
    assert strong_finding.sources == files
    assert _statuses(placeholders)[CheckId.TEST_QUALITY] == CheckStatus.FAIL
    assert (
        _statuses(make_snapshot(files=files))[CheckId.TEST_QUALITY]
        == CheckStatus.PARTIAL
    )


def test_pyproject_content_verifies_test_and_coverage_configuration(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    valid_content = (
        "[tool.pytest.ini_options]\ntestpaths = ['tests']\n"
        "[tool.coverage.report]\nfail_under = 85\n"
    )
    valid = _statuses(
        make_snapshot(
            files=("pyproject.toml",),
            inspected_files=(_inspected("pyproject.toml", valid_content),),
        )
    )
    invalid = _statuses(
        make_snapshot(
            files=("pyproject.toml",),
            inspected_files=(_inspected("pyproject.toml", "not valid toml = ["),),
        )
    )

    assert valid[CheckId.TEST_CONFIGURATION] == CheckStatus.PASS
    assert valid[CheckId.COVERAGE] == CheckStatus.PASS
    assert invalid[CheckId.TEST_CONFIGURATION] == CheckStatus.FAIL
    assert invalid[CheckId.COVERAGE] == CheckStatus.FAIL


def test_workflow_content_checks_action_pins_and_permissions(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    path = ".github/workflows/ci.yml"
    secure = _statuses(
        make_snapshot(
            files=(path,),
            inspected_files=(
                _inspected(
                    path,
                    "permissions: read-all\nsteps:\n"
                    "  - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n",
                ),
            ),
        )
    )
    unsafe = _statuses(
        make_snapshot(
            files=(path,),
            inspected_files=(
                _inspected(
                    path,
                    "permissions: write-all\nsteps:\n  - uses: actions/checkout@v4\n",
                ),
            ),
        )
    )

    assert secure[CheckId.ACTIONS_PINNED] == CheckStatus.PASS
    assert secure[CheckId.WORKFLOW_PERMISSIONS] == CheckStatus.PASS
    assert unsafe[CheckId.ACTIONS_PINNED] == CheckStatus.FAIL
    assert unsafe[CheckId.WORKFLOW_PERMISSIONS] == CheckStatus.FAIL


def test_security_and_dependabot_files_are_content_validated(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    paths = ("SECURITY.md", ".github/dependabot.yml")
    valid = _statuses(
        make_snapshot(
            files=paths,
            inspected_files=(
                _inspected(
                    paths[0],
                    "Report security vulnerabilities privately to security@example.com. "
                    "We acknowledge reports and coordinate responsible disclosure promptly.",
                ),
                _inspected(
                    paths[1],
                    "version: 2\nupdates:\n  - package-ecosystem: pip\n"
                    "    directory: /\n    schedule:\n      interval: weekly\n",
                ),
            ),
        )
    )
    empty = _statuses(
        make_snapshot(
            files=paths,
            inspected_files=(_inspected(paths[0], ""), _inspected(paths[1], "")),
        )
    )

    assert valid[CheckId.SECURITY_POLICY] == CheckStatus.PASS
    assert valid[CheckId.DEPENDENCY_UPDATES] == CheckStatus.PASS
    assert empty[CheckId.SECURITY_POLICY] == CheckStatus.FAIL
    assert empty[CheckId.DEPENDENCY_UPDATES] == CheckStatus.FAIL


def test_secret_pattern_scan_is_bounded_and_reports_only_sampled_content(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    flagged = _statuses(
        make_snapshot(
            files=("config.py",),
            inspected_files=(
                _inspected(
                    "config.py",
                    "ACCESS_KEY = '" + "AKIA" + "ABCDEFGHIJKLMNOP'",
                ),
            ),
        )
    )
    incomplete = _statuses(
        make_snapshot(
            files=("config.py", "src/app.py"),
            inspected_files=(_inspected("config.py", "DEBUG = False"),),
            inspection_truncated=True,
        )
    )

    assert flagged[CheckId.NO_DETECTED_SECRETS] == CheckStatus.FAIL
    assert incomplete[CheckId.NO_DETECTED_SECRETS] == CheckStatus.PASS
    assert (
        _statuses(make_snapshot())[CheckId.NO_DETECTED_SECRETS] == CheckStatus.PARTIAL
    )
