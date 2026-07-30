"""Deterministic repository checks that do not depend on HTTP or the UI."""

import ast
import json
import re
import tomllib
from collections import Counter
from collections.abc import Callable
from pathlib import PurePosixPath

from github_portfolio_reviewer.models import (
    AnalysisFinding,
    CheckId,
    CheckStatus,
    RepositorySnapshot,
)

SOURCE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".ipynb",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".swift",
    ".ts",
    ".tsx",
}
RESERVED_SOURCE_DIRECTORIES = {
    ".git",
    ".github",
    ".venv",
    "build",
    "cache",
    "dist",
    "docs",
    "documentation",
    "examples",
    "generated",
    "node_modules",
    "test",
    "tests",
    "vendor",
}
SOURCE_DIRECTORIES = {"app", "lib", "pkg", "src"}
ROOT_MANIFESTS = {
    "build.gradle",
    "build.gradle.kts",
    "cargo.toml",
    "gemfile",
    "go.mod",
    "package.json",
    "pipfile",
    "pom.xml",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
}
TEST_CONFIG_PATTERNS = (
    re.compile(r"^(?:pytest\.ini|tox\.ini|noxfile\.py|conftest\.py)$"),
    re.compile(r"^(?:jest|vitest)\.config\.[^/]+$"),
)
COVERAGE_FILES = {
    ".coveragerc",
    ".nycrc",
    "codecov.yml",
    "codecov.yaml",
    "coverage.toml",
}
LOCK_FILES = {
    "bun.lock",
    "bun.lockb",
    "cargo.lock",
    "composer.lock",
    "gemfile.lock",
    "go.sum",
    "gradle.lockfile",
    "package-lock.json",
    "pdm.lock",
    "pipfile.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "yarn.lock",
}
GITHUB_WORKFLOW_PATTERN = re.compile(r"^\.github/workflows/.+\.ya?ml$")
SECRET_PATTERNS = (
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
)


def analyze_repository(snapshot: RepositorySnapshot) -> tuple[AnalysisFinding, ...]:
    """Analyze a repository snapshot and return one finding for every rubric check."""
    paths = tuple(_normalize_path(path) for path in snapshot.files)
    inspected = {
        _normalize_path(file.path): file.content for file in snapshot.inspected_files
    }
    readme = snapshot.readme or ""
    production_files = _production_source_files(paths)

    findings = (
        _description_finding(snapshot),
        _topics_finding(snapshot),
        _license_finding(snapshot, paths),
        _active_finding(snapshot),
        _readme_exists_finding(readme),
        _readme_detail_finding(readme),
        _readme_section_finding(
            CheckId.README_INSTALLATION,
            readme,
            ("installation", "install", "setup", "prerequisites", "getting started"),
            "installation or setup",
        ),
        _readme_section_finding(
            CheckId.README_USAGE,
            readme,
            ("usage", "how to use", "quickstart", "example", "examples"),
            "usage or examples",
        ),
        _readme_badges_finding(readme),
        _readme_visuals_finding(readme),
        _source_layout_finding(snapshot, production_files),
        _manifest_finding(snapshot, paths),
        _path_presence_finding(
            snapshot,
            paths,
            CheckId.GITIGNORE,
            lambda path: path == ".gitignore",
            lambda path: path.endswith("/.gitignore"),
            "a root .gitignore",
        ),
        _modularity_finding(production_files),
        _test_files_finding(snapshot, paths),
        _test_quality_finding(snapshot, paths, inspected),
        _test_configuration_finding(snapshot, paths, inspected),
        _coverage_finding(snapshot, paths, inspected, readme),
        _ci_workflow_finding(snapshot, paths),
        _actions_pinned_finding(snapshot, paths, inspected),
        _workflow_permissions_finding(snapshot, paths, inspected),
        _ci_badge_finding(readme),
        _docs_finding(snapshot, paths, readme),
        _governance_file_finding(
            snapshot,
            paths,
            CheckId.CONTRIBUTING,
            {"contributing.md", "contributing.rst", "contributing.adoc"},
            "a contributing guide",
        ),
        _governance_file_finding(
            snapshot,
            paths,
            CheckId.CODE_OF_CONDUCT,
            {
                "code_of_conduct.md",
                "code-of-conduct.md",
                "code_of_conduct.rst",
            },
            "a code of conduct",
        ),
        _governance_file_finding(
            snapshot,
            paths,
            CheckId.CHANGELOG,
            {"changelog.md", "changelog.rst", "history.md", "releases.md"},
            "a changelog or release history",
        ),
        _security_policy_finding(snapshot, paths, inspected),
        _dependency_updates_finding(snapshot, paths, inspected),
        _sensitive_files_finding(snapshot, paths),
        _detected_secrets_finding(snapshot),
        _lock_file_finding(snapshot, paths),
    )

    expected = set(CheckId)
    actual = {finding.check_id for finding in findings}
    if actual != expected or len(findings) != len(expected):
        raise RuntimeError("Analyzer checks do not match the scoring rubric.")
    return findings


