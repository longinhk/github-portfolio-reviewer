"""Deterministic repository checks that do not depend on HTTP or the UI."""

import ast
import json
import re
import tomllib
from collections import Counter
from collections.abc import Callable
from pathlib import PurePosixPath

from github_portfolio_reviewer.conventions import (
    GITHUB_WORKFLOW_PATTERN,
    is_ci_file,
)
from github_portfolio_reviewer.models import (
    AnalysisFinding,
    CheckId,
    CheckStatus,
    EvidenceConfidence,
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
    "doc",
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
DOCUMENTATION_DIRECTORIES = {"doc", "docs", "documentation"}
DOCUMENTATION_SUFFIXES = {".adoc", ".ipynb", ".md", ".rst", ".txt"}
DOCUMENTATION_TOOLING = {
    ".readthedocs.yaml",
    ".readthedocs.yml",
    "doc/conf.py",
    "docs/conf.py",
    "documentation/conf.py",
    "docusaurus.config.cjs",
    "docusaurus.config.js",
    "docusaurus.config.mjs",
    "docusaurus.config.ts",
    "mkdocs.yaml",
    "mkdocs.yml",
}
CHANGELOG_NAMES = {
    "changelog",
    "changes",
    "history",
    "news",
    "release-notes",
    "release_notes",
    "releases",
}
CHANGELOG_SUFFIXES = {"", ".adoc", ".md", ".rst", ".txt"}
CHANGELOG_DIRECTORIES = {
    "changelog",
    "changes",
    "news",
    "release-notes",
    "release_notes",
    "releases",
    "whatsnew",
}
FIXTURE_DIRECTORIES = {
    "__fixtures__",
    "example",
    "examples",
    "fixture",
    "fixtures",
    "sample",
    "samples",
    "spec",
    "specs",
    "test",
    "test-data",
    "test_data",
    "testdata",
    "testing",
    "tests",
}
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
    readme_source = snapshot.readme_path or "README.md"
    production_files = _production_source_files(paths)

    findings = (
        _description_finding(snapshot),
        _topics_finding(snapshot),
        _license_finding(snapshot, paths),
        _active_finding(snapshot),
        _readme_exists_finding(readme, readme_source),
        _readme_detail_finding(readme, readme_source),
        _readme_section_finding(
            CheckId.README_INSTALLATION,
            readme,
            ("installation", "install", "setup", "prerequisites", "getting started"),
            "installation or setup",
            readme_source,
        ),
        _readme_section_finding(
            CheckId.README_USAGE,
            readme,
            ("usage", "how to use", "quickstart", "example", "examples"),
            "usage or examples",
            readme_source,
        ),
        _readme_badges_finding(readme, readme_source),
        _readme_visuals_finding(readme, readme_source),
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
        _coverage_finding(snapshot, paths, inspected, readme, readme_source),
        _ci_workflow_finding(snapshot, paths, inspected),
        _actions_pinned_finding(snapshot, paths, inspected),
        _workflow_permissions_finding(snapshot, paths, inspected),
        _ci_badge_finding(readme, readme_source),
        _docs_finding(snapshot, paths, readme, readme_source),
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
        _changelog_finding(snapshot, paths),
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


def _readme_exists_finding(readme: str, source: str) -> AnalysisFinding:
    if readme.strip():
        return _finding(
            CheckId.README_EXISTS,
            CheckStatus.PASS,
            "README detected.",
            sources=(source,),
        )
    return _finding(CheckId.README_EXISTS, CheckStatus.FAIL, "No README detected.")


def _readme_detail_finding(readme: str, source: str) -> AnalysisFinding:
    prose = re.sub(r"(?s)```.*?```|~~~.*?~~~", " ", readme)
    words = re.findall(r"\b[\w'-]+\b", prose)
    word_count = len(words)
    unique_words = len({word.casefold() for word in words})
    sufficiently_varied = unique_words >= 40 or (
        word_count > 0 and unique_words / word_count >= 0.2
    )
    if word_count >= 200 and sufficiently_varied:
        status = CheckStatus.PASS
    elif word_count >= 50 and unique_words >= 15:
        status = CheckStatus.PARTIAL
    else:
        status = CheckStatus.FAIL
    return _finding(
        CheckId.README_DETAIL,
        status,
        f"README contains approximately {word_count} words.",
        sources=(source,) if readme else (),
    )


def _readme_section_finding(
    check_id: CheckId,
    readme: str,
    terms: tuple[str, ...],
    label: str,
    source: str,
) -> AnalysisFinding:
    headings = [
        match.casefold()
        for match in re.findall(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", readme)
    ]
    matching_heading = next(
        (heading for heading in headings if any(term in heading for term in terms)),
        None,
    )
    if matching_heading is not None and _readme_section_has_content(
        readme, matching_heading
    ):
        return _finding(
            check_id,
            CheckStatus.PASS,
            f"Found a {label} heading.",
            sources=(source,),
        )
    if matching_heading is not None:
        return _finding(
            check_id,
            CheckStatus.PARTIAL,
            f"README has a {label} heading, but the section contains little guidance.",
            sources=(source,),
        )
    lowered = readme.casefold()
    if lowered and any(term in lowered for term in terms):
        return _finding(
            check_id,
            CheckStatus.PARTIAL,
            f"README mentions {label}, but has no clearly named section.",
            sources=(source,),
        )
    return _finding(check_id, CheckStatus.FAIL, f"README has no {label} guidance.")


def _readme_section_has_content(readme: str, heading: str) -> bool:
    """Return whether a named Markdown section contains useful body content."""
    pattern = re.compile(
        rf"(?ims)^\s{{0,3}}#{{1,6}}\s+{re.escape(heading)}\s*#*\s*$"
        r"(?P<body>.*?)(?=^\s{0,3}#{1,6}\s+|\Z)"
    )
    match = pattern.search(readme)
    if match is None:
        return False
    body = match.group("body")
    words = re.findall(r"\b[\w'-]+\b", body)
    has_command = bool(re.search(r"(?m)^\s*(?:```|~~~|\$\s|pip\s|python\s)", body))
    return len(words) >= 5 or has_command


def _image_targets(readme: str) -> tuple[str, ...]:
    markdown = re.findall(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)", readme)
    html = re.findall(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", readme, re.I)
    return tuple(markdown + html)


def _readme_badges_finding(readme: str, source: str) -> AnalysisFinding:
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
        sources=(source,) if readme else (),
    )


def _readme_visuals_finding(readme: str, source: str) -> AnalysisFinding:
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
        sources=(source,) if readme else (),
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
        confidence=(
            EvidenceConfidence.PROVISIONAL
            if snapshot.tree_truncated and not test_files
            else EvidenceConfidence.VERIFIED
        ),
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
            confidence=EvidenceConfidence.UNVERIFIED,
        )

    test_cases = 0
    assertion_signals = 0
    assertion_bearing_cases = 0
    parse_errors = 0
    for path, content in sampled:
        cases, assertions, asserted_cases, parsed = _test_metrics(path, content)
        test_cases += cases
        assertion_signals += assertions
        assertion_bearing_cases += asserted_cases
        parse_errors += not parsed

    incomplete = len(sampled) < len(test_paths)
    if test_cases >= 2 and assertion_bearing_cases >= 2:
        status = CheckStatus.PASS
    elif test_cases or assertion_signals or parse_errors or incomplete:
        status = CheckStatus.PARTIAL
    else:
        status = CheckStatus.FAIL

    evidence = (
        f"Sampled {len(sampled)} of {len(test_paths)} test file(s); found "
        f"{test_cases} implemented test case(s), {assertion_bearing_cases} with "
        f"assertion evidence, and {assertion_signals} assertion signal(s)."
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
        confidence=(
            EvidenceConfidence.SAMPLED
            if incomplete or parse_errors
            else EvidenceConfidence.VERIFIED
        ),
    )


def _test_metrics(path: str, content: str) -> tuple[int, int, int, bool]:
    """Return deterministic test and assertion metrics for sampled text."""
    if PurePosixPath(path).suffix == ".py":
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError):
            return 0, 0, 0, False

        test_nodes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ]
        implemented_nodes = [
            node for node in test_nodes if not _is_placeholder_test(node)
        ]
        implemented = len(implemented_nodes)
        assertions = sum(_is_assertion_signal(node) for node in ast.walk(tree))
        asserted_cases = sum(
            any(_is_assertion_signal(child) for child in ast.walk(node))
            for node in implemented_nodes
        )
        return implemented, assertions, asserted_cases, True

    test_cases = len(re.findall(r"(?m)\b(?:it|test)\s*\(", content))
    assertions = len(re.findall(r"(?m)\b(?:expect|assert)\s*\(?", content))
    return test_cases, assertions, min(test_cases, assertions), True


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
            confidence=(
                EvidenceConfidence.UNVERIFIED
                if not sampled
                else EvidenceConfidence.SAMPLED
            ),
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
            confidence=EvidenceConfidence.UNVERIFIED,
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
    readme_source: str,
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
            sources=(readme_source,),
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
            confidence=(
                EvidenceConfidence.UNVERIFIED
                if not sampled
                else EvidenceConfidence.SAMPLED
            ),
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
    snapshot: RepositorySnapshot,
    paths: tuple[str, ...],
    inspected: dict[str, str],
) -> AnalysisFinding:
    ci_files = tuple(path for path in paths if is_ci_file(path))
    inspected_ci = tuple(
        (path, inspected[path]) for path in ci_files if path in inspected
    )
    configured_file = next(
        (path for path, content in inspected_ci if _has_ci_structure(path, content)),
        None,
    )
    if configured_file is not None:
        return _finding(
            CheckId.CI_WORKFLOW,
            CheckStatus.PASS,
            f"Verified executable CI structure in {configured_file}; execution status was not checked.",
            sources=(configured_file,),
        )
    if inspected_ci:
        inspected_paths = tuple(path for path, _ in inspected_ci)
        return _finding(
            CheckId.CI_WORKFLOW,
            CheckStatus.PARTIAL,
            (
                f"Inspected {len(inspected_paths)} CI configuration(s), but none "
                "contained the required provider structure and execution step."
            ),
            sources=inspected_paths,
        )
    if ci_files:
        return _finding(
            CheckId.CI_WORKFLOW,
            CheckStatus.PARTIAL,
            f"Detected CI configuration at {ci_files[0]}, but its contents were not inspected.",
            sources=(ci_files[0],),
            confidence=EvidenceConfidence.UNVERIFIED,
        )
    return _missing_path_finding(
        snapshot, CheckId.CI_WORKFLOW, "No recognized CI configuration detected."
    )


