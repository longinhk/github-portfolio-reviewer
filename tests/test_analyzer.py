"""Tests for deterministic repository-analysis rules."""

from collections.abc import Callable

from github_portfolio_reviewer.analyzer import analyze_repository
from github_portfolio_reviewer.models import (
    CheckId,
    CheckStatus,
    EvidenceConfidence,
    RepositorySnapshot,
    RepositoryTextFile,
)


def _strong_readme() -> str:
    paragraph = (
        "The reviewer collects public repository metadata and bounded text evidence, "
        "then applies transparent Python rules for documentation, testing, automation, "
        "security hygiene, and project structure. Every result includes its source, "
        "confidence, limitations, and a practical improvement so students can understand "
        "the engineering tradeoffs instead of trusting an unexplained rating. "
    )
    body = paragraph * 5
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
                "on: [push]\npermissions: read-all\njobs:\n  test:\n    steps:\n"
                "      - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
                "      - run: pytest --cov=project\n",
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
    assert all(
        finding.status == CheckStatus.PASS
        for finding in findings
        if finding.check_id != CheckId.NO_DETECTED_SECRETS
    )
    secret_sample = next(
        finding
        for finding in findings
        if finding.check_id == CheckId.NO_DETECTED_SECRETS
    )
    assert secret_sample.status == CheckStatus.PARTIAL
    assert secret_sample.confidence == EvidenceConfidence.SAMPLED


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

    assert statuses[CheckId.CI_WORKFLOW] == CheckStatus.PARTIAL
    assert statuses[CheckId.TEST_FILES] == CheckStatus.PASS
    assert statuses[CheckId.DOCS] == CheckStatus.PASS
    assert statuses[CheckId.SECURITY_POLICY] == CheckStatus.PARTIAL


