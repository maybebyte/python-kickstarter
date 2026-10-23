"""Workflow behavior through its public request interface."""

import shutil
from pathlib import Path

import pytest

from kickstarter_workflow.records import Record, object_value, text
from kickstarter_workflow.workflow import Workflow


@pytest.mark.parametrize("project_type", ["application", "library"])
def test_new_projects_generate_and_existing_projects_reuse_without_upgrade(
    tmp_path: Path, plan: Record, project_type: str
) -> None:
    new: Record = {
        **plan,
        "mode": "new",
        "source": str(tmp_path / "new-project"),
        "isolate_git": True,
    }
    new["answers"] = {**object_value(plan, "answers"), "project_type": project_type}
    new["mapping"] = [
        {"source": "src/sample/__init__.py", "target": "src/sample/__init__.py", "role": "source"},
        {
            "source": "tests/unit/test_example.py",
            "target": "tests/unit/test_example.py",
            "role": "test",
        },
    ]
    new["repository_checks"] = [["just", "ci"]]
    workflow = Workflow(tmp_path / "state")
    result = workflow.dispatch("prepare", new)
    assert result["status"] == "prepared", result
    assert result["workspace"] == new["source"]
    workspace = Path(text(new, "source"))
    answers = (workspace / ".copier-answers.yml").read_bytes()
    _ = (workspace / "README.md").write_text("Existing project ownership.\n")
    reuse: Record = {**new, "mode": "existing", "task": "reuse"}
    reused = workflow.dispatch("prepare", reuse)
    assert reused["status"] == "prepared", reused
    isolated = Path(str(reused["workspace"]))
    assert isolated != workspace
    assert (isolated / ".copier-answers.yml").read_bytes() == answers
    assert (isolated / "README.md").read_text() == "Existing project ownership.\n"
    assert (workspace / "README.md").read_text() == "Existing project ownership.\n"


def test_workbench_copies_product_and_retains_real_copier_provenance(
    tmp_path: Path, plan: Record
) -> None:
    workflow = Workflow(tmp_path / "state")
    result = workflow.dispatch("prepare", plan)
    assert result["status"] == "prepared", result
    workspace = Path(str(result["workspace"]))
    source = Path(text(plan, "source"))
    assert (workspace / "product/app.py").read_bytes() == (source / "app.py").read_bytes()
    answers = (workspace / ".copier-answers.yml").read_text()
    assert "_commit:" in answers
    assert result["template_revision"] == "37adbeeea53a242ed25db602a35b9d719d95c8ae"
    assert not (workspace / ".git/hooks").exists()
    assert not (source / "pyproject.toml").exists()
    assert workflow.dispatch("resume", plan)["workspace"] == str(workspace)
    other = workflow.dispatch("prepare", {**plan, "task": "two"})
    assert other["status"] == "prepared", other
    assert other["workspace"] != result["workspace"]


def test_verify_runs_real_template_repository_and_product_gates(
    tmp_path: Path, plan: Record
) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    verified = workflow.dispatch("verify", plan)
    assert verified["status"] == "verified", verified
    assert int(str(verified["product_tests"])) >= 1
    assert verified["product_coverage"] == 100
    receipt = verified["receipt"]
    assert workflow.dispatch("status", plan)["receipt"] == receipt
    workspace = Path(str(prepared["workspace"]))
    _ = (workspace / "product/app.py").write_text('raise RuntimeError("candidate changed")\n')
    stale = workflow.dispatch("status", plan)
    assert stale["status"] == "blocked"
    assert "stale" in text(stale, "reason")


def test_reviewed_return_preserves_unrelated_files_and_validates_destination(
    tmp_path: Path, plan: Record
) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    workspace = Path(str(prepared["workspace"]))
    source = Path(text(plan, "source"))
    app = workspace / "product/app.py"
    _ = app.write_text(app.read_text().replace("value * 2", "value + value"))
    verified = workflow.dispatch("verify", plan)
    assert verified["status"] == "verified", verified
    _ = (source / "unrelated.txt").write_text("Other task owns this.\n")
    request: Record = {
        "project": "sample",
        "task": "one",
        "review": {
            "receipt": verified["receipt"],
            "reviewer": "independent-test-review",
            "allowlist": ["app.py"],
            "reason": "Equivalent expression reviewed.",
        },
    }
    result = workflow.dispatch("return", request)
    assert result["status"] == "returned", result
    assert result["destination_validated"] is True
    assert "value + value" in (source / "app.py").read_text()
    assert (source / "unrelated.txt").read_text() == "Other task owns this.\n"
    assert not (source / "pyproject.toml").exists()
    assert result["reconciled"] is True


def test_receipt_is_invalidated_when_the_executed_interpreter_changes(
    tmp_path: Path, plan: Record
) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    verified = workflow.dispatch("verify", plan)
    assert verified["status"] == "verified", verified
    interpreter = Path(text(prepared, "workspace")) / ".venv/bin/python"
    assert interpreter.is_symlink()
    original = interpreter.readlink()
    alternate = tmp_path / "alternate-python"
    _ = shutil.copy2(interpreter.resolve(), alternate)
    try:
        interpreter.unlink()
        interpreter.symlink_to(alternate)
        stale = workflow.dispatch("status", plan)
        assert stale["status"] == "blocked", stale
        assert "stale" in text(stale, "reason")
    finally:
        interpreter.unlink()
        interpreter.symlink_to(original)
    assert workflow.dispatch("status", plan)["status"] == "verified"


def test_disposable_exemption_is_durable_but_not_verification(tmp_path: Path) -> None:
    workflow = Workflow(tmp_path / "state")
    request: Record = {
        "project": "sample",
        "task": "one",
        "mode": "disposable",
        "reason": "one-off diagnostic",
    }
    result = workflow.dispatch("prepare", request)
    assert result["status"] == "exempt"
    assert workflow.dispatch("resume", request)["status"] == "exempt"
    assert workflow.dispatch("verify", request)["status"] == "blocked"
    assert workflow.dispatch("return", request)["status"] == "blocked"
