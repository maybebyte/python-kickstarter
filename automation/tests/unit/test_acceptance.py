"""Acceptance refusals with real preparation, gates and measured product execution."""

import shutil
from pathlib import Path

import pytest

from kickstarter_workflow.files import string_list
from kickstarter_workflow.records import Record, load, object_value, text
from kickstarter_workflow.workflow import Workflow
from tests.conftest import command


def _files(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mode & 0o777)
        for path in root.rglob("*")
        if path.is_file()
    }


def _commands(task: Path) -> list[Record]:
    return [load(path) for path in task.glob("run-*/**/*.json") if "argv" in load(path)]


def test_enclosing_home_is_refused_and_exact_root_preserves_external_state(
    tmp_path: Path, plan: Record, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    command("git", "init", "--quiet", "--template=", str(home), cwd=tmp_path)
    source = home / "project"
    _ = shutil.copytree(Path(text(plan, "source")), source, ignore=shutil.ignore_patterns(".git"))
    hooks = home / "global-hooks"
    hooks.mkdir()
    marker = home / "hook-executed"
    hook = hooks / "post-checkout"
    _ = hook.write_text(f"#!/bin/sh\n: > '{marker}'\n")
    hook.chmod(0o700)
    _ = (home / ".gitconfig").write_text(f"[core]\n\thooksPath = {hooks}\n")
    installation = home / ".local/bin/installed-tool"
    installation.parent.mkdir(parents=True)
    _ = installation.write_text("Existing installation; not a task dependency.\n")
    _ = (home / "unrelated.txt").write_text("Outside the declared source.\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(home / ".gitconfig"))
    request: Record = {**plan, "source": str(source)}
    workflow = Workflow(tmp_path / "state")
    before = _files(home)
    rejected = workflow.dispatch("prepare", request)
    assert rejected["status"] == "blocked", rejected
    task = tmp_path / "state/sample/one"
    assert not (task / "workspace").exists()
    assert not (task / "source.json").exists()
    assert any(item["cwd"] == str(source) and item["exit"] == 0 for item in _commands(task))
    assert _files(home) == before

    command("git", "init", "--quiet", "--template=", str(source), cwd=tmp_path)
    local_hook = source / ".git/hooks/pre-commit"
    local_hook.parent.mkdir()
    _ = local_hook.write_text("#!/bin/sh\nexit 0\n")
    local_hook.chmod(0o700)
    before = _files(home)
    accepted = workflow.dispatch("prepare", {**request, "task": "exact-root"})
    assert accepted["status"] == "prepared", accepted
    workspace = Path(text(accepted, "workspace"))
    assert workspace != source
    assert set(load(workspace.parent / "source.json")) == {"app.py", "test_app.py", "README.md"}
    assert not (workspace / ".git/hooks").exists()
    assert not marker.exists()
    assert _files(home) == before


def test_new_mode_refuses_unchanged_generated_example_tests(tmp_path: Path, plan: Record) -> None:
    request: Record = {
        **plan,
        "mode": "new",
        "source": str(tmp_path / "new-project"),
        "isolate_git": True,
        "mapping": [
            {
                "source": "src/sample/__init__.py",
                "target": "src/sample/__init__.py",
                "role": "source",
            },
            {
                "source": "tests/unit/test_example.py",
                "target": "tests/unit/test_example.py",
                "role": "test",
            },
        ],
        "repository_checks": [["just", "ci"]],
    }
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", request)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    example = (workspace / "tests/unit/test_example.py").read_bytes()
    rejected = workflow.dispatch("verify", request)
    assert rejected["status"] == "blocked", rejected
    assert "receipt" not in rejected
    assert (workspace / "tests/unit/test_example.py").read_bytes() == example
    assert not (tmp_path / "state/sample/one/receipts").exists()
    assert workflow.dispatch("status", request)["status"] == "blocked"


@pytest.mark.parametrize("failure", ["zero", "skipped", "inadequate"])
def test_measured_product_run_refuses_inadequate_evidence_after_real_ci_passes(
    tmp_path: Path, plan: Record, failure: str
) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    tests = workspace / "product/test_app.py"
    if failure == "inadequate":
        _ = (workspace / "tests/unit/test_control.py").write_bytes(tests.read_bytes())
        _ = tests.write_text(
            '"""A test that imports but does not exercise the product."""\n\nfrom app import twice\n\n\ndef test_import_only() -> None:\n    assert callable(twice)\n    assert twice.__name__ == "twice"\n    assert twice.__module__ == "app"\n'
        )
    else:
        _ = tests.write_text(
            '"""Module collection exercises the product, but no successful test does."""\n\n'
            + ("import pytest\n" if failure == "skipped" else "")
            + "from app import twice\n\nassert twice(3) == 6\n"
            + (
                '\n\n@pytest.mark.skip(reason="Explicit nonexecution fixture.")\ndef test_not_executed() -> None:\n    assert twice(3) == 6\n'
                if failure == "skipped"
                else ""
            )
        )
    result = workflow.dispatch("verify", plan)
    assert result["status"] == "blocked", result
    task = workspace.parent
    commands = _commands(task)
    assert any(string_list(item, "argv")[1:] == ["ci"] and item["exit"] == 0 for item in commands)
    product_runs = [
        item for item in commands if "--override-ini=addopts=" in string_list(item, "argv")
    ]
    assert len(product_runs) == 1
    assert product_runs[0]["exit"] == (5 if failure == "zero" else 0)
    evidence = Path(text(product_runs[0], "output")).parent
    junit = (evidence / "product-tests.xml").read_text()
    coverage = object_value(load(evidence / "product-coverage.json"), "files")
    summary = object_value(object_value(coverage, "product/app.py"), "summary")
    if failure == "zero":
        assert "<testcase " not in junit
    elif failure == "skipped":
        assert "<skipped " in junit
        assert summary["percent_covered"] == 100
    else:
        assert "<testcase " in junit
        assert float(str(summary["percent_covered"])) < 85
    assert "receipt" not in result
    assert not (task / "receipts").exists()
    assert workflow.dispatch("status", plan)["status"] == "blocked"