def test_documentation_and_changelog_conventions_are_recognized(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    doc_directory = _statuses(
        make_snapshot(files=("doc/guide.rst", "doc/conf.py", "CHANGES"))
    )
    direct_whatsnew = _statuses(make_snapshot(files=("docs/whatsnew.rst",)))
    nested_release_notes = _statuses(
        make_snapshot(files=("documentation/release-notes/1.2.md",))
    )

    assert doc_directory[CheckId.DOCS] == CheckStatus.PASS
    assert doc_directory[CheckId.CHANGELOG] == CheckStatus.PASS
    assert direct_whatsnew[CheckId.CHANGELOG] == CheckStatus.PASS
    assert nested_release_notes[CheckId.CHANGELOG] == CheckStatus.PASS


def test_missing_community_files_are_unverified_not_definitively_missing(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = {
        finding.check_id: finding for finding in analyze_repository(make_snapshot())
    }

    for check_id in (
        CheckId.CONTRIBUTING,
        CheckId.CODE_OF_CONDUCT,
        CheckId.SECURITY_POLICY,
    ):
        finding = findings[check_id]
        assert finding.status == CheckStatus.PARTIAL
        assert finding.confidence == EvidenceConfidence.UNVERIFIED
        assert "owner-level default community files" in finding.evidence


def test_external_documentation_link_is_partial_and_unverified(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    finding = next(
        finding
        for finding in analyze_repository(
            make_snapshot(
                readme=(
                    "# Project\n\n"
                    "Read the [documentation](https://example.readthedocs.io/) "
                    "for the complete guide."
                )
            )
        )
        if finding.check_id == CheckId.DOCS
    )

    assert finding.status == CheckStatus.PARTIAL
    assert finding.confidence == EvidenceConfidence.UNVERIFIED


def test_doc_conf_is_not_counted_as_production_source(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    statuses = _statuses(make_snapshot(files=("doc/conf.py",)))

    assert statuses[CheckId.SOURCE_LAYOUT] == CheckStatus.FAIL
    assert statuses[CheckId.MODULARITY] == CheckStatus.FAIL


def test_truncated_tree_turns_path_absence_into_partial_evidence(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = analyze_repository(make_snapshot(tree_truncated=True))
    by_id = {finding.check_id: finding for finding in findings}

    assert by_id[CheckId.CI_WORKFLOW].status == CheckStatus.PARTIAL
    assert "truncated" in by_id[CheckId.CI_WORKFLOW].evidence
    assert by_id[CheckId.CI_WORKFLOW].confidence == EvidenceConfidence.PROVISIONAL
    assert by_id[CheckId.TEST_FILES].confidence == EvidenceConfidence.PROVISIONAL
    assert by_id[CheckId.NO_SENSITIVE_FILES].status == CheckStatus.PARTIAL
    assert (
        by_id[CheckId.NO_SENSITIVE_FILES].confidence == EvidenceConfidence.PROVISIONAL
    )


def test_sensitive_filename_is_warning_but_env_example_is_safe(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    safe_findings = analyze_repository(
        make_snapshot(
            files=(
                ".env.example",
                "tests/fixtures/test-cert.pem",
                "public-key.pem",
            )
        )
    )
    safe = {finding.check_id: finding.status for finding in safe_findings}
    safe_sensitive = next(
        finding
        for finding in safe_findings
        if finding.check_id == CheckId.NO_SENSITIVE_FILES
    )
    risky_findings = analyze_repository(
        make_snapshot(
            files=(
                ".env.example",
                ".env",
                "keys/private.pem",
                "config/server-key.pem",
            )
        )
    )
    risky = next(
        finding
        for finding in risky_findings
        if finding.check_id == CheckId.NO_SENSITIVE_FILES
    )

    assert safe[CheckId.NO_SENSITIVE_FILES] == CheckStatus.PASS
    assert "manual review" in safe_sensitive.evidence
    assert safe_sensitive.sources == (
        "tests/fixtures/test-cert.pem",
        "public-key.pem",
    )
    assert risky.status == CheckStatus.FAIL
    assert "does not confirm" in risky.evidence
    assert "config/server-key.pem" in risky.sources


def test_readme_section_keywords_without_headings_receive_partial_credit(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    readme = "Installation is easy and usage is demonstrated here. " + "word " * 60
    statuses = _statuses(make_snapshot(readme=readme))

    assert statuses[CheckId.README_INSTALLATION] == CheckStatus.PARTIAL
    assert statuses[CheckId.README_USAGE] == CheckStatus.PARTIAL
    assert statuses[CheckId.README_DETAIL] == CheckStatus.FAIL


def test_readme_sources_keep_the_actual_github_path(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    findings = analyze_repository(
        make_snapshot(
            readme="# Guide\n\n## Installation\n\nRun pip install locally.",
            readme_path="README.rst",
        )
    )

    readme_findings = (
        finding
        for finding in findings
        if finding.check_id
        in {
            CheckId.README_EXISTS,
            CheckId.README_DETAIL,
            CheckId.README_INSTALLATION,
        }
    )
    assert all(finding.sources == ("README.rst",) for finding in readme_findings)


def test_repeated_word_padding_does_not_pass_readme_detail(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    statuses = _statuses(make_snapshot(readme="# Project\n\n" + "padding " * 250))

    assert statuses[CheckId.README_DETAIL] == CheckStatus.FAIL


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
    assert strong_finding.confidence == EvidenceConfidence.VERIFIED
    assert _statuses(placeholders)[CheckId.TEST_QUALITY] == CheckStatus.FAIL
    unverified_finding = next(
        finding
        for finding in analyze_repository(make_snapshot(files=files))
        if finding.check_id == CheckId.TEST_QUALITY
    )
    assert unverified_finding.status == CheckStatus.PARTIAL
    assert unverified_finding.confidence == EvidenceConfidence.UNVERIFIED


def test_test_quality_requires_assertions_across_two_test_cases(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    path = "tests/test_service.py"
    statuses = _statuses(
        make_snapshot(
            files=(path,),
            inspected_files=(
                _inspected(
                    path,
                    "def test_first():\n"
                    "    assert service() == 1\n"
                    "    assert service() is not None\n\n"
                    "def test_second():\n"
                    "    service()\n",
                ),
            ),
        )
    )

    assert statuses[CheckId.TEST_QUALITY] == CheckStatus.PARTIAL


def test_partial_test_sample_has_sampled_confidence(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    files = ("tests/test_api.py", "tests/test_service.py")
    finding = next(
        finding
        for finding in analyze_repository(
            make_snapshot(
                files=files,
                inspected_files=(
                    _inspected(
                        files[0],
                        "def test_success():\n    assert call_api() == 200\n",
                    ),
                ),
            )
        )
        if finding.check_id == CheckId.TEST_QUALITY
    )

    assert finding.confidence == EvidenceConfidence.SAMPLED


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
                    "on: [push]\npermissions: read-all\njobs:\n  test:\n    steps:\n"
                    "      - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n",
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
                    "on: [push]\npermissions: write-all\njobs:\n  test:\n    steps:\n"
                    "      - uses: actions/checkout@v4\n",
                ),
            ),
        )
    )

    assert secure[CheckId.ACTIONS_PINNED] == CheckStatus.PASS
    assert secure[CheckId.CI_WORKFLOW] == CheckStatus.PASS
    assert secure[CheckId.WORKFLOW_PERMISSIONS] == CheckStatus.PASS
    assert unsafe[CheckId.ACTIONS_PINNED] == CheckStatus.FAIL
    assert unsafe[CheckId.WORKFLOW_PERMISSIONS] == CheckStatus.FAIL


def test_ci_check_prefers_an_inspected_workflow_over_an_uninspected_provider(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    workflow = ".github/workflows/ci.yml"
    statuses = _statuses(
        make_snapshot(
            files=(".circleci/config.yml", workflow),
            inspected_files=(
                _inspected(
                    workflow,
                    '"on": [push]\njobs:\n  test:\n    steps:\n      - run: pytest\n',
                ),
            ),
        )
    )

    assert statuses[CheckId.CI_WORKFLOW] == CheckStatus.PASS


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
    assert incomplete[CheckId.NO_DETECTED_SECRETS] == CheckStatus.PARTIAL
    assert (
        _statuses(make_snapshot())[CheckId.NO_DETECTED_SECRETS] == CheckStatus.PARTIAL
    )


def test_fixture_only_secret_pattern_requires_review_without_failing(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    finding = next(
        finding
        for finding in analyze_repository(
            make_snapshot(
                files=("tests/fixtures/test_credentials.py",),
                inspected_files=(
                    _inspected(
                        "tests/fixtures/test_credentials.py",
                        "ACCESS_KEY = '" + "AKIA" + "ABCDEFGHIJKLMNOP'",
                    ),
                ),
            )
        )
        if finding.check_id == CheckId.NO_DETECTED_SECRETS
    )

    assert finding.status == CheckStatus.PARTIAL
    assert "intentionally fake" in finding.evidence


def test_clean_secret_scan_is_sampled_not_full_repository_verification(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    finding = next(
        finding
        for finding in analyze_repository(
            make_snapshot(
                files=("pyproject.toml",),
                inspected_files=(_inspected("pyproject.toml", "[project]\n"),),
            )
        )
        if finding.check_id == CheckId.NO_DETECTED_SECRETS
    )

    assert finding.status == CheckStatus.PARTIAL
    assert finding.confidence == EvidenceConfidence.SAMPLED
