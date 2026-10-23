"""Reviewed selective return with three-way reconciliation and a recovery journal."""

import difflib
import os
import shutil
import uuid
from pathlib import Path

from kickstarter_workflow.files import confined, copy_inventory, inventory, mappings, string_list
from kickstarter_workflow.process import Runner
from kickstarter_workflow.records import (
    Record,
    Value,
    WorkflowError,
    digest,
    load,
    object_value,
    save,
    sync_directory,
    text,
)
from kickstarter_workflow.setup import git_root
from kickstarter_workflow.verification import (
    product_evidence,
    repository_checks,
    validate_receipt,
    verify,
)

SCAFFOLD = frozenset(
    {
        "pyproject.toml",
        "uv.lock",
        "justfile",
        "AGENTS.md",
        ".copier-answers.yml",
        ".pre-commit-config.yaml",
        "coverage.xml",
    }
)


def _review(state: Record, review: Record) -> list[str]:
    _ = text(review, "reviewer")
    _ = text(review, "reason")
    if review.get("receipt") != state.get("receipt"):
        raise WorkflowError("review does not bind the verified candidate")
    allowlist = string_list(review, "allowlist")
    permitted = {text(item, "source") for item in mappings(object_value(state, "plan"))}
    if len(allowlist) != len(set(allowlist)) or not set(allowlist).issubset(permitted):
        raise WorkflowError("return requires a unique explicit mapped product allowlist")
    if any(name in SCAFFOLD or name.startswith((".git", ".github", ".venv")) for name in allowlist):
        raise WorkflowError("scaffolding adoption requires a separate assignment")
    return allowlist


def _merge(item: Record, state: Record, task: Path, runner: Runner) -> bytes:
    plan = object_value(state, "plan")
    source = confined(Path(text(plan, "source")), text(item, "source"))
    baseline = confined(task / "baseline", text(item, "source"))
    candidate = confined(Path(text(state, "workspace")), text(item, "target"))
    if (
        candidate.stat().st_mode != baseline.stat().st_mode
        and source.stat().st_mode != baseline.stat().st_mode
        and candidate.stat().st_mode != source.stat().st_mode
    ):
        raise WorkflowError("conflicting destination mode change requires a decision")
    if source.read_bytes() == baseline.read_bytes():
        return candidate.read_bytes()
    if candidate.read_bytes() == baseline.read_bytes():
        return source.read_bytes()
    _ = runner.run(
        ["git", "merge-file", "-p", str(candidate), str(baseline), str(source)],
        task,
        allow_failure=True,
    )
    if runner.last_exit:
        raise WorkflowError("destination conflict requires a decision; no files transferred")
    return runner.last_output.read_bytes()


def _reconcile(state: Record, task: Path, runner: Runner) -> tuple[Record, bool]:
    plan = object_value(state, "plan")
    source = Path(text(plan, "source"))
    before = load(task / "source.json")
    current = inventory(source)
    if current == before:
        return state, False
    merged: list[tuple[Path, bytes, int]] = []
    workspace = Path(text(state, "workspace"))
    candidate_inventory = inventory(workspace)
    for item in mappings(plan):
        name, target = text(item, "source"), text(item, "target")
        if current.get(name) == before.get(name):
            continue
        if name not in before or name not in current:
            raise WorkflowError("destination add/delete conflict requires a decision")
        data = _merge(item, state, task, runner)
        mode = object_value(candidate_inventory, target)["mode"]
        if mode == object_value(before, name)["mode"]:
            mode = object_value(current, name)["mode"]
        merged.append((confined(workspace, target), data, int(str(mode))))
    diff = _candidate_diff(merged)
    for path, data, mode in merged:
        _ = path.write_bytes(data)
        path.chmod(mode)
    _ = (task / "baseline").rename(task / ("baseline-" + uuid.uuid4().hex))
    (task / "baseline").mkdir(mode=0o700)
    copy_inventory(source, task / "baseline", current)
    save(task / "source.json", current)
    state = {**state, "source_sha256": digest((task / "source.json").read_bytes())}
    updated = verify(state, task, runner.child())
    if inventory(workspace) != candidate_inventory:
        report = task / ("reconciliation-" + text(updated, "receipt") + ".diff")
        _ = report.write_text(diff)
        updated.update(
            {
                "status": "review_required",
                "reason": "reconciled candidate requires receipt-bound host intent review before return",
                "reconciliation_diff": str(report),
                "previous_receipt": state.get("receipt"),
                "reconciled": True,
            }
        )
    save(task / "task.json", updated)
    return updated, True


def _candidate_diff(merged: list[tuple[Path, bytes, int]]) -> str:
    lines: list[str] = []
    for path, data, mode in merged:
        lines.append(f"{path}: mode {path.stat().st_mode & 0o777:o} -> {mode:o}\n")
        lines.extend(
            difflib.unified_diff(
                path.read_text(errors="replace").splitlines(keepends=True),
                data.decode(errors="replace").splitlines(keepends=True),
                fromfile="reviewed/" + path.name,
                tofile="reconciled/" + path.name,
            )
        )
    return "".join(lines)


def _journal(
    state: Record, review: Record, allowlist: list[str], task: Path, *, reconciled: bool
) -> Record:
    plan = object_value(state, "plan")
    source, workspace = Path(text(plan, "source")), Path(text(state, "workspace"))
    current, candidate = inventory(source), inventory(workspace)
    entries: Record = {}
    for item in mappings(plan):
        name, target = text(item, "source"), text(item, "target")
        if current.get(name) != candidate.get(target) and name not in allowlist:
            raise WorkflowError("changed mapped files are missing from the reviewed allowlist")
        if name in allowlist:
            entries[name] = {
                "before": current.get(name),
                "after": candidate.get(target),
                "target": target,
            }
    journal: Record = {
        "status": "transferring",
        "entries": entries,
        "destination_before": current,
        "review": review,
        "state": state,
        "reconciled": reconciled,
        "applied": [],
    }
    save(task / "return.json", journal)
    return journal


