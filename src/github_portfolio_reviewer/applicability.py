"""Classify whether the software-project rubric fits repository evidence."""

import re
from pathlib import PurePosixPath

from github_portfolio_reviewer.conventions import follows_test_file_convention
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
NARRATIVE_CONTENT_SUFFIXES = CONTENT_SUFFIXES - {".ipynb"}
CONTENT_TERMS = {
    "awesome",
    "book",
    "books",
    "cheatsheet",
    "course",
    "curriculum",
    "guide",
    "guides",
    "interview",
    "knowledge base",
    "learn",
    "learning",
    "lecture",
    "lectures",
    "list",
    "lists",
    "notes",
    "reading list",
    "reference",
    "references",
    "resources",
    "skills",
    "slides",
    "study plan",
    "tutorial",
    "tutorials",
}
CONTENT_MAINTENANCE_DIRECTORIES = {"script", "scripts", "tool", "tools"}
CONTENT_SITE_DIRECTORIES = {"site", "website"}
CURATED_COLLECTION_PHRASES = {
    "awesome list",
    "collective list",
    "curated list",
    "definitive list",
    "list of",
}
LEARNING_SEQUENCE_PATTERN = re.compile(
    r"(?:day|week|lesson|chapter)[-_ ]*0*\d+(?:[-_ ]+0*\d+)?"
)
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
    "archive",
    "archived",
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
NON_PRODUCT_TEST_DIRECTORIES = SUPPORT_DIRECTORIES - TEST_DIRECTORIES


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
    narrative_files = tuple(
        path for path in pure_paths if _is_narrative_content_file(path)
    )
    skill_files = tuple(path for path in pure_paths if path.name == "skill.md")
    example_source_files = tuple(
        path for path in source_files if path.suffix != ".ipynb"
    )
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
    curated_collection_hint = any(
        re.search(rf"(?:^| ){re.escape(phrase)}(?: |$)", normalized_descriptor)
        for phrase in CURATED_COLLECTION_PHRASES
    )
    content_dominant = len(content_files) >= max(3, len(source_files) * 3)
    narrative_only = bool(
        len(narrative_files) >= 3 and not source_files and not test_files
    )
    hinted_narrative_only = bool(
        content_hint and narrative_files and not source_files and not test_files
    )
    content_with_examples = bool(
        content_hint
        and len(narrative_files) >= 3
        and not root_manifests
        and not test_files
        and example_source_files
    )
    content_with_tooling = bool(
        content_hint
        and narrative_files
        and _software_is_confined_to_content_tooling(
            source_files,
            test_files,
            narrative_count=len(narrative_files),
        )
    )
    skill_collection = bool(
        len(skill_files) >= 3
        and len(skill_files) >= len(source_files)
        and not test_files
    )
    curated_collection = bool(
        curated_collection_hint
        and len(narrative_files) >= 3
        and len(narrative_files) >= len(source_files)
    )
    structured_learning_collection = _is_structured_learning_collection(
        narrative_files,
        source_files,
        root_manifests=root_manifests,
    )

    if (
        (
            content_hint
            and content_dominant
            and not test_files
            and (not root_manifests or not source_files)
        )
        or narrative_only
        or hinted_narrative_only
        or content_with_examples
        or content_with_tooling
        or skill_collection
        or curated_collection
        or structured_learning_collection
    ):
        if content_with_tooling:
            classification_signal = (
                "Content-oriented metadata; software files are confined to supporting "
                "tooling directories"
            )
        elif skill_collection:
            classification_signal = (
                "Multiple SKILL.md documents identify a reusable skill collection"
            )
        elif curated_collection:
            classification_signal = (
                "Curated-list metadata is supported by a narrative-dominant tree"
            )
        elif structured_learning_collection:
            classification_signal = (
                "Numbered learning sections contain course material and example code"
            )
        elif content_with_examples and source_files:
            classification_signal = (
                "Content-oriented metadata with untested example source files"
            )
        elif content_hint:
            classification_signal = (
                "Content-oriented repository name, description, or topics"
            )
        else:
            classification_signal = "Narrative documents dominate the tree; no source or test files detected"
        return RubricAssessment(
            repository_kind=RepositoryKind.CONTENT,
            fit=RubricFit.LOW,
            explanation=(
                "This appears to be educational or reference content, so the "
                "software-project score would be misleading."
            ),
            signals=(
                classification_signal,
                f"{len(content_files)} content file(s), {len(source_files)} source "
                f"file(s), and {len(test_files)} test file(s)",
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
    if path.suffix not in CODE_SUFFIXES:
        return False
    parts = set(path.parts[:-1])
    if parts & NON_PRODUCT_TEST_DIRECTORIES:
        return False
    return follows_test_file_convention(path.as_posix())


def _is_source_file(path: PurePosixPath) -> bool:
    """Return whether a path looks like production source rather than support content."""
    if path.suffix not in CODE_SUFFIXES or _is_test_file(path):
        return False
    return not bool(set(path.parts[:-1]) & SUPPORT_DIRECTORIES)


def _is_content_file(path: PurePosixPath) -> bool:
    """Return whether a path is primarily documentation, learning, or reference content."""
    return path.suffix in CONTENT_SUFFIXES or path.name == "skill.md"


def _is_narrative_content_file(path: PurePosixPath) -> bool:
    """Return whether a file is narrative material rather than an executable notebook."""
    return path.suffix in NARRATIVE_CONTENT_SUFFIXES or path.name == "skill.md"


def _software_is_confined_to_content_tooling(
    source_files: tuple[PurePosixPath, ...],
    test_files: tuple[PurePosixPath, ...],
    *,
    narrative_count: int,
) -> bool:
    """Return whether all software evidence belongs to an isolated support area."""
    software_files = source_files + test_files
    if not software_files or any(len(path.parts) == 1 for path in software_files):
        return False
    top_level_directories = {path.parts[0] for path in software_files}
    if top_level_directories <= CONTENT_MAINTENANCE_DIRECTORIES:
        return True
    return bool(
        top_level_directories
        <= CONTENT_MAINTENANCE_DIRECTORIES | CONTENT_SITE_DIRECTORIES
        and narrative_count >= len(software_files)
    )


def _is_structured_learning_collection(
    narrative_files: tuple[PurePosixPath, ...],
    source_files: tuple[PurePosixPath, ...],
    *,
    root_manifests: tuple[PurePosixPath, ...],
) -> bool:
    """Return whether numbered learning sections dominate a manifest-free tree."""
    if root_manifests or len(narrative_files) < 5:
        return False
    learning_files = tuple(
        path
        for path in narrative_files + source_files
        if any(LEARNING_SEQUENCE_PATTERN.fullmatch(part) for part in path.parts[:-1])
    )
    relevant_count = len(narrative_files) + len(source_files)
    return bool(len(learning_files) >= 10 and len(learning_files) * 2 >= relevant_count)


def _path_is_below(path: PurePosixPath, root: str) -> bool:
    """Return whether a source path belongs to a manifest-backed project root."""
    return path.as_posix().startswith(f"{root}/")
