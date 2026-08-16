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


def is_ci_file(path: str) -> bool:
    """Return whether a normalized path follows a supported CI convention."""
    normalized = path.replace("\\", "/").strip("/").casefold()
    return bool(
        GITHUB_WORKFLOW_PATTERN.fullmatch(normalized)
        or normalized in CI_CONFIGURATION_PATHS
    )
