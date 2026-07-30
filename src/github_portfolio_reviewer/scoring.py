"""Transparent 100-point scoring rules for repository findings."""

from dataclasses import dataclass

from github_portfolio_reviewer.models import (
    AnalysisFinding,
    Category,
    CheckId,
    CheckStatus,
    RepositorySnapshot,
    ReviewMode,
    ReviewReport,
    ScoredCheck,
)

RULESET_VERSION = "1.1.0"


@dataclass(frozen=True, slots=True)
class CheckSpecification:
    """Human-readable scoring metadata for one analysis check."""

    category: Category
    title: str
    max_points: int
    recommendation: str


CHECK_SPECIFICATIONS: dict[CheckId, CheckSpecification] = {
    CheckId.DESCRIPTION: CheckSpecification(
        Category.METADATA,
        "Clear repository description",
        3,
        "Write a concise description that states the problem, solution, and main technology.",
    ),
    CheckId.TOPICS: CheckSpecification(
        Category.METADATA,
        "Discoverable topics",
        2,
        "Add at least three accurate GitHub topics, such as python, ai, or streamlit.",
    ),
    CheckId.LICENSE: CheckSpecification(
        Category.METADATA,
        "Explicit license",
        3,
        "Choose an appropriate license and add its standard LICENSE file at the root.",
    ),
    CheckId.ACTIVE: CheckSpecification(
        Category.METADATA,
        "Repository available for development",
        2,
        "If the project is still maintained, unarchive it; otherwise explain its completed status.",
    ),
    CheckId.README_EXISTS: CheckSpecification(
        Category.README,
        "README present",
        5,
        "Add a README with the project purpose, setup, usage, and results.",
    ),
    CheckId.README_DETAIL: CheckSpecification(
        Category.README,
        "README gives sufficient context",
        8,
        "Expand the README to explain the problem, approach, key decisions, and limitations.",
    ),
    CheckId.README_INSTALLATION: CheckSpecification(
        Category.README,
        "Installation instructions",
        4,
        "Add an Installation or Setup section with copyable environment and install commands.",
    ),
    CheckId.README_USAGE: CheckSpecification(
        Category.README,
        "Usage examples",
        4,
        "Add a Usage or Examples section showing the main workflow and expected output.",
    ),
    CheckId.README_BADGES: CheckSpecification(
        Category.README,
        "Useful status badges",
        2,
        "Add only useful badges, such as CI status and supported Python version.",
    ),
    CheckId.README_VISUALS: CheckSpecification(
        Category.README,
        "Screenshots or demo visuals",
        2,
        "Add a screenshot, architecture diagram, or short demo GIF that shows the result.",
    ),
    CheckId.SOURCE_LAYOUT: CheckSpecification(
        Category.STRUCTURE,
        "Recognizable source layout",
        5,
        "Group production code under a clear package or src/, app/, or lib/ directory.",
    ),
    CheckId.DEPENDENCY_MANIFEST: CheckSpecification(
        Category.STRUCTURE,
        "Dependency/build manifest",
        4,
        "Add a standard root manifest such as pyproject.toml or package.json.",
    ),
    CheckId.GITIGNORE: CheckSpecification(
        Category.STRUCTURE,
        "Root .gitignore",
        3,
        "Add a root .gitignore covering environments, caches, build outputs, and secrets.",
    ),
    CheckId.MODULARITY: CheckSpecification(
        Category.STRUCTURE,
        "Code split into focused modules",
        3,
        "Split unrelated responsibilities into small, clearly named modules.",
    ),
    CheckId.TEST_FILES: CheckSpecification(
        Category.TESTS,
        "Automated tests",
        7,
        "Add a tests/ directory with representative success, edge, and failure cases.",
    ),
    CheckId.TEST_QUALITY: CheckSpecification(
        Category.TESTS,
        "Implemented test behavior",
        4,
        "Replace placeholder tests with deterministic cases that exercise behavior and assert outcomes.",
    ),
    CheckId.TEST_CONFIGURATION: CheckSpecification(
        Category.TESTS,
        "Test configuration",
        2,
        "Add explicit test configuration and document the command used to run tests.",
    ),
    CheckId.COVERAGE: CheckSpecification(
        Category.TESTS,
        "Coverage tracking",
        2,
        "Configure coverage reporting to reveal important behavior that lacks tests.",
    ),
    CheckId.CI_WORKFLOW: CheckSpecification(
        Category.CI_CD,
        "CI workflow configuration",
        4,
        "Add a CI workflow that installs dependencies, lints code, and runs tests.",
    ),
    CheckId.ACTIONS_PINNED: CheckSpecification(
        Category.CI_CD,
        "Pinned GitHub Actions",
        2,
        "Pin third-party GitHub Actions to full commit SHAs and review updates deliberately.",
    ),
    CheckId.WORKFLOW_PERMISSIONS: CheckSpecification(
        Category.CI_CD,
        "Least-privilege workflow permissions",
        2,
        "Declare explicit read-only workflow permissions and grant write access only to jobs that require it.",
    ),
    CheckId.CI_BADGE: CheckSpecification(
        Category.CI_CD,
        "Visible CI status",
        2,
        "Add the CI workflow status badge to the README after the workflow is reliable.",
    ),
    CheckId.DOCS: CheckSpecification(
        Category.DOCUMENTATION,
        "Extended documentation",
        4,
        "Document architecture, important decisions, or API behavior under docs/.",
    ),
    CheckId.CONTRIBUTING: CheckSpecification(
        Category.DOCUMENTATION,
        "Contribution guide",
        2,
        "Add CONTRIBUTING.md with local setup, checks, and pull-request expectations.",
    ),
    CheckId.CODE_OF_CONDUCT: CheckSpecification(
        Category.DOCUMENTATION,
        "Code of conduct",
        2,
        "Add a standard code of conduct if you intend to accept community contributions.",
    ),
    CheckId.CHANGELOG: CheckSpecification(
        Category.DOCUMENTATION,
        "Change history",
        2,
        "Track notable releases in CHANGELOG.md once the project has versioned releases.",
    ),
    CheckId.SECURITY_POLICY: CheckSpecification(
        Category.SECURITY,
        "Security policy",
        2,
        "Add SECURITY.md explaining how vulnerabilities should be reported privately.",
    ),
    CheckId.DEPENDENCY_UPDATES: CheckSpecification(
        Category.SECURITY,
        "Automated dependency updates",
        3,
        "Configure Dependabot or Renovate for the dependency ecosystems you use.",
    ),
    CheckId.NO_SENSITIVE_FILES: CheckSpecification(
        Category.SECURITY,
        "No risky tracked filenames",
        3,
        "Inspect flagged files, remove real secrets from history, rotate them, and add ignores.",
    ),
    CheckId.NO_DETECTED_SECRETS: CheckSpecification(
        Category.SECURITY,
        "No detected credential patterns",
        4,
        "Remove detected credentials from history, rotate them immediately, and use repository secrets or environment variables.",
    ),
    CheckId.LOCK_FILE: CheckSpecification(
        Category.SECURITY,
        "Reproducible dependencies",
        3,
        "Commit an appropriate lock file or pin deployable application dependencies.",
    ),
}

