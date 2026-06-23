"""Render the template across the answer matrix and run the generated gate."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest
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

FULL = {**MINIMAL, "project_type": "library", "ruff_ruleset": "all",
        "enable_property_tests": True, "enable_mutation_tests": True,
        "enable_policy_tests": True, "enable_scanners": True,
        "enable_dependency_audit": True, "enable_renovate": True,
        "enable_sha_pin_policy": True}

MATRIX = {"minimal": MINIMAL, "full": FULL,
          "app": {**MINIMAL, "project_type": "application"},
          "curated": {**MINIMAL, "ruff_ruleset": "curated"}}


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


def test_free_text_answers_are_toml_and_python_safe(render, tmp_path: Path) -> None:
    """A double-quote (or backslash) in free-text answers must not abort generation.

    description/author_name/author_email are interpolated into double-quoted TOML and the
    module docstring; unescaped, a `"` makes invalid TOML and the copy-only `uv lock` _task
    aborts the whole render. The values are escaped (not rejected), so prose quotes survive.
    """
    data = {**MINIMAL, "description": 'They said "hi"', "author_name": 'O"Brien'}
    # render runs the copy-only `uv lock`/`uv sync`; broken TOML would raise here.
    project = render(data, tmp_path / "out")

    parsed = tomllib.loads((project / "pyproject.toml").read_text())
    assert parsed["project"]["description"] == 'They said "hi"'
    assert parsed["project"]["authors"][0]["name"] == 'O"Brien'

    # The same values reach the module docstring; it must stay importable Python.
    assert run_in(project, "uv", "run", "python", "-c", "import demo_project").returncode == 0


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


def test_property_marker_enforced(render, tmp_path: Path) -> None:
    """An unmarked test under tests/property/ fails collection, not silently no-ops."""
    project = render({**MINIMAL, "enable_property_tests": True}, tmp_path / "out")
    (project / "tests" / "property" / "test_unmarked.py").write_text(
        "def test_forgot_the_marker() -> None:\n    assert True\n"
    )
    result = run_in(project, "just", "fuzz", check=False)
    assert result.returncode != 0
    assert "must set the property marker" in (result.stdout + result.stderr)


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
    assert agents.count("\n") < 80  # instruction budget
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


def test_semgrep_runs_hermetically(render, tmp_path: Path) -> None:
    """semgrep uses only the vendored config: telemetry off, no registry `auto`.

    `--config auto` is non-hermetic (its ruleset drifts) and, fatally, semgrep
    refuses it when metrics are off; the vendored .semgrep.yml keeps scans
    deterministic and offline. ruff's `S` rules cover the bandit baseline.
    """
    project = render({**MINIMAL, "enable_scanners": True}, tmp_path / "out")
    justfile = (project / "justfile").read_text()
    scan = (project / ".github" / "workflows" / "scan.yml").read_text()
    for text in (justfile, scan):
        semgrep_line = next(
            line for line in text.splitlines() if "semgrep" in line and "scan" in line
        )
        assert "--metrics=off" in semgrep_line
        assert "--config auto" not in semgrep_line
        assert "--config .semgrep.yml" in semgrep_line


def test_scan_recipe_blocks_violations(render, tmp_path: Path) -> None:
    """`just scan` actually runs semgrep and blocks on a real violation.

    The vendored no-eval rule fires before the gitleaks step, so this needs no
    gitleaks binary — it proves the recipe is wired, not merely present.
    """
    project = render({**MINIMAL, "enable_scanners": True}, tmp_path / "out")
    (project / "src" / "demo_project" / "danger.py").write_text(
        "def run(expr: str) -> object:\n    return eval(expr)\n"
    )
    result = run_in(project, "just", "scan", check=False)
    assert result.returncode != 0
    assert "eval" in (result.stdout + result.stderr).lower()


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


def test_mutate_recipe_executes_mutants(render, tmp_path: Path) -> None:
    """`just mutate` generates AND runs mutants, not leaving them "not checked".

    A broken mutmut config (e.g. unloading pytest-cov while addopts still passes
    --cov) silently leaves every mutant unchecked while the recipe exits 0.
    """
    project = render({**MINIMAL, "enable_mutation_tests": True}, tmp_path / "out")
    result = run_in(project, "just", "mutate")
    out = result.stdout + result.stderr
    assert "not checked" not in out
    assert "survived" in out or "killed" in out


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


def test_ci_fuzz_uses_ci_profile(render, tmp_path: Path) -> None:
    """Generated CI runs the property suite at `ci` strength, not the dev default.

    Without this the registered 300-example `ci` Hypothesis profile is unreachable —
    `just fuzz` defaults HYPOTHESIS_PROFILE to `dev`, so CI would fuzz at 25 examples.
    """
    on = render({**MINIMAL, "enable_property_tests": True}, tmp_path / "on")
    ci = yaml.safe_load((on / ".github" / "workflows" / "ci.yml").read_text())
    run_step = next(s for s in ci["jobs"]["ci"]["steps"] if s.get("run") == "just ci")
    assert run_step["env"]["HYPOTHESIS_PROFILE"] == "ci"
    # No dead env wiring when the property layer is off.
    off = render(MINIMAL, tmp_path / "off")
    assert "HYPOTHESIS_PROFILE" not in (off / ".github" / "workflows" / "ci.yml").read_text()


def test_ci_gitleaks_scans_history(render, tmp_path: Path) -> None:
    """CI gitleaks walks commit history, not just the working tree.

    The checkout uses fetch-depth: 0; `gitleaks dir` would ignore history and let a
    committed-then-deleted secret escape, making the full clone wasted and misleading.
    """
    project = render({**MINIMAL, "enable_scanners": True}, tmp_path / "out")
    scan = (project / ".github" / "workflows" / "scan.yml").read_text()
    yaml.safe_load(scan)  # valid YAML after the multi-line gitleaks run block
    assert "gitleaks git ." in scan
    assert "gitleaks dir" not in scan
    assert "fetch-depth: 0" in scan


def test_sha_pin_policy(render, tmp_path: Path) -> None:
    full = {**MINIMAL, "enable_policy_tests": True, "enable_sha_pin_policy": True}
    project = render(full, tmp_path / "out")
    run_in(project, "uv", "run", "pytest", "--no-cov", "tests/policy")
    assert "test_actions_are_sha_pinned" in (project / "tests" / "policy" / "test_gates.py").read_text()


def test_sha_pin_audit_ships_without_policy_tests(render, tmp_path: Path) -> None:
    """enable_sha_pin_policy ships the zizmor CI audit unconditionally, but the SHA-pin
    *policy test* lives in tests/policy/ and needs enable_policy_tests — the toggles are
    independent. The README must not promise the test when only the audit ships.
    """
    audit_only = render(
        {**MINIMAL, "enable_sha_pin_policy": True, "enable_policy_tests": False},
        tmp_path / "audit_only",
    )
    # scan.yml exists here solely because sha_pin is on; the zizmor step is present.
    assert "zizmor" in (audit_only / ".github" / "workflows" / "scan.yml").read_text()
    # ...but with no policy suite, the SHA-pin policy test does not ship.
    assert not (audit_only / "tests" / "policy").exists()

    # With the policy layer also on, the SHA-pin policy test ships.
    both = render(
        {**MINIMAL, "enable_sha_pin_policy": True, "enable_policy_tests": True},
        tmp_path / "both",
    )
    assert "test_actions_are_sha_pinned" in (
        (both / "tests" / "policy" / "test_gates.py").read_text()
    )


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


@pytest.mark.parametrize("version", ["3.11", "3.12", "3.13"])
def test_python_version_wiring(render, tmp_path: Path, version: str) -> None:
    project = render({**MINIMAL, "python_version": version}, tmp_path / version)
    pyproject = (project / "pyproject.toml").read_text()
    assert f'requires-python = ">={version}"' in pyproject
    assert f'target-version = "py{version.replace(".", "")}"' in pyproject
    assert f'pythonVersion = "{version}"' in pyproject


@pytest.mark.parametrize("floor", [0, 150])
def test_coverage_floor_out_of_range_is_rejected(render, tmp_path: Path, floor: int) -> None:
    """A floor outside 1..100 must be rejected at answer time, not silently rendered.

    fail_under <= 0 turns the coverage gate into a silent no-op; > 100 makes it
    permanently unsatisfiable (coverage caps at 100). copier validates `data=` answers,
    so an out-of-range floor raises before any project is written.
    """
    with pytest.raises(ValueError, match="coverage_floor"):
        render({**MINIMAL, "coverage_floor": floor}, tmp_path / str(floor))


def test_tool_version_pins_have_no_drift(render, tmp_path: Path) -> None:
    """Tool versions duplicated across files must agree — catches one-sided bumps.

    Asserts the sites agree rather than hardcoding a version, so a legitimate bump
    needs no edit here while a drifted (one-sided) bump fails the gate.
    """
    project = render(FULL, tmp_path / "out")
    justfile = (project / "justfile").read_text()
    scan = (project / ".github" / "workflows" / "scan.yml").read_text()
    mise = (project / "mise.toml").read_text()
    ci = (project / ".github" / "workflows" / "ci.yml").read_text()
    mutation = (project / ".github" / "workflows" / "mutation.yml").read_text()

    def _versions_near(keyword: str, *texts: str) -> set[str]:
        return {
            v
            for text in texts
            for line in text.splitlines()
            if keyword in line
            for v in re.findall(r"\d+\.\d+\.\d+", line)
        }

    # semgrep: local recipe vs CI step; gitleaks: mise pin vs CI download URL/tarball.
    assert len(_versions_near("semgrep", justfile, scan)) == 1
    assert len(_versions_near("gitleaks", mise, scan)) == 1
    # uv tool: mise pin vs every setup-uv `version:` across the workflows.
    uv_versions = set(re.findall(r'uv = "(\d+\.\d+\.\d+)"', mise))
    for wf in (ci, scan, mutation):
        uv_versions |= set(re.findall(r'version: "(\d+\.\d+\.\d+)"', wf))
    assert len(uv_versions) == 1, f"uv version drift: {uv_versions}"


def test_license_rendering(render, tmp_path: Path) -> None:
    mit = render({**MINIMAL, "license": "MIT"}, tmp_path / "mit")
    mit_text = (mit / "LICENSE").read_text()
    assert "MIT License" in mit_text
    assert "WITHOUT WARRANTY OF ANY KIND" in mit_text  # full body, not truncated
    apache = render({**MINIMAL, "license": "Apache-2.0"}, tmp_path / "apache")
    assert "Licensed under the Apache License" in (apache / "LICENSE").read_text()
    prop = render({**MINIMAL, "license": "proprietary"}, tmp_path / "prop")
    assert "All rights reserved" in (prop / "LICENSE").read_text()
    assert "license =" not in (prop / "pyproject.toml").read_text()
    # No ellipsis placeholder ever ships in a rendered LICENSE.
    for variant in (mit, apache, prop):
        assert "\n...\n" not in (variant / "LICENSE").read_text()


def test_full_combo_gate_green(render, tmp_path: Path) -> None:
    """The gold-standard check: a fully-loaded project is green on `just ci`."""
    project = render(FULL, tmp_path / "full")
    run_in(project, "just", "ci")


@pytest.mark.parametrize("name", list(MATRIX))
def test_matrix(render, tmp_path: Path, name: str) -> None:
    project = render(MATRIX[name], tmp_path / name)
    # Fast subset for every combo; the full `just ci` is exercised by test_full_combo_gate_green.
    run_in(project, "just", "fmt-check")
    run_in(project, "just", "lint")
    run_in(project, "just", "typecheck")
