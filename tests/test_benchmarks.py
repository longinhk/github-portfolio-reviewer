"""Frozen repository-shape benchmarks for ruleset regression testing."""

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from github_portfolio_reviewer.analyzer import analyze_repository
from github_portfolio_reviewer.models import (
    CheckId,
    CheckStatus,
    RepositoryKind,
    RepositoryReference,
    RepositorySnapshot,
    RepositoryTextFile,
    RubricFit,
)
from github_portfolio_reviewer.scoring import score_repository


@dataclass(frozen=True, slots=True)
class BenchmarkExpectation:
    """Important stable outcomes for one synthetic repository shape."""

    name: str
    overrides: dict[str, object]
    kind: RepositoryKind
    fit: RubricFit
    score_range: tuple[float, float] | None
    checks: dict[CheckId, CheckStatus]


def _file(path: str, content: str) -> RepositoryTextFile:
    return RepositoryTextFile(path=path, content=content)


def _portfolio_readme() -> str:
    paragraph = (
        "This project demonstrates a clear engineering workflow with documented "
        "architecture, typed modules, automated verification, bounded external API "
        "requests, explicit limitations, reproducible dependencies, and practical "
        "examples for internship reviewers. The report explains every result and "
        "connects recommendations to observable repository evidence. "
    )
    return (
        "# Project\n\n"
        "[![CI](https://github.com/example/project/actions/workflows/ci.yml/badge.svg)](#)\n\n"
        "![Interface](docs/interface.png)\n\n"
        "## Installation\n\nCreate an environment and install the locked dependencies.\n\n"
        "## Usage\n\nRun the application and review the generated evidence report.\n\n"
        + paragraph
        * 5
    )


