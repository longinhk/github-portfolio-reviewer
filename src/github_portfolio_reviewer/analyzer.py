"""Deterministic repository checks that do not depend on HTTP or the UI."""

import re
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


def analyze_repository(snapshot: RepositorySnapshot) -> tuple[AnalysisFinding, ...]:
    """Analyze a repository snapshot and return one finding for every rubric check."""
    paths = tuple(_normalize_path(path) for path in snapshot.files)
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
        _test_configuration_finding(snapshot, paths),
        _coverage_finding(snapshot, paths, readme),
        _ci_workflow_finding(snapshot, paths),
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
        _security_policy_finding(snapshot, paths),
        _dependency_updates_finding(snapshot, paths),
        _sensitive_files_finding(snapshot, paths),
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
        return _finding(CheckId.README_EXISTS, CheckStatus.PASS, "README detected.")
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
        return _finding(check_id, CheckStatus.PASS, f"Found a {label} heading.")
    lowered = readme.casefold()
    if lowered and any(term in lowered for term in terms):
        return _finding(
            check_id,
            CheckStatus.PARTIAL,
            f"README mentions {label}, but has no clearly named section.",
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
        )
    return _finding(
        CheckId.SOURCE_LAYOUT,
        CheckStatus.PARTIAL,
        "Source files exist, but only at the repository root or an unconventional path.",
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
        return _finding(check_id, CheckStatus.PASS, f"Found {passing}.")
    partial = next((path for path in paths if partial_match(path)), None)
    if partial:
        return _finding(check_id, CheckStatus.PARTIAL, f"Found nested file {partial}.")
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
    )


def _is_test_file(path: str) -> bool:
    pure_path = PurePosixPath(path)
    name = pure_path.name
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
    return _finding(CheckId.TEST_FILES, status, evidence)


def _test_configuration_finding(
    snapshot: RepositorySnapshot, paths: tuple[str, ...]
) -> AnalysisFinding:
    config = next(
        (
            path
            for path in paths
            if any(
                pattern.fullmatch(PurePosixPath(path).name)
                for pattern in TEST_CONFIG_PATTERNS
            )
        ),
        None,
    )
    if config:
        return _finding(
            CheckId.TEST_CONFIGURATION,
            CheckStatus.PASS,
            f"Found explicit test configuration: {config}.",
        )
    if "pyproject.toml" in paths or "package.json" in paths:
        return _finding(
            CheckId.TEST_CONFIGURATION,
            CheckStatus.PARTIAL,
            "A general project manifest may contain test settings, but its content was not inspected.",
        )
    return _missing_path_finding(
        snapshot, CheckId.TEST_CONFIGURATION, "No explicit test configuration found."
    )


def _coverage_finding(
    snapshot: RepositorySnapshot, paths: tuple[str, ...], readme: str
) -> AnalysisFinding:
    config = next(
        (
            path
            for path in paths
            if PurePosixPath(path).name in COVERAGE_FILES
            or path.startswith(".github/workflows/")
            and "coverage" in path
        ),
        None,
    )
    if config:
        return _finding(
            CheckId.COVERAGE, CheckStatus.PASS, f"Found coverage evidence: {config}."
        )
    if re.search(r"\b(?:coverage|codecov|coveralls)\b", readme, re.I):
        return _finding(
            CheckId.COVERAGE,
            CheckStatus.PARTIAL,
            "README mentions coverage, but no dedicated configuration file was detected.",
        )
    return _missing_path_finding(
        snapshot, CheckId.COVERAGE, "No coverage configuration or badge detected."
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
        )
    return _missing_path_finding(
        snapshot, CheckId.CI_WORKFLOW, "No recognized CI configuration detected."
    )


def _is_ci_file(path: str) -> bool:
    return bool(
        re.fullmatch(r"\.github/workflows/.+\.ya?ml", path)
        or path
        in {
            ".circleci/config.yml",
            ".travis.yml",
            "azure-pipelines.yml",
            "jenkinsfile",
        }
    )


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
        )
    if any(
        path in {"mkdocs.yml", "mkdocs.yaml", "docusaurus.config.js"} for path in paths
    ):
        return _finding(
            CheckId.DOCS,
            CheckStatus.PARTIAL,
            "Found documentation tooling but no documentation files in the returned tree.",
        )
    if re.search(r"(?im)^\s{0,3}#{1,6}\s+documentation\b", readme):
        return _finding(
            CheckId.DOCS,
            CheckStatus.PARTIAL,
            "Documentation is included in the README but has no dedicated directory.",
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
        return _finding(check_id, CheckStatus.PASS, f"Found {path}.")
    return _missing_path_finding(snapshot, check_id, f"Could not find {label}.")


def _security_policy_finding(
    snapshot: RepositorySnapshot, paths: tuple[str, ...]
) -> AnalysisFinding:
    allowed = {"security.md", ".github/security.md", "docs/security.md"}
    path = next((path for path in paths if path in allowed), None)
    if path:
        return _finding(CheckId.SECURITY_POLICY, CheckStatus.PASS, f"Found {path}.")
    return _missing_path_finding(
        snapshot, CheckId.SECURITY_POLICY, "No SECURITY.md policy detected."
    )


def _dependency_updates_finding(
    snapshot: RepositorySnapshot, paths: tuple[str, ...]
) -> AnalysisFinding:
    recognized = {
        ".github/dependabot.yaml",
        ".github/dependabot.yml",
        "renovate.json",
        "renovate.json5",
    }
    path = next((path for path in paths if path in recognized), None)
    if path:
        return _finding(
            CheckId.DEPENDENCY_UPDATES,
            CheckStatus.PASS,
            f"Found dependency-update configuration: {path}.",
        )
    return _missing_path_finding(
        snapshot,
        CheckId.DEPENDENCY_UPDATES,
        "No Dependabot or Renovate configuration detected.",
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


def _finding(check_id: CheckId, status: CheckStatus, evidence: str) -> AnalysisFinding:
    return AnalysisFinding(check_id=check_id, status=status, evidence=evidence)
