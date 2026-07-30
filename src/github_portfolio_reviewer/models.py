"""Domain models shared by the reviewer modules."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Category(StrEnum):
    """High-level areas included in a repository review."""

    METADATA = "Repository metadata"
    README = "README quality"
    STRUCTURE = "Project structure"
    TESTS = "Tests"
    CI_CD = "CI/CD"
    DOCUMENTATION = "Documentation"
    SECURITY = "Security"


class CheckStatus(StrEnum):
    """Possible outcomes for an analysis check."""

    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


class CheckId(StrEnum):
    """Stable identifiers connecting analysis results to scoring rules."""

    DESCRIPTION = "description"
    TOPICS = "topics"
    LICENSE = "license"
    ACTIVE = "active"
    README_EXISTS = "readme_exists"
    README_DETAIL = "readme_detail"
    README_INSTALLATION = "readme_installation"
    README_USAGE = "readme_usage"
    README_BADGES = "readme_badges"
    README_VISUALS = "readme_visuals"
    SOURCE_LAYOUT = "source_layout"
    DEPENDENCY_MANIFEST = "dependency_manifest"
    GITIGNORE = "gitignore"
    MODULARITY = "modularity"
    TEST_FILES = "test_files"
    TEST_QUALITY = "test_quality"
    TEST_CONFIGURATION = "test_configuration"
    COVERAGE = "coverage"
    CI_WORKFLOW = "ci_workflow"
    ACTIONS_PINNED = "actions_pinned"
    WORKFLOW_PERMISSIONS = "workflow_permissions"
    CI_BADGE = "ci_badge"
    DOCS = "docs"
    CONTRIBUTING = "contributing"
    CODE_OF_CONDUCT = "code_of_conduct"
    CHANGELOG = "changelog"
    SECURITY_POLICY = "security_policy"
    DEPENDENCY_UPDATES = "dependency_updates"
    NO_SENSITIVE_FILES = "no_sensitive_files"
    NO_DETECTED_SECRETS = "no_detected_secrets"
    LOCK_FILE = "lock_file"


class ReviewMode(StrEnum):
    """Deterministic recommendation focus selected by the user."""

    GENERAL = "General"
    PYTHON = "Python internship"
    AI_ML = "AI/ML internship"
    DATA_SCIENCE = "Data science internship"
    BACKEND = "Backend internship"


@dataclass(frozen=True, slots=True)
class RepositoryReference:
    """The owner and repository name parsed from user input."""

    owner: str
    name: str

    @property
    def full_name(self) -> str:
        """Return the canonical ``owner/repository`` identifier."""
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True, slots=True)
class RepositoryTextFile:
    """Bounded text content fetched to verify selected repository signals."""

    path: str
    content: str


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    """Repository evidence collected from GitHub without changing the repository."""

    reference: RepositoryReference
    html_url: str
    description: str | None
    default_branch: str
    stars: int
    forks: int
    open_issues: int
    language: str | None
    topics: tuple[str, ...]
    license_name: str | None
    archived: bool
    fork: bool
    created_at: datetime | None
    pushed_at: datetime | None
    readme: str | None
    files: tuple[str, ...]
    tree_truncated: bool = False
    inspected_files: tuple[RepositoryTextFile, ...] = ()
    inspection_truncated: bool = False


@dataclass(frozen=True, slots=True)
class AnalysisFinding:
    """Unscored evidence produced by a single deterministic check."""

    check_id: CheckId
    status: CheckStatus
    evidence: str
    sources: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScoredCheck:
    """An analysis finding enriched with scoring and improvement guidance."""

    check_id: CheckId
    category: Category
    title: str
    status: CheckStatus
    evidence: str
    points: float
    max_points: int
    recommendation: str
    sources: tuple[str, ...] = ()
    target: str = "Repository"


@dataclass(frozen=True, slots=True)
class CategoryScore:
    """The earned and available points for one report category."""

    category: Category
    points: float
    max_points: int


@dataclass(frozen=True, slots=True)
class ReviewReport:
    """The complete scored review displayed to a user."""

    repository: RepositorySnapshot
    checks: tuple[ScoredCheck, ...]
    review_mode: ReviewMode = ReviewMode.GENERAL
    ruleset_version: str = "1.0.0"

    @property
    def score(self) -> float:
        """Return the exact repository score out of 100."""
        return sum(check.points for check in self.checks)

    @property
    def category_scores(self) -> tuple[CategoryScore, ...]:
        """Aggregate scored checks by category while preserving category order."""
        scores: list[CategoryScore] = []
        for category in Category:
            matching = [check for check in self.checks if check.category == category]
            scores.append(
                CategoryScore(
                    category=category,
                    points=sum(check.points for check in matching),
                    max_points=sum(check.max_points for check in matching),
                )
            )
        return tuple(scores)


@dataclass(frozen=True, slots=True)
class Suggestion:
    """A prioritized action derived from a failed or partial check."""

    priority: str
    category: Category
    title: str
    action: str
    potential_points: float
    check_id: CheckId | None = None
