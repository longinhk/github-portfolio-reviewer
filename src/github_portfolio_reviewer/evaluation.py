"""Metrics for independently labeled repository-classification observations."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from github_portfolio_reviewer.models import RepositoryKind, RubricFit


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    """One expected label and one reviewer observation."""

    name: str
    expected_kind: RepositoryKind
    observed_kind: RepositoryKind
    expected_fit: RubricFit
    observed_fit: RubricFit


@dataclass(frozen=True, slots=True)
class EvaluationSummary:
    """Classification accuracy and confusion counts."""

    total: int
    kind_correct: int
    fit_correct: int
    kind_confusion: Mapping[tuple[RepositoryKind, RepositoryKind], int]
    fit_confusion: Mapping[tuple[RubricFit, RubricFit], int]

    @property
    def kind_accuracy(self) -> float:
        """Return repository-kind accuracy in the inclusive range 0–1."""
        return self.kind_correct / self.total if self.total else 0.0

    @property
    def fit_accuracy(self) -> float:
        """Return rubric-fit accuracy in the inclusive range 0–1."""
        return self.fit_correct / self.total if self.total else 0.0


def load_cases(path: Path) -> tuple[EvaluationCase, ...]:
    """Load and validate a UTF-8 JSON array of labeled observations."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("Evaluation data must be a non-empty JSON array.")
    return tuple(_case_from_mapping(item) for item in payload)


def evaluate_cases(cases: Sequence[EvaluationCase]) -> EvaluationSummary:
    """Calculate exact-label accuracy and confusion counts."""
    kind_confusion = Counter((case.expected_kind, case.observed_kind) for case in cases)
    fit_confusion = Counter((case.expected_fit, case.observed_fit) for case in cases)
    return EvaluationSummary(
        total=len(cases),
        kind_correct=sum(case.expected_kind == case.observed_kind for case in cases),
        fit_correct=sum(case.expected_fit == case.observed_fit for case in cases),
        kind_confusion=dict(kind_confusion),
        fit_confusion=dict(fit_confusion),
    )


def render_markdown(summary: EvaluationSummary) -> str:
    """Render compact, reviewable evaluation metrics."""
    lines = [
        "# Repository classification evaluation",
        "",
        f"Cases: **{summary.total}**",
        f"Repository-kind accuracy: **{summary.kind_accuracy:.1%}**",
        f"Rubric-fit accuracy: **{summary.fit_accuracy:.1%}**",
        "",
        "## Repository-kind confusion",
        "",
        "| Expected | Observed | Count |",
        "| --- | --- | ---: |",
    ]
    lines.extend(
        f"| {expected.value} | {observed.value} | {count} |"
        for (expected, observed), count in sorted(
            summary.kind_confusion.items(),
            key=lambda item: (item[0][0].value, item[0][1].value),
        )
    )
    lines.extend(
        [
            "",
            "## Rubric-fit confusion",
            "",
            "| Expected | Observed | Count |",
            "| --- | --- | ---: |",
        ]
    )
    lines.extend(
        f"| {expected.value} | {observed.value} | {count} |"
        for (expected, observed), count in sorted(
            summary.fit_confusion.items(),
            key=lambda item: (item[0][0].value, item[0][1].value),
        )
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Evaluate a labeled observation file from the command line."""
    parser = argparse.ArgumentParser(prog="portfolio-evaluate")
    parser.add_argument("data", type=Path, help="JSON labeled-observation file")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        rendered = render_markdown(evaluate_cases(load_cases(args.data)))
        if args.output is None:
            print(rendered)
        else:
            args.output.write_text(f"{rendered}\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(2, f"portfolio-evaluate: {error}\n")
    return 0


def _case_from_mapping(item: Any) -> EvaluationCase:
    if not isinstance(item, Mapping):
        raise ValueError("Every evaluation case must be a JSON object.")
    expected = item.get("expected")
    observed = item.get("observed")
    if not isinstance(expected, Mapping) or not isinstance(observed, Mapping):
        raise ValueError("Every case needs expected and observed objects.")
    name = str(item.get("name") or "").strip()
    if not name:
        raise ValueError("Every evaluation case needs a name.")
    try:
        return EvaluationCase(
            name=name,
            expected_kind=RepositoryKind(str(expected["kind"])),
            observed_kind=RepositoryKind(str(observed["kind"])),
            expected_fit=RubricFit(str(expected["fit"])),
            observed_fit=RubricFit(str(observed["fit"])),
        )
    except (KeyError, ValueError) as error:
        raise ValueError(f"Evaluation case {name!r} has an invalid label.") from error


if __name__ == "__main__":  # pragma: no cover - console entry point
    raise SystemExit(main())
