"""Render the template across the answer matrix and run the generated gate."""

from __future__ import annotations

import json
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


def test_property_layer(render, tmp_path: Path) -> None:
    on = render({**MINIMAL, "enable_property_tests": True}, tmp_path / "on")
    assert (on / "tests" / "property" / "test_example_property.py").is_file()
    run_in(on, "just", "fuzz")
    off = render(MINIMAL, tmp_path / "off")
    assert not (off / "tests" / "property").exists()


def test_policy_layer(render, tmp_path: Path) -> None:
    on = render({**MINIMAL, "enable_policy_tests": True}, tmp_path / "on")
    assert (on / "tests" / "policy" / "test_gates.py").is_file()
    # --no-cov: policy tests import no package code; the global --cov + fail_under
    # in addopts would otherwise fail the run at 0% coverage (mirrors `just policy`).
    run_in(on, "uv", "run", "pytest", "--no-cov", "tests/policy")
    off = render(MINIMAL, tmp_path / "off")
    assert not (off / "tests" / "policy").exists()


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


def test_audit_layer(render, tmp_path: Path) -> None:
    on = render({**MINIMAL, "enable_dependency_audit": True}, tmp_path / "on")
    result = run_in(on, "just", "audit")
    # Prove pip-audit actually executed (not a vacuous exit-0 on empty input).
    assert "vulnerab" in (result.stdout + result.stderr).lower()
    off = render(MINIMAL, tmp_path / "off")
    assert "audit:" not in (off / "justfile").read_text()


def test_scanner_layer(render, tmp_path: Path) -> None:
    on = render({**MINIMAL, "enable_scanners": True}, tmp_path / "on")
    assert (on / ".gitleaks.toml").is_file()
    assert (on / ".semgrep.yml").is_file()
    assert "scan:" in (on / "justfile").read_text()
    off = render(MINIMAL, tmp_path / "off")
    assert not (off / ".gitleaks.toml").exists()


def test_renovate_layer(render, tmp_path: Path) -> None:
    on = render({**MINIMAL, "enable_renovate": True}, tmp_path / "on")
    cfg = json.loads((on / "renovate.json").read_text())
    assert "helpers:pinGitHubActionDigests" in cfg["extends"]
    assert cfg["pre-commit"]["enabled"] is True
    off = render(MINIMAL, tmp_path / "off")
    assert not (off / "renovate.json").exists()


def test_mutation_config(render, tmp_path: Path) -> None:
    on = render({**MINIMAL, "enable_mutation_tests": True}, tmp_path / "on")
    pyproject = (on / "pyproject.toml").read_text()
    assert "[tool.mutmut]" in pyproject
    assert "source_paths" in pyproject
    assert "mutate:" in (on / "justfile").read_text()
    off = render(MINIMAL, tmp_path / "off")
    assert "[tool.mutmut]" not in (off / "pyproject.toml").read_text()


def test_ci_workflows(render, tmp_path: Path) -> None:
    full = {**MINIMAL, "enable_scanners": True, "enable_dependency_audit": True,
            "enable_sha_pin_policy": True, "enable_mutation_tests": True}
    project = render(full, tmp_path / "out")
    ci = (project / ".github" / "workflows" / "ci.yml").read_text()
    assert "uv sync --locked" in ci
    assert "just ci" in ci
    assert "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0" in ci
    # GitHub expressions survived Jinja rendering literally.
    assert "${{ matrix.python-version }}" in ci
    # Matrix respects requires-python (default 3.13 → no 3.11/3.12 legs).
    assert '"3.11"' not in ci and '"3.12"' not in ci
    assert (project / ".github" / "workflows" / "scan.yml").is_file()
    assert (project / ".github" / "workflows" / "mutation.yml").is_file()
    # Mutation workflow is non-gating.
    assert "continue-on-error: true" in (project / ".github" / "workflows" / "mutation.yml").read_text()
    bare = render(MINIMAL, tmp_path / "bare")
    assert not (bare / ".github" / "workflows" / "scan.yml").exists()


