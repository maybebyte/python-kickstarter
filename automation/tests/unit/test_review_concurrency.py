"""Force shared-record publication overlap in independent public workflow processes."""

import multiprocessing
import os
from multiprocessing.synchronize import Event
from pathlib import Path

import pytest

from kickstarter_workflow.records import Record, encoded, load
from kickstarter_workflow.workflow import Workflow


def _request(task: str) -> Record:
    return {
        "project": "sample",
        "task": task,
        "mode": "disposable",
        "reason": "bounded concurrency regression",
    }


def _prepare_child(root: Path, task: str, reached: Event, release: Event, done: Event) -> None:
    original = os.open
    pending = root / "sample/project.pending"
    lock = root / "sample/project.lock"

    def controlled_open(
        path: str | os.PathLike[str], flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        if task == "two" and Path(path) in {pending, lock}:
            reached.set()
        descriptor = original(path, flags, mode, dir_fd=dir_fd)
        if task == "one" and Path(path) == pending:
            reached.set()
            assert release.wait(10), "publication release timed out"
        return descriptor

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "open", controlled_open)
        result = Workflow(root).dispatch("prepare", _request(task))
    _ = (root.parent / (task + ".json")).write_bytes(encoded(result))
    done.set()


@pytest.mark.parametrize("attempt", range(3))
def test_independent_tasks_wait_for_shared_publication(tmp_path: Path, attempt: int) -> None:
    root = tmp_path / f"state-{attempt}"
    context = multiprocessing.get_context("fork")
    first, second, release, done_first, done_second = (context.Event() for _ in range(5))
    workers = [
        context.Process(target=_prepare_child, args=(root, "one", first, release, done_first)),
        context.Process(target=_prepare_child, args=(root, "two", second, release, done_second)),
    ]
    workers[0].start()
    try:
        assert first.wait(10), "first process did not reach its real pending write"
        workers[1].start()
        assert second.wait(10), "second process did not reach the shared record boundary"
        assert not done_second.wait(0.2), "second task falsely finished while publication was held"
    finally:
        release.set()
        for worker in workers:
            if worker.pid is not None:
                worker.join(10)
                if worker.is_alive():
                    worker.kill()
                    worker.join(10)
    assert [worker.exitcode for worker in workers] == [0, 0]
    for task in ("one", "two"):
        assert load(tmp_path / (task + ".json"))["status"] == "exempt"
        result = Workflow(root).dispatch("resume", _request(task))
        assert result["status"] == "exempt", result
        assert result["plan"] == _request(task)
    assert load(root / "sample/project.json")["latest_task"] == "two"
    assert not list(root.rglob("*.pending"))


@pytest.mark.parametrize("operation", ["status", "resume", "prepare", "cleanup"])
def test_abandoned_project_write_blocks_readiness_and_preserves_state(
    tmp_path: Path, operation: str
) -> None:
    root = tmp_path / "state"
    workflow = Workflow(root)
    request = _request("one")
    assert workflow.dispatch("prepare", request)["status"] == "exempt"
    project = root / "sample"
    before = (project / "one/task.json").read_bytes()
    pending = project / "project.pending"
    _ = pending.write_bytes(b"interrupted publication")
    result = workflow.dispatch(operation, request)
    assert result["status"] == "blocked", result
    assert pending.read_bytes() == b"interrupted publication"
    assert (project / "one/task.json").read_bytes() == before
