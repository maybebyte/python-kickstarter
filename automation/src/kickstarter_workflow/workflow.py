"""Task-owned Python development workflow."""

import fcntl
import os
import uuid
from pathlib import Path

from kickstarter_workflow.files import confined
from kickstarter_workflow.integrity import validate_preparation
from kickstarter_workflow.process import Runner
from kickstarter_workflow.records import (
    Record,
    WorkflowError,
    identifier,
    load,
    object_value,
    private_directory,
    project_record,
    save,
    text,
)
from kickstarter_workflow.setup import prepare
from kickstarter_workflow.transfer import cleanup, effects, return_product
from kickstarter_workflow.verification import validate_receipt, verify


class Workflow:
    """Prepare and validate isolated work without granting publication authority."""

    def __init__(self, state_root: Path) -> None:
        """Select an external durable state directory."""
        self.state_root: Path = state_root

    def _task(self, request: Record) -> Path:
        if "source" in request:
            source = Path(text(request, "source")).resolve()
            if self.state_root.resolve().is_relative_to(source) or source.is_relative_to(
                self.state_root.resolve()
            ):
                raise WorkflowError("source and external state must be separate")
        private_directory(self.state_root)
        project = self.state_root / identifier(request, "project")
        private_directory(project)
        task = project / identifier(request, "task")
        private_directory(task)
        return task

    def dispatch(self, operation: str, request: Record) -> Record:
        """Execute one workflow operation and return a structured outcome."""
        try:
            task = self._task(request)
            descriptor = os.open(task / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "w"):
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self._operate(operation, request, task)
        except (WorkflowError, OSError, ValueError) as error:
            return {"status": "blocked", "reason": str(error)}

    def _runner(self, plan: Record, task: Path) -> Runner:
        return Runner(
            object_value(plan, "tools"),
            task / ("run-" + uuid.uuid4().hex),
            self.state_root / "cache",
        )

    def _read_state(self, task: Path) -> Record:
        path = task / "task.json"
        metadata = path.stat()
        if (
            metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o777 != 0o600
            or metadata.st_nlink != 1
        ):
            raise WorkflowError("task record must be private and independently owned")
        state = load(path)
        plan = object_value(state, "plan")
        if identifier(plan, "task") != task.name or identifier(plan, "project") != task.parent.name:
            raise WorkflowError("task ownership mismatch")
        status = text(state, "status")
        if status in {"exempt", "preparing", "cleaned"}:
            return state
        workspace = Path(text(state, "workspace"))
        expected = Path(text(plan, "source")) if plan.get("mode") == "new" else task / "workspace"
        if workspace != expected or not all(
            confined(workspace, name).is_file()
            for name in (".copier-answers.yml", "pyproject.toml", "justfile")
        ):
            raise WorkflowError("workspace ownership or setup artifacts are missing")
        validate_preparation(state, task, self._runner(plan, task))
        return state

    def _operate(self, operation: str, request: Record, task: Path) -> Record:
        record = task / "task.json"
        project_record(task.parent)
        if any(task.glob("*.pending")):
            raise WorkflowError("pending state write requires explicit recovery; work preserved")
        if operation == "prepare":
            return self._prepare(request, task)
        state = self._read_state(task)
        plan = object_value(state, "plan")
        if "mode" in request and request != plan:
            raise WorkflowError("task plan changed; do not share mutable task ownership")
        if operation in {"resume", "status"}:
            return self._status(state, task)
        if operation == "cleanup":
            result = cleanup(state, task)
            save(record, result)
            return result
        if "workspace" not in state:
            raise WorkflowError("operation requires prepared production workspace")
        if operation == "verify":
            save(record, {**state, "status": "verifying"})
            try:
                result = verify(state, task, self._runner(plan, task))
            except (WorkflowError, OSError, ValueError) as error:
                save(record, {**state, "status": "blocked", "reason": str(error)})
                raise
            save(record, result)
            return result
        if operation == "return":
            result = return_product(state, request, task, self._runner(plan, task))
            save(record, result)
            return result
        raise WorkflowError("unsupported operation")

    def _status(self, state: Record, task: Path) -> Record:
        if state["status"] in {"verified", "review_required"}:
            _ = validate_receipt(state, task, self._runner(object_value(state, "plan"), task))
        if state["status"] == "returning":
            return {
                **state,
                "applied": list(effects(load(task / "return.json"))),
                "reason": "interrupted return; retry validates actual effects",
            }
        return state

    def _prepare(self, request: Record, task: Path) -> Record:
        record = task / "task.json"
        if record.exists():
            previous = load(record)
            if previous.get("plan") == request:
                return self._operate("resume", request, task)
            if previous.get("status") != "exempt" or request.get("mode") == "disposable":
                raise WorkflowError("task plan changed; prepare a separate task")
            save(task / ("exemption-" + uuid.uuid4().hex + ".json"), previous)
        if text(request, "mode") == "disposable":
            result: Record = {
                "status": "exempt",
                "reason": text(request, "reason"),
                "plan": request,
            }
        else:
            save(
                record,
                {
                    "status": "preparing",
                    "plan": request,
                    "reason": "setup incomplete; preserve partial work",
                },
            )
            result = prepare(request, task, self._runner(request, task))
        save(record, result)
        project_record(
            task.parent,
            {
                "project": text(request, "project"),
                "latest_task": text(request, "task"),
                "mapping": request.get("mapping"),
                "source": request.get("source"),
            },
        )
        return result
