"""Repository path conventions shared by evidence collection and analysis."""

import re

GITHUB_WORKFLOW_PATTERN = re.compile(r"^\.github/workflows/.+\.ya?ml$")
CI_CONFIGURATION_PATHS = {
    ".circleci/config.yml",
    ".gitlab-ci.yml",
    ".travis.yml",
    "azure-pipelines.yml",
    "jenkinsfile",
}
TEST_DIRECTORY_NAMES = {"__tests__", "spec", "specs", "test", "tests"}
TEST_SUPPORT_FILE_NAMES = {
    "__init__.py",
    "conftest.py",
    "factories.py",
    "fixtures.py",
}
TEST_FILE_PATTERNS = (
    re.compile(r"test_.+\.py"),
    re.compile(r".+_test\.py"),
    re.compile(r".+\.(?:test|spec)\.[jt]sx?"),
    re.compile(r".+_test\.go"),
    re.compile(r".+_test\.(?:c|cc|cpp|cxx)"),
    re.compile(r".+_spec\.rb"),
    re.compile(r".+(?:test|tests)\.(?:cs|java|kt|swift)"),
)


def is_ci_file(path: str) -> bool:
    """Return whether a normalized path follows a supported CI convention."""
    normalized = path.replace("\\", "/").strip("/").casefold()
    return bool(
        GITHUB_WORKFLOW_PATTERN.fullmatch(normalized)
        or normalized in CI_CONFIGURATION_PATHS
    )


def follows_test_file_convention(path: str) -> bool:
    """Return whether a normalized source path follows a common test convention."""
    normalized = path.replace("\\", "/").strip("/").casefold()
    parts = normalized.split("/")
    name = parts[-1]
    if name in TEST_SUPPORT_FILE_NAMES:
        return False
    return bool(
        set(parts[:-1]) & TEST_DIRECTORY_NAMES
        or any(pattern.fullmatch(name) for pattern in TEST_FILE_PATTERNS)
    )
