"""Tests for deterministic software-rubric applicability assessment."""

from collections.abc import Callable

from github_portfolio_reviewer.applicability import assess_rubric_fit
from github_portfolio_reviewer.models import (
    RepositoryKind,
    RepositoryReference,
    RepositorySnapshot,
    RubricFit,
)


def test_conventional_software_project_has_high_rubric_fit(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            files=(
                "pyproject.toml",
                "src/project/app.py",
                "src/project/service.py",
                "tests/test_app.py",
            )
        )
    )

    assert assessment.repository_kind == RepositoryKind.SOFTWARE
    assert assessment.fit == RubricFit.HIGH


def test_nested_projects_are_classified_as_a_medium_fit_monorepo(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            files=(
                "service-a/pyproject.toml",
                "service-a/src/api.py",
                "service-b/package.json",
                "service-b/src/index.ts",
            )
        )
    )

    assert assessment.repository_kind == RepositoryKind.MONOREPO
    assert assessment.fit == RubricFit.MEDIUM
    assert "whole default branch" in assessment.explanation


def test_support_manifests_do_not_make_django_shape_a_monorepo(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            files=(
                "package.json",
                "pyproject.toml",
                "django/core/handlers/base.py",
                "tests/test_client.py",
                "docs/requirements.txt",
                "tests/fixtures/project/requirements.txt",
            )
        )
    )

    assert assessment.repository_kind == RepositoryKind.SOFTWARE
    assert assessment.fit == RubricFit.HIGH


def test_support_directory_names_do_not_make_software_look_like_content(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            description=(
                "Build a distributable Python package while keeping generated "
                "dist and node_modules directories out of source control"
            ),
            files=(
                "pyproject.toml",
                "src/project/app.py",
                "tests/test_app.py",
                "build/package.json",
                "dist/requirements.txt",
                "node_modules/example/package.json",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.SOFTWARE
    assert assessment.fit == RubricFit.HIGH


def test_root_and_real_nested_project_make_pydantic_shape_a_monorepo(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            files=(
                "pyproject.toml",
                "pydantic/main.py",
                "tests/test_main.py",
                "pydantic-core/Cargo.toml",
                "pydantic-core/src/lib.rs",
                "tests/plugin/pyproject.toml",
            )
        )
    )

    assert assessment.repository_kind == RepositoryKind.MONOREPO
    assert assessment.fit == RubricFit.MEDIUM
    assert assessment.signals == ("Manifests identify 2 distinct project roots",)


def test_multiple_real_projects_make_freecodecamp_shape_a_monorepo(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            files=(
                "package.json",
                "api/package.json",
                "api/src/index.ts",
                "client/package.json",
                "client/src/index.ts",
                "packages/shared/package.json",
                "packages/shared/src/index.ts",
            )
        )
    )

    assert assessment.repository_kind == RepositoryKind.MONOREPO
    assert assessment.fit == RubricFit.MEDIUM


def test_educational_content_repository_is_not_scored(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            reference=RepositoryReference("example", "machine-learning-notes"),
            description="Machine learning lecture notes and slides",
            language="Jupyter Notebook",
            files=(
                "README.md",
                "notes/introduction.md",
                "notes/regression.ipynb",
                "slides/week-01.pdf",
                "slides/week-02.pdf",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.CONTENT
    assert assessment.fit == RubricFit.LOW


def test_content_collection_is_not_mistaken_for_software_by_root_manifest(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            reference=RepositoryReference("example", "skills"),
            description="A collection of reusable engineering skills",
            files=(
                "package.json",
                "README.md",
                "skills/python/SKILL.md",
                "skills/testing/SKILL.md",
                "skills/security/SKILL.md",
                "skills/docs/SKILL.md",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.CONTENT
    assert assessment.fit == RubricFit.LOW


def test_ambiguous_repository_uses_medium_fit_instead_of_guessing(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(make_snapshot(files=("README.md",)))

    assert assessment.repository_kind == RepositoryKind.UNKNOWN
    assert assessment.fit == RubricFit.MEDIUM


def test_truncated_tree_never_produces_a_low_fit_classification(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            reference=RepositoryReference("example", "learning-notes"),
            description="Lecture notes and slides",
            files=("README.md", "notes/model.ipynb", "slides/week-1.pdf"),
            tree_truncated=True,
        )
    )

    assert assessment.repository_kind == RepositoryKind.UNKNOWN
    assert assessment.fit == RubricFit.MEDIUM
    assert "truncated" in assessment.explanation.casefold()


def test_sample_manifests_without_local_source_do_not_create_a_monorepo(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            files=(
                "pyproject.toml",
                "src/project/app.py",
                "samples/widget/package.json",
                "demo/service/pyproject.toml",
            )
        )
    )

    assert assessment.repository_kind == RepositoryKind.SOFTWARE
    assert assessment.fit == RubricFit.HIGH


def test_content_term_substrings_do_not_trigger_content_classification(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            reference=RepositoryReference("example", "notebook-api"),
            description="A notebook-compatible software service",
            files=(
                "pyproject.toml",
                "src/api.py",
                "docs/one.md",
                "docs/two.md",
                "docs/three.md",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.SOFTWARE
    assert assessment.fit == RubricFit.HIGH
