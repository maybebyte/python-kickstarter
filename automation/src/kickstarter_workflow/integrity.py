"""Validate retained preparation independently of mutable product edits."""

import os
from pathlib import Path

from kickstarter_workflow.environment import environment_identity
from kickstarter_workflow.files import inventory
from kickstarter_workflow.git_context import validate
from kickstarter_workflow.process import Runner
from kickstarter_workflow.records import (
    Record,
    WorkflowError,
    digest,
    load,
    no_links,
    object_value,
    private_directory,
    text,
)
from kickstarter_workflow.setup import git_root, template


def validate_preparation(state: Record, task: Path, runner: Runner) -> None:
    """Refuse missing or modified provenance while preserving unresolved work."""
    plan = object_value(state, "plan")
    workspace = Path(text(state, "workspace"))
    source = no_links(Path(text(plan, "source")))
    git_root(runner, source)
    for name in ("source", "scaffold"):
        path = task / (name + ".json")
        metadata = path.stat()
        if (
            metadata.st_mode & 0o777 != 0o600
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
        ):
            raise WorkflowError("retained preparation record must be private")
        if digest(path.read_bytes()) != state.get(name + "_sha256"):
            raise WorkflowError("stale preparation inventory: " + name)
    if plan["mode"] != "new":
        if not (task / "baseline").is_dir():
            raise WorkflowError("retained baseline is missing")
        private_directory(task / "baseline")
        if inventory(task / "baseline", plan, destination=True) != load(task / "source.json"):
            raise WorkflowError("retained baseline is missing or changed")
    git_root(runner, workspace)
    validate(state, task, runner)
    if environment_identity(workspace) != state.get("environment"):
        raise WorkflowError("stale prepared environment")
    _, revision = template(plan, runner)
    if revision != state.get("template_revision") or runner.identities(task) != state.get("tools"):
        raise WorkflowError("stale setup provenance")
    baseline, current = load(task / "scaffold.json"), inventory(workspace, plan)
    protected = {
        name
        for name in baseline
        if name
        in {
            "justfile",
            "pyproject.toml",
            ".copier-answers.yml",
            "uv.lock",
            ".python-version",
            "product/pyproject.toml",
        }
        or name.startswith("tests/policy/")
    }
    if any(current.get(name) != baseline[name] for name in protected):
        raise WorkflowError(
            "stale prepared gate configuration changed or weakened; prepare a new plan"
        )
