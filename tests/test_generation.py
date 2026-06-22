"""Render the template across the answer matrix and run the generated gate."""

from __future__ import annotations

from pathlib import Path

import yaml

from tests.conftest import run_in

MINIMAL = {
    "project_name": "Demo Project",
    "package_name": "demo_project",
    "author_name": "A Dev",
    "author_email": "dev@example.com",
    "description": "A demo.",
    "license": "MIT",
    "python_version": "3.13",
    "project_type": "library",
    "ruff_ruleset": "all",
    "coverage_floor": 85,
    "enable_property_tests": False,
    "enable_mutation_tests": False,
    "enable_policy_tests": False,
    "enable_scanners": False,
    "enable_dependency_audit": False,
    "enable_renovate": False,
    "enable_sha_pin_policy": False,
}


def test_minimal_renders(render, tmp_path: Path) -> None:
    project = render(MINIMAL, tmp_path / "out")

    # Package laid out under src/, py.typed shipped.
    assert (project / "src" / "demo_project" / "__init__.py").is_file()
    assert (project / "src" / "demo_project" / "py.typed").is_file()

    # _tasks ran (copy-only): uv produced a lockfile.
    assert (project / "uv.lock").is_file()

    # [project].name is the PEP 503-valid slug, NOT the human-readable project_name
    # ("Demo Project" would make `uv lock` reject the name and abort the render).
    assert 'name = "demo_project"' in (project / "pyproject.toml").read_text()

    # Answers file enables `copier update`.
    answers = yaml.safe_load((project / ".copier-answers.yml").read_text())
    assert "_src_path" in answers
    assert answers["package_name"] == "demo_project"

    # No unrendered template artifacts leaked through.
    assert not list(project.rglob("*.jinja"))
    assert not (project / "{{ _copier_conf.answers_file }}.jinja").exists()


def test_minimal_lints_clean(render, tmp_path: Path) -> None:
    project = render(MINIMAL, tmp_path / "out")
    run_in(project, "uv", "run", "ruff", "check", ".")
    run_in(project, "uv", "run", "ruff", "format", "--check", ".")


def test_minimal_typechecks(render, tmp_path: Path) -> None:
    project = render(MINIMAL, tmp_path / "out")
    run_in(project, "uv", "run", "basedpyright")
