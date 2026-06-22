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


def test_minimal_tests_pass_with_coverage(render, tmp_path: Path) -> None:
    project = render(MINIMAL, tmp_path / "out")
    result = run_in(project, "uv", "run", "pytest", "-m", "not property", "tests/unit")
    assert "passed" in result.stdout


def test_minimal_just_ci_green(render, tmp_path: Path) -> None:
    project = render(MINIMAL, tmp_path / "out")
    run_in(project, "just", "ci")


def test_precommit_config_valid(render, tmp_path: Path) -> None:
    project = render(MINIMAL, tmp_path / "out")
    run_in(project, "uv", "run", "pre-commit", "validate-config", ".pre-commit-config.yaml")
    text = (project / ".pre-commit-config.yaml").read_text()
    assert "forbid-rej" in text
    assert "--assume-in-merge" in text
    # Stage the rendered tree first: pre-commit `run --all-files` operates on
    # `git ls-files`, and the copy-only _tasks `git init` but never `git add`, so
    # without this the hooks would inspect zero files and pass vacuously.
    run_in(project, "git", "add", "-A")
    run_in(project, "uv", "run", "pre-commit", "run", "--all-files")


def test_precommit_install_task_runs(template_root, tmp_path: Path) -> None:
    """The copy-only hook-install task fires when the hidden flag is left at default."""
    import copier

    dst = tmp_path / "installed"
    copier.run_copy(
        str(template_root),
        str(dst),
        data={**MINIMAL, "enable_precommit_install": True},
        defaults=True,
        unsafe=True,
        overwrite=True,
        quiet=True,
    )
    assert (dst / ".git" / "hooks" / "pre-commit").exists()
    assert (dst / ".git" / "hooks" / "pre-push").exists()


def test_agent_contract(render, tmp_path: Path) -> None:
    full = {**MINIMAL, "enable_property_tests": True, "enable_policy_tests": True}
    project = render(full, tmp_path / "out")
    assert (project / "CLAUDE.md").read_text().strip() == "@AGENTS.md"
    agents = (project / "AGENTS.md").read_text()
    assert "just ci" in agents
    assert agents.count("\n") < 200  # instruction budget
    # Disabled layers emit nothing.
    minimal = render(MINIMAL, tmp_path / "out2")
    assert "tests/property" not in (minimal / "AGENTS.md").read_text()