def _has_ci_structure(path: str, content: str) -> bool:
    """Validate minimal executable structure for one supported CI provider."""
    if GITHUB_WORKFLOW_PATTERN.fullmatch(path):
        return bool(
            re.search(r"(?m)^\s*['\"]?on['\"]?\s*:", content)
            and re.search(r"(?m)^\s*jobs\s*:", content)
            and re.search(r"(?m)^\s*-?\s*(?:uses|run)\s*:", content)
        )
    if path == ".circleci/config.yml":
        return bool(
            re.search(r"(?m)^\s*version\s*:", content)
            and re.search(r"(?m)^\s*jobs\s*:", content)
            and re.search(r"(?m)^\s*steps\s*:", content)
            and re.search(r"(?m)^\s*-?\s*run\s*:", content)
        )
    if path == ".travis.yml":
        return bool(
            re.search(r"(?m)^\s*(?:language|jobs|stages|os|dist)\s*:", content)
            and re.search(r"(?m)^\s*script\s*:", content)
        )
    if path == ".gitlab-ci.yml":
        return bool(
            re.search(r"(?m)^[A-Za-z0-9_.-]+\s*:\s*$", content)
            and re.search(r"(?m)^\s*script\s*:", content)
        )
    if path == "azure-pipelines.yml":
        return bool(
            re.search(r"(?m)^\s*(?:stages|jobs|steps)\s*:", content)
            and re.search(
                r"(?m)^\s*-?\s*(?:script|task|bash|powershell|pwsh)\s*:",
                content,
            )
        )
    if path == "jenkinsfile":
        has_execution_step = bool(
            re.search(
                r"(?m)^\s*(?:sh|bat|powershell|pwsh|echo)\s+(?:['\"]|\()",
                content,
            )
        )
        declarative = bool(
            re.search(r"(?m)^\s*pipeline\s*\{", content)
            and re.search(r"(?m)^\s*agent(?:\s+\w+|\s*\{)", content)
            and re.search(r"(?m)^\s*stages?\s*\{", content)
            and re.search(r"(?m)^\s*steps?\s*\{", content)
        )
        scripted = bool(re.search(r"(?m)^\s*node(?:\s*\([^)]*\))?\s*\{", content))
        return has_execution_step and (declarative or scripted)
    return False


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
            confidence=EvidenceConfidence.UNVERIFIED,
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
        confidence=(
            EvidenceConfidence.SAMPLED if incomplete else EvidenceConfidence.VERIFIED
        ),
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
            confidence=EvidenceConfidence.UNVERIFIED,
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
        confidence=(
            EvidenceConfidence.VERIFIED
            if any(
                assessment in {CheckStatus.FAIL, CheckStatus.PARTIAL}
                for _, assessment in assessments
            )
            else EvidenceConfidence.SAMPLED
            if len(sampled) < len(workflows)
            else EvidenceConfidence.VERIFIED
        ),
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