CHECK_TARGETS: dict[CheckId, str] = {
    CheckId.DESCRIPTION: "GitHub About section",
    CheckId.TOPICS: "GitHub About section",
    CheckId.LICENSE: "LICENSE",
    CheckId.ACTIVE: "Repository settings",
    CheckId.README_EXISTS: "README.md",
    CheckId.README_DETAIL: "README.md",
    CheckId.README_INSTALLATION: "README.md",
    CheckId.README_USAGE: "README.md",
    CheckId.README_BADGES: "README.md",
    CheckId.README_VISUALS: "README.md",
    CheckId.SOURCE_LAYOUT: "src/ or application package",
    CheckId.DEPENDENCY_MANIFEST: "pyproject.toml or equivalent",
    CheckId.GITIGNORE: ".gitignore",
    CheckId.MODULARITY: "Production source modules",
    CheckId.TEST_FILES: "tests/",
    CheckId.TEST_QUALITY: "Test implementation",
    CheckId.TEST_CONFIGURATION: "Test configuration",
    CheckId.COVERAGE: "Coverage configuration",
    CheckId.CI_WORKFLOW: ".github/workflows/",
    CheckId.ACTIONS_PINNED: ".github/workflows/",
    CheckId.WORKFLOW_PERMISSIONS: ".github/workflows/",
    CheckId.CI_BADGE: "README.md",
    CheckId.DOCS: "docs/",
    CheckId.CONTRIBUTING: "CONTRIBUTING.md",
    CheckId.CODE_OF_CONDUCT: "CODE_OF_CONDUCT.md",
    CheckId.CHANGELOG: "CHANGELOG.md",
    CheckId.SECURITY_POLICY: "SECURITY.md",
    CheckId.DEPENDENCY_UPDATES: ".github/dependabot.yml",
    CheckId.NO_SENSITIVE_FILES: "Tracked filenames",
    CheckId.NO_DETECTED_SECRETS: "Inspected repository text files",
    CheckId.LOCK_FILE: "Dependency lock file",
}

STATUS_FACTORS = {
    CheckStatus.PASS: 1.0,
    CheckStatus.PARTIAL: 0.5,
    CheckStatus.FAIL: 0.0,
}


def score_repository(
    snapshot: RepositorySnapshot,
    findings: tuple[AnalysisFinding, ...],
    *,
    review_mode: ReviewMode = ReviewMode.GENERAL,
) -> ReviewReport:
    """Apply the documented rubric to analysis findings."""
    _validate_rubric(findings)
    checks = tuple(_score_finding(finding) for finding in findings)
    return ReviewReport(
        repository=snapshot,
        checks=checks,
        review_mode=review_mode,
        ruleset_version=RULESET_VERSION,
    )


def score_band(score: float) -> str:
    """Return a plain-language portfolio presentation band for a score."""
    if score >= 90:
        return "Portfolio-ready"
    if score >= 75:
        return "Strong"
    if score >= 60:
        return "Developing"
    if score >= 40:
        return "Needs focused improvement"
    return "Early stage"


def _score_finding(finding: AnalysisFinding) -> ScoredCheck:
    specification = CHECK_SPECIFICATIONS[finding.check_id]
    points = specification.max_points * STATUS_FACTORS[finding.status]
    return ScoredCheck(
        check_id=finding.check_id,
        category=specification.category,
        title=specification.title,
        status=finding.status,
        evidence=finding.evidence,
        points=points,
        max_points=specification.max_points,
        recommendation=specification.recommendation,
        sources=finding.sources,
        target=CHECK_TARGETS[finding.check_id],
    )


def _validate_rubric(findings: tuple[AnalysisFinding, ...]) -> None:
    if set(CHECK_SPECIFICATIONS) != set(CheckId):
        raise RuntimeError("Every analysis check must have exactly one scoring rule.")
    if set(CHECK_TARGETS) != set(CheckId):
        raise RuntimeError("Every analysis check must have exactly one target.")
    if sum(spec.max_points for spec in CHECK_SPECIFICATIONS.values()) != 100:
        raise RuntimeError("Scoring-rule weights must total 100 points.")

    finding_ids = [finding.check_id for finding in findings]
    if len(finding_ids) != len(CheckId) or set(finding_ids) != set(CheckId):
        raise ValueError("Findings must contain every analysis check exactly once.")