def _description_finding(snapshot: RepositorySnapshot) -> AnalysisFinding:
    description = (snapshot.description or "").strip()
    if len(description) >= 50:
        return _finding(
            CheckId.DESCRIPTION, CheckStatus.PASS, "Detailed description set."
        )
    if description:
        return _finding(
            CheckId.DESCRIPTION,
            CheckStatus.PARTIAL,
            f"Description is brief ({len(description)} characters).",
        )
    return _finding(CheckId.DESCRIPTION, CheckStatus.FAIL, "No description set.")


def _topics_finding(snapshot: RepositorySnapshot) -> AnalysisFinding:
    count = len(snapshot.topics)
    if count >= 3:
        status = CheckStatus.PASS
    elif count:
        status = CheckStatus.PARTIAL
    else:
        status = CheckStatus.FAIL
    return _finding(CheckId.TOPICS, status, f"Found {count} repository topic(s).")


def _license_finding(
    snapshot: RepositorySnapshot, paths: tuple[str, ...]
) -> AnalysisFinding:
    license_paths = {
        "license",
        "license.md",
        "license.txt",
        "copying",
        "copying.md",
        "copying.txt",
    }
    license_file = next((path for path in paths if path in license_paths), None)
    if snapshot.license_name:
        return _finding(
            CheckId.LICENSE,
            CheckStatus.PASS,
            f"GitHub detected the {snapshot.license_name} license.",
        )
    if license_file:
        return _finding(
            CheckId.LICENSE,
            CheckStatus.PASS,
            f"Found {license_file}; GitHub did not identify its license type.",
            sources=(license_file,),
        )
    return _missing_path_finding(snapshot, CheckId.LICENSE, "No license file detected.")


def _active_finding(snapshot: RepositorySnapshot) -> AnalysisFinding:
    if snapshot.archived:
        return _finding(
            CheckId.ACTIVE,
            CheckStatus.PARTIAL,
            "Repository is archived; this may be intentional for a completed project.",
        )
    return _finding(CheckId.ACTIVE, CheckStatus.PASS, "Repository is not archived.")


def _readme_exists_finding(readme: str) -> AnalysisFinding:
    if readme.strip():
        return _finding(
            CheckId.README_EXISTS,
            CheckStatus.PASS,
            "README detected.",
            sources=("README.md",),
        )
    return _finding(CheckId.README_EXISTS, CheckStatus.FAIL, "No README detected.")


def _readme_detail_finding(readme: str) -> AnalysisFinding:
    word_count = len(re.findall(r"\b[\w'-]+\b", readme))
    if word_count >= 200:
        status = CheckStatus.PASS
    elif word_count >= 50:
        status = CheckStatus.PARTIAL
    else:
        status = CheckStatus.FAIL
    return _finding(
        CheckId.README_DETAIL,
        status,
        f"README contains approximately {word_count} words.",
        sources=("README.md",) if readme else (),
    )