def _benchmarks() -> tuple[BenchmarkExpectation, ...]:
    secure_workflow = (
        "on: [push]\npermissions: read-all\njobs:\n  test:\n    steps:\n"
        "      - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "      - run: pytest --cov=project\n"
    )
    strong_files = (
        "LICENSE",
        ".gitignore",
        "pyproject.toml",
        "uv.lock",
        "src/project/app.py",
        "src/project/service.py",
        "tests/test_app.py",
        "tests/test_service.py",
        ".coveragerc",
        ".github/workflows/ci.yml",
        "docs/architecture.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "CHANGELOG.md",
        "SECURITY.md",
        ".github/dependabot.yml",
    )
    strong_inspection = (
        _file(
            "pyproject.toml",
            "[project]\nname='project'\n[tool.pytest.ini_options]\ntestpaths=['tests']\n",
        ),
        _file(".coveragerc", "[run]\nbranch=True\n"),
        _file("tests/test_app.py", "def test_app():\n    assert run() == 1\n"),
        _file(
            "tests/test_service.py",
            "def test_service():\n    assert service() is not None\n",
        ),
        _file(".github/workflows/ci.yml", secure_workflow),
        _file(
            "SECURITY.md",
            "# Security\n\nReport vulnerabilities privately by email so they can be acknowledged and investigated safely.",
        ),
        _file(
            ".github/dependabot.yml",
            "version: 2\nupdates:\n  - package-ecosystem: pip\n    directory: /\n    schedule:\n      interval: weekly\n",
        ),
    )
    return (
        BenchmarkExpectation(
            "beginner Python application",
            {
                "description": "A small Python learning application.",
                "readme": "# App\n\nRun python app.py.",
                "files": ("pyproject.toml", "app.py"),
            },
            RepositoryKind.SOFTWARE,
            RubricFit.HIGH,
            (15, 55),
            {CheckId.TEST_FILES: CheckStatus.FAIL},
        ),
        BenchmarkExpectation(
            "mature Python library",
            {
                "description": "A detailed reusable Python library with transparent engineering evidence.",
                "topics": ("python", "testing", "library"),
                "license_name": "MIT License",
                "readme": _portfolio_readme(),
                "files": strong_files,
                "inspected_files": strong_inspection,
            },
            RepositoryKind.SOFTWARE,
            RubricFit.HIGH,
            (90, 99),
            {CheckId.NO_DETECTED_SECRETS: CheckStatus.PARTIAL},
        ),
        BenchmarkExpectation(
            "ML notebook application",
            {
                "description": "A reproducible machine learning experiment application.",
                "language": "Jupyter Notebook",
                "readme": "# Experiment\n\n## Setup\n\nInstall requirements and launch Jupyter.\n\n## Usage\n\nRun the training notebook from top to bottom.",
                "files": ("requirements.txt", "notebooks/model.ipynb"),
            },
            RepositoryKind.SOFTWARE,
            RubricFit.HIGH,
            (20, 65),
            {CheckId.TEST_FILES: CheckStatus.FAIL},
        ),
        BenchmarkExpectation(
            "docs-heavy software",
            {
                "description": "A documented Python service with a conventional package layout.",
                "files": (
                    "pyproject.toml",
                    "src/service.py",
                    "docs/design.md",
                    "docs/api.md",
                    "docs/deployment.md",
                ),
            },
            RepositoryKind.SOFTWARE,
            RubricFit.HIGH,
            (20, 65),
            {CheckId.DOCS: CheckStatus.PASS},
        ),
        BenchmarkExpectation(
            "educational content collection",
            {
                "reference": RepositoryReference("example", "learning-notes"),
                "description": "Lecture notes, reading lists, and course slides",
                "files": (
                    "README.md",
                    "notes/one.md",
                    "notes/two.md",
                    "slides/week-1.pdf",
                ),
            },
            RepositoryKind.CONTENT,
            RubricFit.LOW,
            None,
            {},
        ),
        BenchmarkExpectation(
            "narrative algorithm article collection",
            {
                "reference": RepositoryReference("example", "algorithms"),
                "description": "Crack LeetCode, not only how, but also why.",
                "language": "Markdown",
                "files": (
                    "README.md",
                    "动态规划系列/状态转移详解.md",
                    "数据结构系列/二叉树遍历.md",
                    "算法思维系列/双指针技巧.md",
                    "高频面试系列/链表习题.md",
                ),
            },
            RepositoryKind.CONTENT,
            RubricFit.LOW,
            None,
            {},
        ),
        BenchmarkExpectation(
            "single-page tutorial index",
            {
                "reference": RepositoryReference("example", "build-from-scratch"),
                "description": "Tutorials for learning how technologies work",
                "topics": ("tutorials", "learning"),
                "files": ("README.md", "CONTRIBUTING.md"),
            },
            RepositoryKind.CONTENT,
            RubricFit.LOW,
            None,
            {},
        ),
        BenchmarkExpectation(
            "content list with validation tooling",
            {
                "description": "A collective list of free developer resources",
                "topics": ("list", "resources"),
                "files": (
                    "README.md",
                    "CONTRIBUTING.md",
                    "scripts/validate/links.py",
                    "scripts/tests/test_links.py",
                ),
            },
            RepositoryKind.CONTENT,
            RubricFit.LOW,
            None,
            {},
        ),
        BenchmarkExpectation(
            "content site with isolated website code",
            {
                "reference": RepositoryReference("example", "awesome-tools"),
                "description": "A definitive list of useful programming tools",
                "files": (
                    "README.md",
                    "CONTRIBUTING.md",
                    "docs/guide.md",
                    "pyproject.toml",
                    "website/build.py",
                    "website/tests/test_build.py",
                ),
            },
            RepositoryKind.CONTENT,
            RubricFit.LOW,
            None,
            {},
        ),
        BenchmarkExpectation(
            "content collection with archived tools",
            {
                "description": "A historical reference guide",
                "files": (
                    "README.md",
                    "docs/history.md",
                    "docs/faq.md",
                    "archived/tools/go.mod",
                    "archived/tools/main.go",
                    "archive/validator/Cargo.toml",
                    "archive/validator/src/main.rs",
                ),
            },
            RepositoryKind.CONTENT,
            RubricFit.LOW,
            None,
            {},
        ),
        BenchmarkExpectation(
            "narrative collection with vendored documentation tests",
            {
                "files": (
                    "README.md",
                    "notes/networking.md",
                    "notes/databases.md",
                    "docs/theme/vendor/tests/parser.test.js",
                    "docs/theme/vendor/tests/renderer.test.js",
                    "docs/theme/vendor/package.json",
                ),
            },
            RepositoryKind.CONTENT,
            RubricFit.LOW,
            None,
            {CheckId.TEST_FILES: CheckStatus.FAIL},
        ),
        BenchmarkExpectation(
            "skill collection with root tooling",
            {
                "description": "Reusable skills for software agents",
                "files": (
                    "package.json",
                    "README.md",
                    "skills/python/SKILL.md",
                    "skills/testing/SKILL.md",
                    "skills/security/SKILL.md",
                    "skills/python/scripts/validate.sh",
                    "skills/testing/scripts/check.sh",
                ),
            },
            RepositoryKind.CONTENT,
            RubricFit.LOW,
            None,
            {},
        ),
        BenchmarkExpectation(
            "curated list with root maintenance tooling",
            {
                "description": "A curated list of useful Go packages",
                "files": (
                    "go.mod",
                    "README.md",
                    "CONTRIBUTING.md",
                    "docs/selection-policy.md",
                    "main.go",
                    "convert.go",
                    "main_test.go",
                    "convert_test.go",
                ),
            },
            RepositoryKind.CONTENT,
            RubricFit.LOW,
            None,
            {CheckId.TEST_FILES: CheckStatus.PASS},
        ),
        BenchmarkExpectation(
            "numbered course with example code",
            {
                "files": (
                    "README.md",
                    "Day01-05/lesson.md",
                    "Day01-05/example.py",
                    "Day06-10/lesson.md",
                    "Day06-10/example.py",
                    "Day11-15/lesson.md",
                    "Day11-15/example.py",
                    "Day16-20/lesson.md",
                    "Day16-20/example.py",
                    "Day21-25/lesson.md",
                    "Day21-25/example.py",
                ),
            },
            RepositoryKind.CONTENT,
            RubricFit.LOW,
            None,
            {},
        ),
        BenchmarkExpectation(
            "educational guide with code examples",
            {
                "description": "Learn system design for technical interviews",
                "topics": ("guide", "interview"),
                "files": (
                    "README.md",
                    "guide/caching.md",
                    "guide/databases.md",
                    "solutions/cache.py",
                    "solutions/queue.py",
                ),
            },
            RepositoryKind.CONTENT,
            RubricFit.LOW,
            None,
            {},
        ),
        BenchmarkExpectation(
            "sample-heavy single project",
            {
                "files": (
                    "pyproject.toml",
                    "src/project.py",
                    "samples/widget/package.json",
                    "demos/service/pyproject.toml",
                ),
            },
            RepositoryKind.SOFTWARE,
            RubricFit.HIGH,
            (10, 55),
            {},
        ),
        BenchmarkExpectation(
            "two-service monorepo",
            {
                "files": (
                    "api/pyproject.toml",
                    "api/src/app.py",
                    "web/package.json",
                    "web/src/index.ts",
                ),
            },
            RepositoryKind.MONOREPO,
            RubricFit.MEDIUM,
            (10, 60),
            {},
        ),
        BenchmarkExpectation(
            "scoped package",
            {
                "scope_path": "packages/api",
                "html_url": "https://github.com/example/project/tree/main/packages/api",
                "files": ("pyproject.toml", "src/api.py", "tests/test_api.py"),
            },
            RepositoryKind.SOFTWARE,
            RubricFit.HIGH,
            (15, 65),
            {},
        ),
        BenchmarkExpectation(
            "archived application",
            {
                "archived": True,
                "files": ("pyproject.toml", "src/app.py", "tests/test_app.py"),
            },
            RepositoryKind.SOFTWARE,
            RubricFit.HIGH,
            (15, 65),
            {CheckId.ACTIVE: CheckStatus.PARTIAL},
        ),
        BenchmarkExpectation(
            "malformed CI configuration",
            {
                "files": (
                    "pyproject.toml",
                    "src/app.py",
                    ".github/workflows/ci.yml",
                ),
                "inspected_files": (
                    _file(".github/workflows/ci.yml", "name: CI\nthis is not a job"),
                ),
            },
            RepositoryKind.SOFTWARE,
            RubricFit.HIGH,
            (10, 60),
            {CheckId.CI_WORKFLOW: CheckStatus.PARTIAL},
        ),
        BenchmarkExpectation(
            "tests without assertions",
            {
                "files": (
                    "pyproject.toml",
                    "src/app.py",
                    "tests/test_app.py",
                    "tests/test_service.py",
                ),
                "inspected_files": (
                    _file("tests/test_app.py", "def test_app():\n    pass\n"),
                    _file("tests/test_service.py", "def test_service():\n    ...\n"),
                ),
            },
            RepositoryKind.SOFTWARE,
            RubricFit.HIGH,
            (10, 60),
            {CheckId.TEST_QUALITY: CheckStatus.FAIL},
        ),
        BenchmarkExpectation(
            "truncated repository evidence",
            {
                "tree_truncated": True,
                "files": ("README.md",),
            },
            RepositoryKind.UNKNOWN,
            RubricFit.MEDIUM,
            None,
            {CheckId.CI_WORKFLOW: CheckStatus.PARTIAL},
        ),
    )


@pytest.mark.parametrize("benchmark", _benchmarks(), ids=lambda case: case.name)
def test_frozen_repository_benchmarks(
    make_snapshot: Callable[..., RepositorySnapshot],
    benchmark: BenchmarkExpectation,
) -> None:
    """Keep classification and important findings stable across rule edits."""
    snapshot = make_snapshot(**benchmark.overrides)
    report = score_repository(snapshot, analyze_repository(snapshot))

    assert report.rubric_assessment.repository_kind == benchmark.kind
    assert report.rubric_assessment.fit == benchmark.fit
    if benchmark.score_range is None:
        assert report.presentation_score is None
    else:
        assert report.presentation_score is not None
        minimum, maximum = benchmark.score_range
        assert minimum <= report.score <= maximum
    statuses = {check.check_id: check.status for check in report.checks}
    for check_id, expected in benchmark.checks.items():
        assert statuses[check_id] == expected
