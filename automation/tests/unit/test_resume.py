"""Prepared readiness requires intact retained state, not just three files."""

import shutil
from pathlib import Path

import pytest

from kickstarter_workflow.records import Record, text
from kickstarter_workflow.workflow import Workflow


@pytest.mark.parametrize(
    "damage",
    [
        "source-missing",
        "source-corrupt",
        "baseline-missing",
        "baseline-tampered",
        "git",
        "policy",
        "scaffold",
    ],
)
def test_resume_revalidates_complete_preparation(tmp_path: Path, plan: Record, damage: str) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    task = workspace.parent
    product = workspace / "product/app.py"
    _ = product.write_text(product.read_text().replace("value * 2", "value + value"))
    assert workflow.dispatch("resume", plan)["status"] == "prepared"
    assert workflow.dispatch("prepare", plan)["status"] == "prepared"
    if damage == "source-missing":
        (task / "source.json").unlink()
    elif damage == "source-corrupt":
        _ = (task / "source.json").write_text("{}\n")
    elif damage == "baseline-missing":
        shutil.rmtree(task / "baseline")
    elif damage == "baseline-tampered":
        _ = (task / "baseline/app.py").write_text("unreviewed baseline\n")
    elif damage == "git":
        shutil.rmtree(workspace / ".git")
    elif damage == "scaffold":
        _ = (task / "scaffold.json").write_text("{}\n")
    else:
        _ = (workspace / "justfile").write_text("ci:\n    true\n")
    for operation in ("resume", "prepare"):
        rejected = workflow.dispatch(operation, plan)
        assert rejected["status"] == "blocked", rejected
    assert "value + value" in product.read_text()
    assert (task / "task.json").is_file()


def test_resume_refuses_lost_prepared_environment(tmp_path: Path, plan: Record) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    shutil.rmtree(workspace / ".venv")
    for operation in ("resume", "prepare"):
        result = workflow.dispatch(operation, plan)
        assert result["status"] == "blocked", result
    assert (workspace / "product/app.py").is_file()