def _readme_section_finding(
    check_id: CheckId,
    readme: str,
    terms: tuple[str, ...],
    label: str,
) -> AnalysisFinding:
    headings = [
        match.casefold()
        for match in re.findall(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", readme)
    ]
    if any(term in heading for heading in headings for term in terms):
        return _finding(
            check_id,
            CheckStatus.PASS,
            f"Found a {label} heading.",
            sources=("README.md",),
        )
    lowered = readme.casefold()
    if lowered and any(term in lowered for term in terms):
        return _finding(
            check_id,
            CheckStatus.PARTIAL,
            f"README mentions {label}, but has no clearly named section.",
            sources=("README.md",),
        )
    return _finding(check_id, CheckStatus.FAIL, f"README has no {label} guidance.")


def _image_targets(readme: str) -> tuple[str, ...]:
    markdown = re.findall(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)", readme)
    html = re.findall(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", readme, re.I)
    return tuple(markdown + html)


def _readme_badges_finding(readme: str) -> AnalysisFinding:
    targets = _image_targets(readme)
    badge_terms = ("shields.io", "badge.svg", "codecov", "coveralls")
    badges = [
        target
        for target in targets
        if any(term in target.casefold() for term in badge_terms)
    ]
    status = CheckStatus.PASS if badges else CheckStatus.FAIL
    return _finding(
        CheckId.README_BADGES,
        status,
        f"Found {len(badges)} status badge image(s)."
        if badges
        else "No status badges found.",
        sources=("README.md",) if readme else (),
    )


def _readme_visuals_finding(readme: str) -> AnalysisFinding:
    targets = _image_targets(readme)
    badge_terms = ("shields.io", "badge.svg", "codecov", "coveralls")
    visuals = [
        target
        for target in targets
        if not any(term in target.casefold() for term in badge_terms)
    ]
    status = CheckStatus.PASS if visuals else CheckStatus.FAIL
    return _finding(
        CheckId.README_VISUALS,
        status,
        f"Found {len(visuals)} non-badge visual(s)."
        if visuals
        else "No screenshots, diagrams, or demo visuals found.",
        sources=("README.md",) if readme else (),
    )


def _production_source_files(paths: tuple[str, ...]) -> tuple[str, ...]:
    files: list[str] = []
    for path in paths:
        pure_path = PurePosixPath(path)
        if pure_path.suffix not in SOURCE_EXTENSIONS:
            continue
        directory_parts = set(pure_path.parts[:-1])
        if directory_parts & RESERVED_SOURCE_DIRECTORIES:
            continue
        files.append(path)
    return tuple(files)


def _source_layout_finding(
    snapshot: RepositorySnapshot, production_files: tuple[str, ...]
) -> AnalysisFinding:
    if not production_files:
        return _missing_path_finding(
            snapshot, CheckId.SOURCE_LAYOUT, "No production source files detected."
        )

    conventional = [
        path
        for path in production_files
        if PurePosixPath(path).parts[0] in SOURCE_DIRECTORIES
    ]
    top_level_counts = Counter(
        PurePosixPath(path).parts[0]
        for path in production_files
        if len(PurePosixPath(path).parts) > 1
        and PurePosixPath(path).parts[0] not in RESERVED_SOURCE_DIRECTORIES
    )
    package_layout = any(count >= 2 for count in top_level_counts.values())
    if conventional or package_layout:
        return _finding(
            CheckId.SOURCE_LAYOUT,
            CheckStatus.PASS,
            "Production code is grouped in a recognizable source directory.",
            sources=tuple(production_files[:5]),
        )
    return _finding(
        CheckId.SOURCE_LAYOUT,
        CheckStatus.PARTIAL,
        "Source files exist, but only at the repository root or an unconventional path.",
        sources=tuple(production_files[:5]),
    )


def _manifest_finding(
    snapshot: RepositorySnapshot, paths: tuple[str, ...]
) -> AnalysisFinding:
    root_manifest = next(
        (
            path
            for path in paths
            if path in ROOT_MANIFESTS or re.fullmatch(r"requirements[^/]*\.txt", path)
        ),
        None,
    )
    if root_manifest:
        return _finding(
            CheckId.DEPENDENCY_MANIFEST,
            CheckStatus.PASS,
            f"Found root dependency/build manifest: {root_manifest}.",
            sources=(root_manifest,),
        )
    nested_manifest = next(
        (
            path
            for path in paths
            if PurePosixPath(path).name in ROOT_MANIFESTS
            or re.fullmatch(r"requirements[^/]*\.txt", PurePosixPath(path).name)
        ),
        None,
    )
    if nested_manifest:
        return _finding(
            CheckId.DEPENDENCY_MANIFEST,
            CheckStatus.PARTIAL,
            f"Manifest is nested at {nested_manifest}.",
            sources=(nested_manifest,),
        )
    return _missing_path_finding(
        snapshot, CheckId.DEPENDENCY_MANIFEST, "No dependency/build manifest found."
    )


def _path_presence_finding(
    snapshot: RepositorySnapshot,
    paths: tuple[str, ...],
    check_id: CheckId,
    pass_match: Callable[[str], bool],
    partial_match: Callable[[str], bool],
    label: str,
) -> AnalysisFinding:
    passing = next((path for path in paths if pass_match(path)), None)
    if passing:
        return _finding(
            check_id,
            CheckStatus.PASS,
            f"Found {passing}.",
            sources=(passing,),
        )
    partial = next((path for path in paths if partial_match(path)), None)
    if partial:
        return _finding(
            check_id,
            CheckStatus.PARTIAL,
            f"Found nested file {partial}.",
            sources=(partial,),
        )
    return _missing_path_finding(snapshot, check_id, f"Could not find {label}.")


def _modularity_finding(production_files: tuple[str, ...]) -> AnalysisFinding:
    count = len(production_files)
    if count >= 3:
        status = CheckStatus.PASS
    elif count:
        status = CheckStatus.PARTIAL
    else:
        status = CheckStatus.FAIL
    return _finding(
        CheckId.MODULARITY,
        status,
        f"Found {count} production source file(s), excluding tests and generated code.",
        sources=tuple(production_files[:5]),
    )


def _is_test_file(path: str) -> bool:
    pure_path = PurePosixPath(path)
    name = pure_path.name
    if name in {"__init__.py", "conftest.py", "factories.py", "fixtures.py"}:
        return False
    parts = set(pure_path.parts[:-1])
    if {"test", "tests", "__tests__", "spec", "specs"} & parts:
        return pure_path.suffix in SOURCE_EXTENSIONS
    return bool(
        re.fullmatch(r"test_.+\.py", name)
        or re.fullmatch(r".+_test\.py", name)
        or re.fullmatch(r".+\.(?:test|spec)\.[jt]sx?", name)
    )


def _test_files_finding(
    snapshot: RepositorySnapshot, paths: tuple[str, ...]
) -> AnalysisFinding:
    test_files = [path for path in paths if _is_test_file(path)]
    count = len(test_files)
    if count >= 2:
        status = CheckStatus.PASS
    elif count == 1:
        status = CheckStatus.PARTIAL
    elif snapshot.tree_truncated:
        status = CheckStatus.PARTIAL
    else:
        status = CheckStatus.FAIL
    evidence = f"Found {count} conventionally named test file(s)."
    if snapshot.tree_truncated and not test_files:
        evidence += " The Git tree was truncated, so absence is uncertain."
    return _finding(
        CheckId.TEST_FILES,
        status,
        evidence,
        sources=tuple(test_files[:5]),
    )


def _test_quality_finding(
    snapshot: RepositorySnapshot,
    paths: tuple[str, ...],
    inspected: dict[str, str],
) -> AnalysisFinding:
    """Assess bounded test implementation signals without executing repository code."""
    test_paths = [path for path in paths if _is_test_file(path)]
    if not test_paths:
        return _missing_path_finding(
            snapshot,
            CheckId.TEST_QUALITY,
            "No test files are available for implementation-quality inspection.",
        )

    sampled = [(path, inspected[path]) for path in test_paths if path in inspected]
    if not sampled:
        return _finding(
            CheckId.TEST_QUALITY,
            CheckStatus.PARTIAL,
            "Test files exist, but their contents were not sampled; test quality is unverified.",
            sources=tuple(test_paths[:5]),
        )

    test_cases = 0
    assertion_signals = 0
    parse_errors = 0
    for path, content in sampled:
        cases, assertions, parsed = _test_metrics(path, content)
        test_cases += cases
        assertion_signals += assertions
        parse_errors += not parsed

    incomplete = len(sampled) < len(test_paths)
    if test_cases >= 2 and assertion_signals >= 1:
        status = CheckStatus.PASS
    elif test_cases or assertion_signals or parse_errors or incomplete:
        status = CheckStatus.PARTIAL
    else:
        status = CheckStatus.FAIL

    evidence = (
        f"Sampled {len(sampled)} of {len(test_paths)} test file(s); found "
        f"{test_cases} implemented test case(s) and {assertion_signals} assertion signal(s)."
    )
    if parse_errors:
        evidence += f" {parse_errors} sampled file(s) could not be parsed safely."
    if incomplete:
        evidence += " The bounded inspection did not cover every test file."
    return _finding(
        CheckId.TEST_QUALITY,
        status,
        evidence,
        sources=tuple(path for path, _ in sampled),
    )


def _test_metrics(path: str, content: str) -> tuple[int, int, bool]:
    """Return deterministic test-case and assertion counts for sampled text."""
    if PurePosixPath(path).suffix == ".py":
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):
            return 0, 0, False

        test_nodes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        implemented = sum(not _is_placeholder_test(node) for node in test_nodes)
        assertions = sum(_is_assertion_signal(node) for node in ast.walk(tree))
        return implemented, assertions, True

    test_cases = len(re.findall(r"(?m)\b(?:it|test)\s*\(", content))
    assertions = len(re.findall(r"(?m)\b(?:expect|assert)\s*\(?", content))
    return test_cases, assertions, True


def _is_placeholder_test(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    statements = [
        statement
        for statement in node.body
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )
    ]
    if not statements:
        return True
    if all(
        isinstance(statement, ast.Pass)
        or isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and statement.value.value is Ellipsis
        for statement in statements
    ):
        return True
    return bool(
        len(statements) == 1
        and isinstance(statements[0], ast.Assert)
        and isinstance(statements[0].test, ast.Constant)
        and statements[0].test.value is True
    )


def _is_assertion_signal(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        return not (isinstance(node.test, ast.Constant) and node.test.value is True)
    if not isinstance(node, ast.Call):
        return False
    function = node.func
    if isinstance(function, ast.Attribute):
        return function.attr == "raises" or function.attr.startswith("assert")
    return isinstance(function, ast.Name) and (
        function.id == "raises" or function.id.startswith("assert")
    )


def _test_configuration_finding(
    snapshot: RepositorySnapshot,
    paths: tuple[str, ...],
    inspected: dict[str, str],
) -> AnalysisFinding:
    candidates = [
        path
        for path in paths
        if any(
            pattern.fullmatch(PurePosixPath(path).name)
            for pattern in TEST_CONFIG_PATTERNS
        )
        or path in {"pyproject.toml", "setup.cfg"}
    ]
    sampled = [(path, inspected[path]) for path in candidates if path in inspected]
    valid = [
        path for path, content in sampled if _has_test_configuration(path, content)
    ]
    if valid:
        return _finding(
            CheckId.TEST_CONFIGURATION,
            CheckStatus.PASS,
            f"Verified test configuration in {valid[0]}.",
            sources=(valid[0],),
        )
    if candidates and (not sampled or len(sampled) < len(candidates)):
        return _finding(
            CheckId.TEST_CONFIGURATION,
            CheckStatus.PARTIAL,
            "Possible test-configuration files exist, but bounded content inspection could not verify their settings.",
            sources=tuple(candidates[:5]),
        )
    if sampled:
        return _finding(
            CheckId.TEST_CONFIGURATION,
            CheckStatus.FAIL,
            "Inspected configuration files do not contain recognized test settings.",
            sources=tuple(path for path, _ in sampled),
        )
    if "package.json" in paths:
        return _finding(
            CheckId.TEST_CONFIGURATION,
            CheckStatus.PARTIAL,
            "package.json may define a test command, but its content was not inspected.",
            sources=("package.json",),
        )
    return _missing_path_finding(
        snapshot, CheckId.TEST_CONFIGURATION, "No explicit test configuration found."
    )


def _has_test_configuration(path: str, content: str) -> bool:
    name = PurePosixPath(path).name
    if name == "pyproject.toml":
        try:
            configuration = tomllib.loads(content)
        except (tomllib.TOMLDecodeError, ValueError):
            return False
        tool = configuration.get("tool")
        return bool(
            isinstance(tool, dict)
            and isinstance(tool.get("pytest"), dict)
            and isinstance(tool["pytest"].get("ini_options"), dict)
        )
    if name in {"pytest.ini", "tox.ini", "setup.cfg"}:
        return bool(re.search(r"(?im)^\s*\[(?:pytest|tool:pytest)\]\s*$", content))
    if name in {"noxfile.py", "conftest.py"}:
        try:
            ast.parse(content)
        except (SyntaxError, ValueError):
            return False
        return bool(re.search(r"\bpytest\b", content))
    return bool(
        content.strip() and re.search(r"\b(?:test|describe|vitest|jest)\b", content)
    )


def _coverage_finding(
    snapshot: RepositorySnapshot,
    paths: tuple[str, ...],
    inspected: dict[str, str],
    readme: str,
) -> AnalysisFinding:
    candidates = [
        path
        for path in paths
        if PurePosixPath(path).name in COVERAGE_FILES
        or path == "pyproject.toml"
        or GITHUB_WORKFLOW_PATTERN.fullmatch(path)
    ]
    sampled = [(path, inspected[path]) for path in candidates if path in inspected]
    verified = [
        path for path, content in sampled if _has_coverage_configuration(path, content)
    ]
    if verified:
        return _finding(
            CheckId.COVERAGE,
            CheckStatus.PASS,
            f"Verified coverage configuration or execution in {verified[0]}.",
            sources=(verified[0],),
        )
    if re.search(r"\b(?:coverage|codecov|coveralls)\b", readme, re.I):
        return _finding(
            CheckId.COVERAGE,
            CheckStatus.PARTIAL,
            "README mentions coverage, but no dedicated configuration file was detected.",
            sources=("README.md",),
        )
    dedicated = [
        path for path in candidates if PurePosixPath(path).name in COVERAGE_FILES
    ]
    incomplete = len(sampled) < len(candidates) or bool(dedicated and not sampled)
    if candidates and incomplete:
        return _finding(
            CheckId.COVERAGE,
            CheckStatus.PARTIAL,
            "Potential coverage configuration exists, but bounded content inspection could not verify it.",
            sources=tuple(candidates[:5]),
        )
    if sampled:
        return _finding(
            CheckId.COVERAGE,
            CheckStatus.FAIL,
            "Inspected project and workflow configuration does not enable coverage tracking.",
            sources=tuple(path for path, _ in sampled),
        )
    return _missing_path_finding(
        snapshot, CheckId.COVERAGE, "No coverage configuration or badge detected."
    )


def _has_coverage_configuration(path: str, content: str) -> bool:
    name = PurePosixPath(path).name
    if name == "pyproject.toml":
        try:
            configuration = tomllib.loads(content)
        except (tomllib.TOMLDecodeError, ValueError):
            return False
        tool = configuration.get("tool")
        return bool(isinstance(tool, dict) and isinstance(tool.get("coverage"), dict))
    if name in COVERAGE_FILES:
        if name in {"codecov.yml", "codecov.yaml"}:
            return any(
                line.strip() and not line.lstrip().startswith("#")
                for line in content.splitlines()
            )
        return bool(
            re.search(
                r"(?im)^\s*\[(?:run|report|coverage:run|coverage:report)\]\s*$|\bfail_under\s*=",
                content,
            )
        )
    return bool(
        re.search(
            r"(?i)(?:pytest\s+[^\n]*--cov\b|coverage\s+run\b|codecov(?:/|-)action|coveralls)",
            content,
        )
    )


def _ci_workflow_finding(
    snapshot: RepositorySnapshot, paths: tuple[str, ...]
) -> AnalysisFinding:
    ci_file = next((path for path in paths if _is_ci_file(path)), None)
    if ci_file:
        return _finding(
            CheckId.CI_WORKFLOW,
            CheckStatus.PASS,
            f"Detected CI configuration at {ci_file}; execution status was not verified.",
            sources=(ci_file,),
        )
    return _missing_path_finding(
        snapshot, CheckId.CI_WORKFLOW, "No recognized CI configuration detected."
    )


def _is_ci_file(path: str) -> bool:
    return bool(
        GITHUB_WORKFLOW_PATTERN.fullmatch(path)
        or path
        in {
            ".circleci/config.yml",
            ".travis.yml",
            "azure-pipelines.yml",
            "jenkinsfile",
        }
    )


def _actions_pinned_finding(
    snapshot: RepositorySnapshot,
    paths: tuple[str, ...],
    inspected: dict[str, str],
) -> AnalysisFinding:
    workflows = [path for path in paths if GITHUB_WORKFLOW_PATTERN.fullmatch(path)]
    if not workflows:
        return _missing_path_finding(
            snapshot,
            CheckId.ACTIONS_PINNED,
            "No GitHub Actions workflow is available for action-reference inspection.",
        )

    sampled = [(path, inspected[path]) for path in workflows if path in inspected]
    if not sampled:
        return _finding(
            CheckId.ACTIONS_PINNED,
            CheckStatus.PARTIAL,
            "GitHub Actions workflows exist, but their contents were not sampled; action pinning is unverified.",
            sources=tuple(workflows[:5]),
        )

    references: list[tuple[str, str]] = []
    for path, content in sampled:
        references.extend(
            (path, reference) for reference in _action_references(content)
        )
    unpinned = [
        (path, reference)
        for path, reference in references
        if not re.fullmatch(r"[0-9a-fA-F]{40}", reference.rsplit("@", 1)[-1])
    ]
    if unpinned:
        examples = ", ".join(reference for _, reference in unpinned[:3])
        return _finding(
            CheckId.ACTIONS_PINNED,
            CheckStatus.FAIL,
            f"Found {len(unpinned)} action reference(s) not pinned to a full commit SHA: {examples}.",
            sources=tuple(dict.fromkeys(path for path, _ in unpinned)),
        )

    incomplete = len(sampled) < len(workflows)
    if incomplete:
        status = CheckStatus.PARTIAL
        suffix = " Additional workflow files were not inspected."
    else:
        status = CheckStatus.PASS
        suffix = ""
    return _finding(
        CheckId.ACTIONS_PINNED,
        status,
        f"Inspected {len(sampled)} workflow(s); all {len(references)} external action reference(s) use full commit SHAs.{suffix}",
        sources=tuple(path for path, _ in sampled),
    )


def _action_references(content: str) -> tuple[str, ...]:
    references = re.findall(r"(?im)^\s*(?:-\s*)?uses:\s*['\"]?([^'\"\s#]+)", content)
    return tuple(
        reference
        for reference in references
        if not reference.startswith(("./", "docker://")) and "@" in reference
    )


def _workflow_permissions_finding(
    snapshot: RepositorySnapshot,
    paths: tuple[str, ...],
    inspected: dict[str, str],
) -> AnalysisFinding:
    workflows = [path for path in paths if GITHUB_WORKFLOW_PATTERN.fullmatch(path)]
    if not workflows:
        return _missing_path_finding(
            snapshot,
            CheckId.WORKFLOW_PERMISSIONS,
            "No GitHub Actions workflow is available for permissions inspection.",
        )

    sampled = [(path, inspected[path]) for path in workflows if path in inspected]
    if not sampled:
        return _finding(
            CheckId.WORKFLOW_PERMISSIONS,
            CheckStatus.PARTIAL,
            "GitHub Actions workflows exist, but their contents were not sampled; permissions are unverified.",
            sources=tuple(workflows[:5]),
        )

    assessments = [
        (path, _workflow_permissions_status(content)) for path, content in sampled
    ]
    if any(status == CheckStatus.FAIL for _, status in assessments):
        status = CheckStatus.FAIL
        evidence = "At least one workflow grants write-all permissions."
    elif any(status == CheckStatus.PARTIAL for _, status in assessments):
        status = CheckStatus.PARTIAL
        evidence = "Workflow permissions include write access that requires manual least-privilege review."
    elif any(status is None for _, status in assessments):
        status = (
            CheckStatus.PARTIAL if len(sampled) < len(workflows) else CheckStatus.FAIL
        )
        evidence = (
            "At least one inspected workflow has no explicit permissions declaration."
        )
    elif len(sampled) < len(workflows):
        status = CheckStatus.PARTIAL
        evidence = "Sampled workflows use explicit restrictive permissions, but inspection was incomplete."
    else:
        status = CheckStatus.PASS
        evidence = (
            "All inspected workflows declare explicit read-only or empty permissions."
        )
    return _finding(
        CheckId.WORKFLOW_PERMISSIONS,
        status,
        evidence,
        sources=tuple(path for path, _ in sampled),
    )


def _workflow_permissions_status(content: str) -> CheckStatus | None:
    if re.search(r"(?im)^\s*permissions\s*:\s*write-all\s*(?:#.*)?$", content):
        return CheckStatus.FAIL
    if re.search(
        r"(?im)^\s*permissions\s*:\s*(?:read-all|\{\s*\})\s*(?:#.*)?$", content
    ):
        return CheckStatus.PASS

    lines = content.splitlines()
    declarations = [
        index
        for index, line in enumerate(lines)
        if re.match(r"^\s*permissions\s*:\s*(?:#.*)?$", line)
    ]
    if not declarations:
        return None
    saw_write = False
    for index in declarations:
        indentation = len(lines[index]) - len(lines[index].lstrip())
        for line in lines[index + 1 :]:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            line_indentation = len(line) - len(line.lstrip())
            if line_indentation <= indentation:
                break
            if re.search(r":\s*write\s*(?:#.*)?$", line, re.I):
                saw_write = True
    return CheckStatus.PARTIAL if saw_write else CheckStatus.PASS


def _ci_badge_finding(readme: str) -> AnalysisFinding:
    targets = _image_targets(readme)
    ci_terms = ("actions/workflows", "circleci", "travis", "azure", "buildkite")
    found = any(
        any(term in target.casefold() for term in ci_terms) for target in targets
    )
    return _finding(
        CheckId.CI_BADGE,
        CheckStatus.PASS if found else CheckStatus.FAIL,
        "README displays a CI status badge." if found else "No CI status badge found.",
        sources=("README.md",) if readme else (),
    )


def _docs_finding(
    snapshot: RepositorySnapshot, paths: tuple[str, ...], readme: str
) -> AnalysisFinding:
    doc_files = [
        path
        for path in paths
        if PurePosixPath(path).suffix in {".adoc", ".md", ".rst"}
        and PurePosixPath(path).parts[0] in {"docs", "documentation"}
    ]
    if doc_files:
        return _finding(
            CheckId.DOCS,
            CheckStatus.PASS,
            f"Found {len(doc_files)} file(s) in a documentation directory.",
            sources=tuple(doc_files[:5]),
        )
    if any(
        path in {"mkdocs.yml", "mkdocs.yaml", "docusaurus.config.js"} for path in paths
    ):
        return _finding(
            CheckId.DOCS,
            CheckStatus.PARTIAL,
            "Found documentation tooling but no documentation files in the returned tree.",
            sources=tuple(
                path
                for path in paths
                if path in {"mkdocs.yml", "mkdocs.yaml", "docusaurus.config.js"}
            ),
        )
    if re.search(r"(?im)^\s{0,3}#{1,6}\s+documentation\b", readme):
        return _finding(
            CheckId.DOCS,
            CheckStatus.PARTIAL,
            "Documentation is included in the README but has no dedicated directory.",
            sources=("README.md",),
        )
    return _missing_path_finding(
        snapshot, CheckId.DOCS, "No extended documentation detected outside the README."
    )


def _governance_file_finding(
    snapshot: RepositorySnapshot,
    paths: tuple[str, ...],
    check_id: CheckId,
    names: set[str],
    label: str,
) -> AnalysisFinding:
    path = next((path for path in paths if PurePosixPath(path).name in names), None)
    if path:
        return _finding(
            check_id,
            CheckStatus.PASS,
            f"Found {path}.",
            sources=(path,),
        )
    return _missing_path_finding(snapshot, check_id, f"Could not find {label}.")


def _security_policy_finding(
    snapshot: RepositorySnapshot,
    paths: tuple[str, ...],
    inspected: dict[str, str],
) -> AnalysisFinding:
    allowed = {"security.md", ".github/security.md", "docs/security.md"}
    path = next((path for path in paths if path in allowed), None)
    if path:
        content = inspected.get(path)
        if content is None:
            return _finding(
                CheckId.SECURITY_POLICY,
                CheckStatus.PARTIAL,
                f"Found {path}, but its reporting guidance was not sampled.",
                sources=(path,),
            )
        normalized = content.strip()
        relevant = bool(
            re.search(r"\b(?:security|vulnerabilit(?:y|ies))\b", content, re.I)
        )
        reporting = bool(
            re.search(
                r"\b(?:report|contact|email|privately|disclosure)\b|mailto:|[\w.+-]+@[\w.-]+",
                content,
                re.I,
            )
        )
        if len(normalized) >= 80 and relevant and reporting:
            status = CheckStatus.PASS
            evidence = f"Verified vulnerability-reporting guidance in {path}."
        elif normalized and (relevant or reporting):
            status = CheckStatus.PARTIAL
            evidence = f"{path} contains limited security-reporting guidance."
        else:
            status = CheckStatus.FAIL
            evidence = f"{path} does not contain recognizable vulnerability-reporting guidance."
        return _finding(
            CheckId.SECURITY_POLICY,
            status,
            evidence,
            sources=(path,),
        )
    return _missing_path_finding(
        snapshot, CheckId.SECURITY_POLICY, "No SECURITY.md policy detected."
    )


def _dependency_updates_finding(
    snapshot: RepositorySnapshot,
    paths: tuple[str, ...],
    inspected: dict[str, str],
) -> AnalysisFinding:
    recognized = {
        ".github/dependabot.yaml",
        ".github/dependabot.yml",
        "renovate.json",
        "renovate.json5",
    }
    path = next((path for path in paths if path in recognized), None)
    if path:
        content = inspected.get(path)
        if content is None:
            return _finding(
                CheckId.DEPENDENCY_UPDATES,
                CheckStatus.PARTIAL,
                f"Found {path}, but its update settings were not sampled.",
                sources=(path,),
            )
        status = _dependency_update_status(path, content)
        if status == CheckStatus.PASS:
            evidence = f"Verified dependency-update settings in {path}."
        elif status == CheckStatus.PARTIAL:
            evidence = (
                f"{path} contains incomplete or unusual dependency-update settings."
            )
        else:
            evidence = (
                f"{path} does not contain a usable dependency-update configuration."
            )
        return _finding(
            CheckId.DEPENDENCY_UPDATES,
            status,
            evidence,
            sources=(path,),
        )
    return _missing_path_finding(
        snapshot,
        CheckId.DEPENDENCY_UPDATES,
        "No Dependabot or Renovate configuration detected.",
    )


def _dependency_update_status(path: str, content: str) -> CheckStatus:
    if PurePosixPath(path).name.startswith("dependabot"):
        required = (
            r"(?m)^\s*version\s*:\s*2\s*$",
            r"(?m)^\s*updates\s*:",
            r"(?m)^\s*-?\s*package-ecosystem\s*:",
            r"(?m)^\s*directory\s*:",
            r"(?m)^\s*schedule\s*:",
        )
        matches = sum(bool(re.search(pattern, content)) for pattern in required)
        if matches == len(required):
            return CheckStatus.PASS
        return CheckStatus.PARTIAL if matches >= 2 else CheckStatus.FAIL

    if path.endswith(".json"):
        try:
            configuration = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return CheckStatus.FAIL
        if not isinstance(configuration, dict) or not configuration:
            return CheckStatus.FAIL
        recognized = {"extends", "packageRules", "enabledManagers", "schedule"}
        return (
            CheckStatus.PASS
            if recognized.intersection(configuration)
            else CheckStatus.PARTIAL
        )
    return (
        CheckStatus.PASS
        if "extends" in content or "packageRules" in content
        else CheckStatus.PARTIAL
    )


def _sensitive_files_finding(
    snapshot: RepositorySnapshot, paths: tuple[str, ...]
) -> AnalysisFinding:
    risky = [path for path in paths if _is_risky_filename(path)]
    if risky:
        shown = ", ".join(risky[:3])
        suffix = " …" if len(risky) > 3 else ""
        return _finding(
            CheckId.NO_SENSITIVE_FILES,
            CheckStatus.FAIL,
            f"Risky filename(s) need manual inspection: {shown}{suffix}. "
            "This does not confirm that a secret is present.",
            sources=tuple(risky[:5]),
        )
    if snapshot.tree_truncated:
        return _finding(
            CheckId.NO_SENSITIVE_FILES,
            CheckStatus.PARTIAL,
            "No risky filenames appeared in the truncated tree; evidence is incomplete.",
        )
    return _finding(
        CheckId.NO_SENSITIVE_FILES,
        CheckStatus.PASS,
        "No common secret-bearing filenames detected. File contents were not scanned.",
    )


def _detected_secrets_finding(snapshot: RepositorySnapshot) -> AnalysisFinding:
    sampled = tuple(snapshot.inspected_files)
    if not sampled:
        return _finding(
            CheckId.NO_DETECTED_SECRETS,
            CheckStatus.PARTIAL,
            "No bounded text-file sample was available for credential-pattern inspection.",
        )

    matches: list[tuple[str, str]] = []
    for file in sampled:
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(file.content):
                matches.append((file.path, label))
    if matches:
        labels = ", ".join(f"{label} pattern in {path}" for path, label in matches[:3])
        return _finding(
            CheckId.NO_DETECTED_SECRETS,
            CheckStatus.FAIL,
            f"Detected {len(matches)} possible high-confidence credential pattern(s): {labels}. Manual verification is required.",
            sources=tuple(dict.fromkeys(path for path, _ in matches)),
        )
    return _finding(
        CheckId.NO_DETECTED_SECRETS,
        CheckStatus.PASS,
        f"No high-confidence credential pattern appeared in {len(sampled)} inspected text file(s). This is not a full secret scan.",
        sources=tuple(file.path for file in sampled[:5]),
    )


def _is_risky_filename(path: str) -> bool:
    name = PurePosixPath(path).name
    safe_env_suffixes = (".example", ".sample", ".template")
    if (
        name == ".env"
        or name.startswith(".env.")
        and not name.endswith(safe_env_suffixes)
    ):
        return True
    if PurePosixPath(path).suffix in {".key", ".p12", ".pem", ".pfx"}:
        return True
    return bool(
        name in {"credentials.json", "id_dsa", "id_rsa"}
        or re.fullmatch(r"service-account.*\.json", name)
    )


def _lock_file_finding(
    snapshot: RepositorySnapshot, paths: tuple[str, ...]
) -> AnalysisFinding:
    lock_file = next(
        (path for path in paths if PurePosixPath(path).name in LOCK_FILES), None
    )
    if lock_file:
        return _finding(
            CheckId.LOCK_FILE,
            CheckStatus.PASS,
            f"Found dependency lock evidence: {lock_file}.",
            sources=(lock_file,),
        )
    requirements = next(
        (
            path
            for path in paths
            if re.fullmatch(r"requirements[^/]*\.txt", PurePosixPath(path).name)
        ),
        None,
    )
    if requirements:
        return _finding(
            CheckId.LOCK_FILE,
            CheckStatus.PARTIAL,
            f"Found {requirements}, but path analysis cannot confirm version pinning.",
            sources=(requirements,),
        )
    return _missing_path_finding(
        snapshot, CheckId.LOCK_FILE, "No dependency lock file detected."
    )


def _missing_path_finding(
    snapshot: RepositorySnapshot, check_id: CheckId, evidence: str
) -> AnalysisFinding:
    if snapshot.tree_truncated:
        return _finding(
            check_id,
            CheckStatus.PARTIAL,
            f"{evidence} The Git tree was truncated, so absence is uncertain.",
        )
    return _finding(check_id, CheckStatus.FAIL, evidence)


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip("/").casefold()


def _finding(
    check_id: CheckId,
    status: CheckStatus,
    evidence: str,
    *,
    sources: tuple[str, ...] = (),
) -> AnalysisFinding:
    return AnalysisFinding(
        check_id=check_id,
        status=status,
        evidence=evidence,
        sources=sources,
    )
