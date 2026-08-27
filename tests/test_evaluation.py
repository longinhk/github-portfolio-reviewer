"""Tests for labeled classification metrics."""

import json

import pytest

from github_portfolio_reviewer.evaluation import (
    EvaluationCase,
    evaluate_cases,
    load_cases,
    render_markdown,
)
from github_portfolio_reviewer.models import RepositoryKind, RubricFit


def test_evaluation_reports_accuracy_and_confusion() -> None:
    cases = (
        EvaluationCase(
            "software",
            RepositoryKind.SOFTWARE,
            RepositoryKind.SOFTWARE,
            RubricFit.HIGH,
            RubricFit.HIGH,
        ),
        EvaluationCase(
            "content mistaken for software",
            RepositoryKind.CONTENT,
            RepositoryKind.SOFTWARE,
            RubricFit.LOW,
            RubricFit.HIGH,
        ),
    )

    summary = evaluate_cases(cases)

    assert summary.total == 2
    assert summary.kind_accuracy == 0.5
    assert summary.fit_accuracy == 0.5
    assert "50.0%" in render_markdown(summary)


def test_load_cases_validates_enum_labels(tmp_path) -> None:
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            [
                {
                    "name": "content",
                    "expected": {
                        "kind": RepositoryKind.CONTENT.value,
                        "fit": RubricFit.LOW.value,
                    },
                    "observed": {
                        "kind": RepositoryKind.CONTENT.value,
                        "fit": RubricFit.LOW.value,
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    assert load_cases(path)[0].name == "content"

    path.write_text('[{"name": "broken"}]', encoding="utf-8")
    with pytest.raises(ValueError, match="expected and observed"):
        load_cases(path)
