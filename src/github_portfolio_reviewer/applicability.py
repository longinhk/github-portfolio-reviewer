"""Classify whether the software-project rubric fits repository evidence."""

import re
from pathlib import PurePosixPath

from github_portfolio_reviewer.models import (
    RepositoryKind,
    RepositorySnapshot,
    RubricAssessment,
    RubricFit,
)

MANIFEST_NAMES = {
    "build.gradle",
    "build.gradle.kts",
    "cargo.toml",
    "composer.json",
    "gemfile",
    "go.mod",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
}
CODE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".go",
    ".h",
    ".hpp",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".ipynb",
}
CONTENT_SUFFIXES = {".adoc", ".ipynb", ".md", ".mdx", ".pdf", ".ppt", ".pptx", ".rst"}
CONTENT_TERMS = {
    "awesome",
    "book",
    "books",
    "cheatsheet",
    "course",
    "curriculum",
    "knowledge base",
    "lecture",
    "lectures",
    "notes",
    "reading list",
    "resources",
    "skills",
    "slides",
}
SUPPORT_DIRECTORIES = {
    ".git",
    ".github",
    "doc",
    "docs",
    "documentation",
    "example",
    "examples",
    "sample",
    "samples",
    "demo",
    "demos",
    "build",
    "dist",
    "node_modules",
    "fixture",
    "fixtures",
    "test",
    "tests",
    "vendor",
}
TEST_DIRECTORIES = {"spec", "specs", "test", "tests"}


def assess_rubric_fit(snapshot: RepositorySnapshot) -> RubricAssessment:
    """Return a conservative repository shape and software-rubric fit."""
    if snapshot.tree_truncated:
        return RubricAssessment(
            repository_kind=RepositoryKind.UNKNOWN,
            fit=RubricFit.MEDIUM,
            explanation=(
                "GitHub truncated the file tree, so the repository type cannot be "
                "classified safely. Interpret the whole-repository score with caution."
            ),
            signals=("Truncated Git tree",),
        )

    paths = tuple(path.casefold().strip("/") for path in snapshot.files)
    pure_paths = tuple(PurePosixPath(path) for path in paths)
    root_manifests = tuple(
        path
        for path in pure_paths
        if len(path.parts) == 1 and path.name in MANIFEST_NAMES
    )
    manifest_roots = {
        "." if len(path.parts) == 1 else path.parent.as_posix()
        for path in pure_paths
        if path.name in MANIFEST_NAMES
        and not set(path.parts[:-1]) & SUPPORT_DIRECTORIES
    }
    test_files = tuple(path for path in pure_paths if _is_test_file(path))
    source_files = tuple(path for path in pure_paths if _is_source_file(path))
    content_files = tuple(path for path in pure_paths if _is_content_file(path))
    project_roots = {
        root
        for root in manifest_roots
        if root == "." or any(_path_is_below(source, root) for source in source_files)
    }

    descriptor = " ".join(
        (
            snapshot.reference.name.casefold(),
            (snapshot.description or "").casefold(),
            " ".join(topic.casefold() for topic in snapshot.topics),
        )
    )
    normalized_descriptor = " ".join(re.findall(r"[a-z0-9]+", descriptor))
    content_hint = any(
        re.search(rf"(?:^| ){re.escape(term)}(?: |$)", normalized_descriptor)
        for term in CONTENT_TERMS
    )
    content_dominant = len(content_files) >= max(3, len(source_files) * 3)

    if content_hint and content_dominant and len(test_files) == 0:
        return RubricAssessment(
            repository_kind=RepositoryKind.CONTENT,
            fit=RubricFit.LOW,
            explanation=(
                "This appears to be educational or reference content, so the "
                "software-project score would be misleading."
            ),
            signals=(
                "Content-oriented repository name, description, or topics",
                f"{len(content_files)} content file(s) and {len(test_files)} test file(s)",
            ),
        )

    if len(project_roots) >= 2:
        return RubricAssessment(
            repository_kind=RepositoryKind.MONOREPO,
            fit=RubricFit.MEDIUM,
            explanation=(
                "Multiple manifest-backed projects were detected. The score covers "
                "the whole default branch, not an individual subproject."
            ),
            signals=(
                f"Manifests identify {len(project_roots)} distinct project roots",
            ),
        )

    if root_manifests and (source_files or test_files):
        return RubricAssessment(
            repository_kind=RepositoryKind.SOFTWARE,
            fit=RubricFit.HIGH,
            explanation=(
                "A root manifest and conventional source or test files match the "
                "software-project rubric."
            ),
            signals=(
                f"{len(root_manifests)} root manifest(s)",
                f"{len(source_files)} source file(s) and {len(test_files)} test file(s)",
            ),
        )

    if source_files and test_files:
        return RubricAssessment(
            repository_kind=RepositoryKind.SOFTWARE,
            fit=RubricFit.HIGH,
            explanation=(
                "Conventional source and test files match the software-project rubric."
            ),
            signals=(
                f"{len(source_files)} source file(s) and {len(test_files)} test file(s)",
            ),
        )

    return RubricAssessment(
        repository_kind=RepositoryKind.UNKNOWN,
        fit=RubricFit.MEDIUM,
        explanation=(
            "The repository shape is ambiguous. Interpret the software-project score "
            "with caution."
        ),
        signals=(
            f"{len(root_manifests)} root manifest(s)",
            f"{len(source_files)} source file(s) and {len(test_files)} test file(s)",
        ),
    )


def _is_test_file(path: PurePosixPath) -> bool:
    """Return whether a path follows a common automated-test convention."""
    parts = set(path.parts[:-1])
    name = path.name
    return (
        bool(parts & TEST_DIRECTORIES)
        or name.startswith("test_")
        or name.endswith(("_test.py", ".spec.js", ".spec.ts", ".test.js", ".test.ts"))
    )


def _is_source_file(path: PurePosixPath) -> bool:
    """Return whether a path looks like production source rather than support content."""
    if path.suffix not in CODE_SUFFIXES or _is_test_file(path):
        return False
    return not bool(set(path.parts[:-1]) & SUPPORT_DIRECTORIES)


def _is_content_file(path: PurePosixPath) -> bool:
    """Return whether a path is primarily documentation, learning, or reference content."""
    return path.suffix in CONTENT_SUFFIXES or path.name == "skill.md"


def _path_is_below(path: PurePosixPath, root: str) -> bool:
    """Return whether a source path belongs to a manifest-backed project root."""
    return path.as_posix().startswith(f"{root}/")