def test_sha_pin_policy(render, tmp_path: Path) -> None:
    full = {**MINIMAL, "enable_policy_tests": True, "enable_sha_pin_policy": True}
    project = render(full, tmp_path / "out")
    run_in(project, "uv", "run", "pytest", "--no-cov", "tests/policy")
    assert "test_actions_are_sha_pinned" in (project / "tests" / "policy" / "test_gates.py").read_text()


def test_apache_license_renders(render, tmp_path: Path) -> None:
    project = render({**MINIMAL, "license": "Apache-2.0"}, tmp_path / "out")
    text = (project / "LICENSE").read_text()
    assert text.lstrip().startswith("Apache License")
    # exactly one trailing newline (would otherwise fail end-of-file-fixer)
    assert text.endswith("\n") and not text.endswith("\n\n")
    # the vendored include source must not leak into the generated project
    assert not (project / "LICENSE-APACHE.txt").exists()


def test_library_builds(render, tmp_path: Path) -> None:
    project = render({**MINIMAL, "project_type": "library"}, tmp_path / "lib")
    run_in(project, "uv", "build")
    assert list((project / "dist").glob("*.whl"))
    # No stray entry-point file in a library render.
    pkg = project / "src" / "demo_project"
    assert not (pkg / "__main__.py").exists()
    assert not list(pkg.glob(".py"))


def test_application_runs(render, tmp_path: Path) -> None:
    project = render({**MINIMAL, "project_type": "application"}, tmp_path / "app")
    pyproject = (project / "pyproject.toml").read_text()
    assert "package = false" in pyproject
    assert "pythonpath" in pyproject
    assert "[project.scripts]" not in pyproject  # import-only fork
    run_in(project, "just", "ci")
    # The entry point runs via `python -m` with src on the path: `package = false`
    # leaves src/ uninstalled and pytest's `pythonpath` is pytest-only, so a bare
    # `python -m` raises ModuleNotFoundError — `env PYTHONPATH=src` is required.
    assert run_in(project, "env", "PYTHONPATH=src", "uv", "run", "python", "-m", "demo_project").returncode == 0


def test_all_toggles_on_passes_full_gate(render, tmp_path: Path) -> None:
    """Every guardrail layer ON: the generated project passes its own pre-commit + `just ci`.

    Closes the toggle-ON gate-coverage gap — `test_precommit_config_valid` only exercises MINIMAL,
    and the per-layer tests run sub-recipes that skip whole-tree hooks (e.g. end-of-file-fixer).
    """
    full = {
        **MINIMAL,
        "enable_property_tests": True,
        "enable_mutation_tests": True,
        "enable_policy_tests": True,
        "enable_scanners": True,
        "enable_dependency_audit": True,
        "enable_renovate": True,
        "enable_sha_pin_policy": True,
    }
    project = render(full, tmp_path / "out")

    # Stage everything so the generated project's own pre-commit sees every rendered file.
    run_in(project, "git", "add", "-A")
    precommit = run_in(project, "uv", "run", "pre-commit", "run", "--all-files", check=False)
    assert precommit.returncode == 0, (
        f"pre-commit failed on the all-toggles-ON render:\n{precommit.stdout}\n{precommit.stderr}"
    )

    gate = run_in(project, "just", "ci", check=False)
    assert gate.returncode == 0, (
        f"`just ci` failed on the all-toggles-ON render:\n{gate.stdout}\n{gate.stderr}"
    )


def test_curated_ruleset(render, tmp_path: Path) -> None:
    project = render({**MINIMAL, "ruff_ruleset": "curated"}, tmp_path / "out")
    pyproject = (project / "pyproject.toml").read_text()
    assert 'select = ["E", "F"' in pyproject
    assert '"ALL"' not in pyproject
    run_in(project, "uv", "run", "ruff", "check", ".")