def _ci_badge_finding(readme: str, source: str) -> AnalysisFinding:
    targets = _image_targets(readme)
    ci_terms = ("actions/workflows", "circleci", "travis", "azure", "buildkite")
    found = any(
        any(term in target.casefold() for term in ci_terms) for target in targets
    )
    return _finding(
        CheckId.CI_BADGE,
        CheckStatus.PASS if found else CheckStatus.FAIL,
        "README displays a CI status badge." if found else "No CI status badge found.",
        sources=(source,) if readme else (),
    )


def _docs_finding(
    snapshot: RepositorySnapshot,
    paths: tuple[str, ...],
    readme: str,
    readme_source: str,
) -> AnalysisFinding:
    doc_files = [
        path
        for path in paths
        if PurePosixPath(path).suffix in DOCUMENTATION_SUFFIXES
        and PurePosixPath(path).parts[0] in DOCUMENTATION_DIRECTORIES
    ]
    if doc_files:
        return _finding(
            CheckId.DOCS,
            CheckStatus.PASS,
            f"Found {len(doc_files)} file(s) in a documentation directory.",
            sources=tuple(doc_files[:5]),
        )
    tooling = [path for path in paths if path in DOCUMENTATION_TOOLING]
    if tooling:
        return _finding(
            CheckId.DOCS,
            CheckStatus.PARTIAL,
            "Found documentation tooling but no documentation files in the returned tree.",
            sources=tuple(tooling[:5]),
        )
    external_links = _external_documentation_links(readme)
    if external_links:
        return _finding(
            CheckId.DOCS,
            CheckStatus.PARTIAL,
            "README links to external documentation, but that content was not inspected.",
            sources=(readme_source,),
            confidence=EvidenceConfidence.UNVERIFIED,
        )
    if re.search(r"(?im)^\s{0,3}#{1,6}\s+documentation\b", readme):
        return _finding(
            CheckId.DOCS,
            CheckStatus.PARTIAL,
            "Documentation is included in the README but has no dedicated directory.",
            sources=(readme_source,),
        )
    return _missing_path_finding(
        snapshot, CheckId.DOCS, "No extended documentation detected outside the README."
    )


