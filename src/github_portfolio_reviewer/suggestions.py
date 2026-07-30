"""Create a short, prioritized action plan from scored checks."""

from github_portfolio_reviewer.models import (
    CheckId,
    CheckStatus,
    ReviewMode,
    ReviewReport,
    ScoredCheck,
    Suggestion,
)

HIGH_PRIORITY_CHECKS = {
    CheckId.CI_WORKFLOW,
    CheckId.DEPENDENCY_MANIFEST,
    CheckId.LICENSE,
    CheckId.NO_SENSITIVE_FILES,
    CheckId.NO_DETECTED_SECRETS,
    CheckId.README_EXISTS,
    CheckId.SOURCE_LAYOUT,
    CheckId.TEST_FILES,
    CheckId.TEST_QUALITY,
}
MEDIUM_PRIORITY_CHECKS = {
    CheckId.ACTIONS_PINNED,
    CheckId.DEPENDENCY_UPDATES,
    CheckId.GITIGNORE,
    CheckId.LOCK_FILE,
    CheckId.README_DETAIL,
    CheckId.README_INSTALLATION,
    CheckId.README_USAGE,
    CheckId.SECURITY_POLICY,
    CheckId.WORKFLOW_PERMISSIONS,
}

CASCADE_CHECKS: dict[CheckId, set[CheckId]] = {
    CheckId.README_EXISTS: {
        CheckId.README_DETAIL,
        CheckId.README_INSTALLATION,
        CheckId.README_USAGE,
        CheckId.README_BADGES,
        CheckId.README_VISUALS,
    },
    CheckId.TEST_FILES: {
        CheckId.TEST_QUALITY,
        CheckId.TEST_CONFIGURATION,
        CheckId.COVERAGE,
    },
    CheckId.CI_WORKFLOW: {
        CheckId.ACTIONS_PINNED,
        CheckId.WORKFLOW_PERMISSIONS,
        CheckId.CI_BADGE,
    },
    CheckId.SOURCE_LAYOUT: {CheckId.MODULARITY},
}

MODE_FOCUS_CHECKS: dict[ReviewMode, set[CheckId]] = {
    ReviewMode.GENERAL: set(),
    ReviewMode.PYTHON: {
        CheckId.SOURCE_LAYOUT,
        CheckId.DEPENDENCY_MANIFEST,
        CheckId.MODULARITY,
        CheckId.TEST_FILES,
        CheckId.TEST_QUALITY,
        CheckId.TEST_CONFIGURATION,
        CheckId.COVERAGE,
    },
    ReviewMode.AI_ML: {
        CheckId.README_DETAIL,
        CheckId.README_USAGE,
        CheckId.README_VISUALS,
        CheckId.DOCS,
        CheckId.TEST_QUALITY,
        CheckId.COVERAGE,
        CheckId.LOCK_FILE,
    },
    ReviewMode.DATA_SCIENCE: {
        CheckId.README_DETAIL,
        CheckId.README_USAGE,
        CheckId.README_VISUALS,
        CheckId.DOCS,
        CheckId.TEST_QUALITY,
        CheckId.LOCK_FILE,
    },
    ReviewMode.BACKEND: {
        CheckId.CI_WORKFLOW,
        CheckId.ACTIONS_PINNED,
        CheckId.WORKFLOW_PERMISSIONS,
        CheckId.TEST_FILES,
        CheckId.TEST_QUALITY,
        CheckId.SECURITY_POLICY,
        CheckId.DEPENDENCY_UPDATES,
        CheckId.NO_SENSITIVE_FILES,
        CheckId.NO_DETECTED_SECRETS,
    },
}


def generate_suggestions(
    report: ReviewReport, *, limit: int | None = 8
) -> tuple[Suggestion, ...]:
    """Return deduplicated actions ordered by risk and potential score gain."""
    incomplete = [check for check in report.checks if check.status != CheckStatus.PASS]
    suppressed = _suppressed_check_ids(incomplete)
    suggestions = [
        _to_suggestion(check)
        for check in incomplete
        if check.check_id not in suppressed
    ]
    suggestions.sort(
        key=lambda suggestion: _suggestion_sort_key(
            suggestion, review_mode=report.review_mode
        )
    )
    if limit is not None:
        suggestions = suggestions[:limit]
    return tuple(suggestions)


def _suppressed_check_ids(checks: list[ScoredCheck]) -> set[CheckId]:
    by_id = {check.check_id: check for check in checks}
    suppressed: set[CheckId] = set()
    for parent, children in CASCADE_CHECKS.items():
        parent_check = by_id.get(parent)
        if parent_check and parent_check.status == CheckStatus.FAIL:
            suppressed.update(children)
    return suppressed


def _to_suggestion(check: ScoredCheck) -> Suggestion:
    priority = _priority_for(check)
    return Suggestion(
        priority=priority,
        category=check.category,
        title=check.title,
        action=check.recommendation,
        potential_points=check.max_points - check.points,
        check_id=check.check_id,
    )


def _priority_for(check: ScoredCheck) -> str:
    if (
        check.check_id == CheckId.NO_SENSITIVE_FILES
        and check.status == CheckStatus.FAIL
    ):
        return "High"
    if check.check_id in HIGH_PRIORITY_CHECKS:
        return "High"
    if check.check_id in MEDIUM_PRIORITY_CHECKS:
        return "Medium"
    return "Low"


def _suggestion_sort_key(
    suggestion: Suggestion, *, review_mode: ReviewMode
) -> tuple[int, int, float, str]:
    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    focused = suggestion.check_id in MODE_FOCUS_CHECKS[review_mode]
    return (
        priority_order[suggestion.priority],
        0 if focused else 1,
        -suggestion.potential_points,
        suggestion.title,
    )