def _replace(candidate: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / (".kickstarter-return-" + uuid.uuid4().hex)
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        candidate.stat().st_mode & 0o777,
    )
    with os.fdopen(descriptor, "wb") as stream:
        _ = stream.write(candidate.read_bytes())
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(candidate.stat().st_mode & 0o777)
    _ = temporary.replace(destination)
    sync_directory(destination.parent)


def effects(journal: Record) -> list[str]:
    """Report actual applied paths even after interruption before a journal update."""
    state = object_value(journal, "state")
    source = Path(text(object_value(state, "plan"), "source"))
    current = inventory(source)
    return [
        name
        for name, entry in object_value(journal, "entries").items()
        if isinstance(entry, dict) and current.get(name) == entry.get("after")
    ]


def _apply(journal: Record, task: Path) -> None:
    state = object_value(journal, "state")
    source = Path(text(object_value(state, "plan"), "source"))
    workspace = Path(text(state, "workspace"))
    entries = object_value(journal, "entries")
    current = inventory(source)
    for name in entries:
        entry = object_value(entries, name)
        if current.get(name) not in (entry.get("before"), entry.get("after")):
            raise WorkflowError("destination changed during interrupted return; decision required")
    for name in entries:
        entry = object_value(entries, name)
        fresh = inventory(source).get(name)
        if fresh == entry.get("after"):
            continue
        if fresh != entry.get("before"):
            raise WorkflowError("destination changed immediately before transfer")
        _replace(confined(workspace, text(entry, "target")), confined(source, name))
        journal["applied"] = list(effects(journal))
        save(task / "return.json", journal)


def return_product(state: Record, request: Record, task: Path, runner: Runner) -> Record:
    """Return reviewed files, or recover an interrupted transfer without blind writes."""
    plan = object_value(state, "plan")
    if plan["mode"] == "new":
        raise WorkflowError("new projects already occupy their destination; no copy-back operation")
    review = object_value(request, "review")
    path = task / "return.json"
    if path.exists():
        journal = load(path)
        if journal.get("review") != review:
            raise WorkflowError("interrupted return review differs; explicit decision required")
        state = object_value(journal, "state")
        _ = validate_receipt(state, task, runner)
    else:
        if state["status"] not in {"verified", "review_required"}:
            raise WorkflowError("return requires successful current verification")
        allowlist = _review(state, review)
        _ = validate_receipt(state, task, runner)
        git_root(runner, Path(text(plan, "source")))
        previous_receipt = state.get("receipt")
        state, reconciled = _reconcile(state, task, runner)
        if state["status"] == "review_required" and state.get("receipt") != previous_receipt:
            return state
        journal = _journal(
            state,
            review,
            allowlist,
            task,
            reconciled=reconciled or state.get("reconciled") is True,
        )
    save(task / "task.json", {**state, "status": "returning"})
    _apply(journal, task)
    return _validate_destination(journal, task, runner)


def _require_inventory(actual: Record, expected: Record) -> None:
    if actual != expected:
        raise WorkflowError("destination differs from reviewed payload or unrelated files")


def _validate_destination(journal: Record, task: Path, runner: Runner) -> Record:
    state = object_value(journal, "state")
    plan = object_value(state, "plan")
    source, workspace = Path(text(plan, "source")), Path(text(state, "workspace"))
    before = inventory(source)
    transferred = effects(journal)
    expected = dict(object_value(journal, "destination_before"))
    entries = object_value(journal, "entries")
    expected.update({name: object_value(entries, name)["after"] for name in entries})
    journal["destination_before_checks"] = before
    journal["transferred"] = list(transferred)
    save(task / "return.json", journal)
    try:
        _require_inventory(before, expected)
        repository_checks(plan, source, workspace, runner)
        measured = product_evidence(plan, source, workspace, runner, destination=True)
        _require_inventory(inventory(source), before)
        _ = validate_receipt(state, task, runner)
    except (WorkflowError, OSError, ValueError) as error:
        current = inventory(source)
        changes: list[Value] = [
            name
            for name in sorted(before.keys() | current.keys())
            if before.get(name) != current.get(name)
        ]
        result: Record = {
            **state,
            "status": "blocked",
            "reason": str(error),
            "destination_validated": False,
            "transferred": list(transferred),
            "applied": list(effects(journal)),
            "destination_changes": changes,
        }
        journal.update(result)
        journal["destination_before_checks"] = before
        journal["destination"] = current
        journal["destination_evidence"] = str(runner.evidence)
        save(task / "return.json", journal)
        return result
    journal.update(
        {
            "status": "returned",
            "applied": list(effects(journal)),
            "destination": inventory(source),
            "destination_evidence": str(runner.evidence),
        }
    )
    save(task / "return.json", journal)
    return {
        **state,
        **measured,
        "status": "returned",
        "destination_validated": True,
        "reconciled": journal["reconciled"],
        "applied": journal["applied"],
    }


def cleanup(state: Record, task: Path) -> Record:
    """Remove resolved task workspace only; retain records and raw diagnostics."""
    if state["status"] not in {"returned", "exempt", "cleaned"}:
        raise WorkflowError("unresolved work must be preserved")
    workspace = task / "workspace"
    if workspace.exists():
        _ = inventory(workspace)
        shutil.rmtree(workspace)
    return {**state, "status": "cleaned"}