def _external_documentation_links(readme: str) -> tuple[str, ...]:
    """Return explicit external documentation targets linked from the README."""
    markdown_links = re.findall(
        r"(?<!!)\[([^\]]+)\]\((https?://[^)\s]+)(?:\s+[^)]*)?\)",
        readme,
        re.I,
    )
    html_links = re.findall(
        r"<a\b[^>]*\bhref=[\"'](https?://[^\"']+)[\"'][^>]*>(.*?)</a>",
        readme,
        re.I | re.S,
    )
    candidates = [(label, target) for label, target in markdown_links] + [
        (re.sub(r"<[^>]+>", " ", label), target) for target, label in html_links
    ]
    label_terms = ("api reference", "documentation", "docs", "guide", "manual")
    return tuple(
        target
        for label, target in candidates
        if any(term in label.casefold() for term in label_terms)
        or re.search(
            r"(?i)://docs\.|readthedocs\.(?:io|org)(?:/|$)|/docs(?:/|$)",
            target,
        )
    )


def _changelog_finding(
    snapshot: RepositorySnapshot, paths: tuple[str, ...]
) -> AnalysisFinding:
    """Recognize common root and documentation-directory release histories."""
    matches: list[str] = []
    for path in paths:
        pure_path = PurePosixPath(path)
        if len(pure_path.parts) == 1:
            stem = pure_path.stem if pure_path.suffix else pure_path.name
            if stem in CHANGELOG_NAMES and pure_path.suffix in CHANGELOG_SUFFIXES:
                matches.append(path)
                continue
        if (
            pure_path.parts[0] in DOCUMENTATION_DIRECTORIES
            and (
                set(pure_path.parts[1:-1]) & CHANGELOG_DIRECTORIES
                or pure_path.stem in CHANGELOG_DIRECTORIES
            )
            and pure_path.suffix in DOCUMENTATION_SUFFIXES
        ):
            matches.append(path)

    if matches:
        return _finding(
            CheckId.CHANGELOG,
            CheckStatus.PASS,
            f"Found release history at {matches[0]}.",
            sources=tuple(matches[:5]),
        )
    return _missing_path_finding(
        snapshot, CheckId.CHANGELOG, "Could not find a changelog or release history."
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
    if snapshot.tree_truncated:
        return _missing_path_finding(snapshot, check_id, f"Could not detect {label}.")
    return _finding(
        check_id,
        CheckStatus.PARTIAL,
        f"No {label} was detected in this repository tree. GitHub owner-level "
        "default community files are not inspected.",
        confidence=EvidenceConfidence.UNVERIFIED,
    )


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
                confidence=EvidenceConfidence.UNVERIFIED,
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
    if snapshot.tree_truncated:
        return _missing_path_finding(
            snapshot, CheckId.SECURITY_POLICY, "No SECURITY.md policy detected."
        )
    return _finding(
        CheckId.SECURITY_POLICY,
        CheckStatus.PARTIAL,
        "No SECURITY.md policy was detected in this repository tree. GitHub "
        "owner-level default community files are not inspected.",
        confidence=EvidenceConfidence.UNVERIFIED,
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
                confidence=EvidenceConfidence.UNVERIFIED,
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
            confidence=EvidenceConfidence.PROVISIONAL,
        )
    advisory = [path for path in paths if _is_advisory_sensitive_filename(path)]
    if advisory:
        return _finding(
            CheckId.NO_SENSITIVE_FILES,
            CheckStatus.PASS,
            "No likely production secret-bearing filenames detected. "
            f"Found {len(advisory)} certificate or test-fixture filename(s) that "
            "still merit manual review.",
            sources=tuple(advisory[:5]),
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
            confidence=EvidenceConfidence.UNVERIFIED,
        )

    matches: list[tuple[str, str]] = []
    fixture_matches: list[tuple[str, str]] = []
    for file in sampled:
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(file.content):
                target = fixture_matches if _is_fixture_path(file.path) else matches
                target.append((file.path, label))
    if matches:
        labels = ", ".join(f"{label} pattern in {path}" for path, label in matches[:3])
        return _finding(
            CheckId.NO_DETECTED_SECRETS,
            CheckStatus.FAIL,
            f"Detected {len(matches)} possible high-confidence credential pattern(s): {labels}. Manual verification is required.",
            sources=tuple(dict.fromkeys(path for path, _ in matches)),
        )
    if fixture_matches:
        labels = ", ".join(
            f"{label} pattern in {path}" for path, label in fixture_matches[:3]
        )
        return _finding(
            CheckId.NO_DETECTED_SECRETS,
            CheckStatus.PARTIAL,
            f"Credential-like patterns appeared only in test or example fixtures: "
            f"{labels}. Confirm that they are intentionally fake.",
            sources=tuple(dict.fromkeys(path for path, _ in fixture_matches)),
        )
    return _finding(
        CheckId.NO_DETECTED_SECRETS,
        CheckStatus.PARTIAL,
        f"No high-confidence credential pattern appeared in the bounded sample of {len(sampled)} text file(s). Uninspected files and Git history remain unknown.",
        sources=tuple(file.path for file in sampled[:5]),
        confidence=EvidenceConfidence.SAMPLED,
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
    if name in {"credentials.json", "id_dsa", "id_rsa"} or re.fullmatch(
        r"service-account.*\.json", name
    ):
        return True
    if _is_fixture_path(path):
        return False
    suffix = PurePosixPath(path).suffix
    if suffix in {".key", ".p12", ".pfx"}:
        return True
    if suffix == ".pem" and re.search(r"(?:^|[-_.])public[-_.]?key(?:[-_.]|$)", name):
        return False
    return bool(
        suffix == ".pem"
        and re.search(r"(?:^|[-_.])(?:credential|key|private|secret)(?:[-_.]|$)", name)
    )


def _is_advisory_sensitive_filename(path: str) -> bool:
    """Return whether a certificate/key-like path deserves review, not deduction."""
    suffix = PurePosixPath(path).suffix
    return suffix in {".key", ".p12", ".pem", ".pfx"} and not _is_risky_filename(path)


def _is_fixture_path(path: str) -> bool:
    """Return whether a path is clearly scoped to tests, examples, or fixtures."""
    return bool(set(PurePosixPath(path).parts[:-1]) & FIXTURE_DIRECTORIES)


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
            confidence=EvidenceConfidence.PROVISIONAL,
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
    confidence: EvidenceConfidence = EvidenceConfidence.VERIFIED,
) -> AnalysisFinding:
    return AnalysisFinding(
        check_id=check_id,
        status=status,
        evidence=evidence,
        sources=sources,
        confidence=confidence,
    )
