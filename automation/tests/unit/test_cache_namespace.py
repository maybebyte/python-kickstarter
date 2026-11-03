"""Project and task names never become tool cache storage."""

from pathlib import Path

import pytest

from kickstarter_workflow.records import Record, load, text
from kickstarter_workflow.workflow import Workflow


@pytest.mark.parametrize("task_name", ["uv", "python", "tmp", "ordinary-task"])
def test_cache_project_tasks_do_not_alias_internal_storage(
    tmp_path: Path, plan: Record, monkeypatch: pytest.MonkeyPatch, task_name: str
) -> None:
    monkeypatch.delenv("TMPDIR", raising=False)
    request: Record = {
        **plan,
        "project": "cache",
        "task": task_name,
        "repository_checks": [["uv", "cache", "dir"], ["uv", "python", "dir"]],
    }
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", request)
    assert prepared["status"] == "prepared", prepared
    verified = workflow.dispatch("verify", request)
    assert verified["status"] == "verified", verified
    task = Path(text(prepared, "workspace")).parent
    locations: dict[str, Path] = {}
    for path in task.glob("run-*/**/*.json"):
        record = load(path)
        argv = record.get("argv")
        if isinstance(argv, list) and argv[1:] in (["cache", "dir"], ["python", "dir"]):
            assert record["exit"] == 0
            locations[str(argv[1])] = Path(Path(text(record, "output")).read_text().strip())
    assert set(locations) == {"cache", "python"}
    assert all(not path.is_relative_to(tmp_path / "state/cache") for path in locations.values())
    assert workflow.dispatch("resume", request)["receipt"] == verified["receipt"]
