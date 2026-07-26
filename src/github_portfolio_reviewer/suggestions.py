"""Create a short, prioritized action plan from scored checks."""

from github_portfolio_reviewer.models import (
    CheckId,
    CheckStatus,
    ReviewReport,
    ScoredCheck,
    Suggestion,
)

HIGH_PRIORITY_CHECKS = {
    CheckId.CI_WORKFLOW,
    CheckId.DEPENDENCY_MANIFEST,
    CheckId.LICENSE,
    CheckId.NO_SENSITIVE_FILES,
    CheckId.README_EXISTS,
    CheckId.SOURCE_LAYOUT,
    CheckId.TEST_FILES,
}
MEDIUM_PRIORITY_CHECKS = {
    CheckId.DEPENDENCY_UPDATES,
    CheckId.GITIGNORE,
    CheckId.LOCK_FILE,
    CheckId.README_DETAIL,
    CheckId.README_INSTALLATION,
    CheckId.README_USAGE,
    CheckId.SECURITY_POLICY,
}

CASCADE_CHECKS: dict[CheckId, set[CheckId]] = {
    CheckId.README_EXISTS: {
        CheckId.README_DETAIL,
        CheckId.README_INSTALLATION,
        CheckId.README_USAGE,
        CheckId.README_BADGES,
        CheckId.README_VISUALS,
    },
    CheckId.TEST_FILES: {CheckId.TEST_CONFIGURATION, CheckId.COVERAGE},
    CheckId.CI_WORKFLOW: {CheckId.CI_BADGE},
    CheckId.SOURCE_LAYOUT: {CheckId.MODULARITY},
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
    suggestions.sort(key=_suggestion_sort_key)
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


def _suggestion_sort_key(suggestion: Suggestion) -> tuple[int, float, str]:
    priority_order = {"High": 0, "Medium": 1, "Low": 2}
    return (
        priority_order[suggestion.priority],
        -suggestion.potential_points,
        suggestion.title,
    )
