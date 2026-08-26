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


def test_narrative_algorithm_collection_without_known_content_terms_is_not_scored(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            reference=RepositoryReference("example", "algorithms"),
            description="Crack LeetCode, not only how, but also why.",
            language="Markdown",
            files=(
                "README.md",
                "动态规划系列/状态转移详解.md",
                "数据结构系列/二叉树遍历.md",
                "算法思维系列/双指针技巧.md",
                "高频面试系列/链表习题.md",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.CONTENT
    assert assessment.fit == RubricFit.LOW
    assert "Narrative documents dominate" in assessment.signals[0]


def test_single_page_tutorial_index_is_not_forced_into_software_scoring(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            reference=RepositoryReference("example", "build-from-scratch"),
            description="Tutorials for learning how technologies work",
            topics=("tutorials", "learning"),
            files=("README.md", "CONTRIBUTING.md"),
        )
    )

    assert assessment.repository_kind == RepositoryKind.CONTENT
    assert assessment.fit == RubricFit.LOW


def test_content_list_with_validation_scripts_is_not_mistaken_for_product_code(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            description="A collective list of free developer resources",
            topics=("list", "resources"),
            files=(
                "README.md",
                "CONTRIBUTING.md",
                "scripts/validate/links.py",
                "scripts/tests/test_links.py",
                ".github/workflows/test_validation.yml",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.CONTENT
    assert assessment.fit == RubricFit.LOW
    assert "supporting tooling" in assessment.signals[0]
    assert "1 test file(s)" in assessment.signals[1]


def test_archived_tool_projects_do_not_turn_current_content_into_a_monorepo(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            description="A historical reference and guide to workplace policy",
            files=(
                "README.md",
                "docs/history.md",
                "docs/faq.md",
                "archived/license-tools/go.mod",
                "archived/license-tools/main.go",
                "archived/license-tools/main_test.go",
                "archive/old-validator/Cargo.toml",
                "archive/old-validator/src/main.rs",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.CONTENT
    assert assessment.fit == RubricFit.LOW


def test_vendored_documentation_tests_are_not_product_test_evidence(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            files=(
                "README.md",
                "notes/networking.md",
                "notes/databases.md",
                "docs/theme/vendor/tests/parser.test.js",
                "docs/theme/vendor/tests/renderer.test.js",
                "docs/theme/vendor/package.json",
            )
        )
    )

    assert assessment.repository_kind == RepositoryKind.CONTENT
    assert assessment.fit == RubricFit.LOW
    assert "0 test file(s)" in assessment.signals[1]


def test_skill_collection_with_root_tooling_is_not_scored_as_an_application(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            description="Reusable skills for software agents",
            files=(
                "package.json",
                "README.md",
                "skills/python/SKILL.md",
                "skills/testing/SKILL.md",
                "skills/security/SKILL.md",
                "skills/python/scripts/validate.sh",
                "skills/testing/scripts/check.sh",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.CONTENT
    assert assessment.fit == RubricFit.LOW
    assert "SKILL.md" in assessment.signals[0]


def test_curated_list_with_root_generator_and_go_tests_is_not_product_software(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            description="A curated list of useful Go packages",
            files=(
                "go.mod",
                "README.md",
                "CONTRIBUTING.md",
                "docs/selection-policy.md",
                "main.go",
                "convert.go",
                "main_test.go",
                "convert_test.go",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.CONTENT
    assert assessment.fit == RubricFit.LOW
    assert "Curated-list" in assessment.signals[0]
    assert "2 test file(s)" in assessment.signals[1]


def test_numbered_course_with_example_code_is_not_scored_as_an_application(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            files=(
                "README.md",
                "Day01-05/lesson.md",
                "Day01-05/example.py",
                "Day06-10/lesson.md",
                "Day06-10/example.py",
                "Day11-15/lesson.md",
                "Day11-15/example.py",
                "Day16-20/lesson.md",
                "Day16-20/example.py",
                "Day21-25/lesson.md",
                "Day21-25/example.py",
            )
        )
    )

    assert assessment.repository_kind == RepositoryKind.CONTENT
    assert assessment.fit == RubricFit.LOW
    assert "Numbered learning sections" in assessment.signals[0]


def test_content_site_with_isolated_website_code_is_not_scored_as_the_root_product(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            reference=RepositoryReference("example", "awesome-tools"),
            description="A definitive list of useful programming tools",
            files=(
                "README.md",
                "CONTRIBUTING.md",
                "docs/selection-guide.md",
                "pyproject.toml",
                "website/build.py",
                "website/static/main.js",
                "website/tests/test_build.py",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.CONTENT
    assert assessment.fit == RubricFit.LOW
    assert "supporting tooling" in assessment.signals[0]


def test_content_words_do_not_hide_a_website_when_software_outweighs_narrative_files(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            description="An interactive tutorial website",
            topics=("tutorial", "learning"),
            files=(
                "package.json",
                "README.md",
                "website/app.ts",
                "website/router.ts",
                "website/search.ts",
                "website/tests/app.test.ts",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.SOFTWARE
    assert assessment.fit == RubricFit.HIGH


def test_go_test_convention_keeps_a_real_go_application_scoreable(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            description="A production command-line service",
            files=(
                "go.mod",
                "cmd/service/main.go",
                "internal/service/service.go",
                "internal/service/service_test.go",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.SOFTWARE
    assert assessment.fit == RubricFit.HIGH


def test_educational_guide_with_untested_examples_is_not_scored_as_an_application(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            description="Learn system design for technical interviews",
            topics=("guide", "interview"),
            files=(
                "README.md",
                "guide/caching.md",
                "guide/databases.md",
                "solutions/cache.py",
                "solutions/queue.py",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.CONTENT
    assert assessment.fit == RubricFit.LOW
    assert "example source files" in assessment.signals[0]


def test_content_language_does_not_hide_a_conventional_software_application(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            description="An interactive learning guide for backend development",
            topics=("guide", "learning"),
            files=(
                "package.json",
                "src/app.ts",
                "src/router.ts",
                "tests/app.test.ts",
                "content/intro.md",
                "content/deployment.md",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.SOFTWARE
    assert assessment.fit == RubricFit.HIGH


def test_notebook_only_repository_remains_ambiguous_without_content_cues(
    make_snapshot: Callable[..., RepositorySnapshot],
) -> None:
    assessment = assess_rubric_fit(
        make_snapshot(
            description="Experimental analysis workspace",
            language="Jupyter Notebook",
            files=(
                "README.md",
                "notebooks/explore.ipynb",
                "notebooks/model.ipynb",
                "notebooks/results.ipynb",
            ),
        )
    )

    assert assessment.repository_kind == RepositoryKind.UNKNOWN
    assert assessment.fit == RubricFit.MEDIUM


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
