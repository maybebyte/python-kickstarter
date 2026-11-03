"""Disposable Git discovery over the complete measured candidate."""

from pathlib import Path

from kickstarter_workflow.process import Runner
from kickstarter_workflow.records import (
    Record,
    WorkflowError,
    digest,
    load,
    object_value,
    save,
    text,
)


def _complete_history(root: Path, runner: Runner) -> None:
    runner.env["GIT_NO_LAZY_FETCH"] = "1"
    if runner.run(["git", "rev-parse", "--is-shallow-repository"], root) != "false":
        raise WorkflowError("shallow Git history is unsupported; provide complete local history")
    _ = runner.run(
        ["git", "config", "--local", "--get", "extensions.partialClone"], root, allow_failure=True
    )
    if runner.last_exit == 0:
        raise WorkflowError("partial Git clones are unsupported")
    common = Path(
        runner.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], root)
    )
    if (common / "info/grafts").exists():
        raise WorkflowError("rewritten Git history via grafts is unsupported")


def history(root: Path, runner: Runner) -> Record:
    """Identify local reachable history and refs, never the caller's mutable index."""
    _complete_history(root, runner)
    head = runner.run(["git", "rev-parse", "--verify", "--quiet", "HEAD"], root, allow_failure=True)
    if runner.last_exit:
        head = ""
    branch = runner.run(["git", "symbolic-ref", "--quiet", "HEAD"], root, allow_failure=True)
    if runner.last_exit:
        branch = ""
    refs: Record = {}
    output = runner.run(
        ["git", "for-each-ref", "--format=%(refname) %(objectname) %(symref)"], root
    )
    for line in output.splitlines():
        name, oid, *symbolic = line.split()
        if name.startswith("refs/replace/"):
            raise WorkflowError("replacement Git objects are unsupported")
        refs[name] = {"oid": oid, "symbolic": symbolic[0] if symbolic else ""}
    return {"head": head, "branch": branch, "refs": refs}


def identity(root: Path, runner: Runner) -> Record:
    """Bind semantic Git inputs without volatile index stat-cache bytes."""
    _ = runner.run(["git", "ls-files", "--stage", "-z"], root)
    index = digest(runner.last_output.read_bytes())
    return {**history(root, runner), "index": index}


def retain(source: Path, task: Path, runner: Runner) -> str:
    """Freeze complete reachable local history without cloning config or hooks."""
    before = history(source, runner)
    bundle = task / "repository.bundle"
    if before["head"] or before["refs"]:
        revisions = ["--all", "HEAD"] if before["head"] else ["--all"]
        _ = runner.run(["git", "bundle", "create", str(bundle), *revisions], source)
        _ = runner.run(["git", "bundle", "verify", str(bundle)], source)
    if history(source, runner) != before:
        raise WorkflowError("source Git history changed during preparation")
    record: Record = {
        "history": before,
        "bundle": digest(bundle.read_bytes()) if bundle.exists() else None,
    }
    path = task / "repository-git.json"
    save(path, record)
    return digest(path.read_bytes())


def validate(state: Record, task: Path, runner: Runner) -> None:
    """Refuse stale source refs and damaged retained Git context."""
    path = task / "repository-git.json"
    if digest(path.read_bytes()) != state.get("git_sha256"):
        raise WorkflowError("retained Git context changed")
    record = load(path)
    bundle = task / "repository.bundle"
    if (digest(bundle.read_bytes()) if bundle.exists() else None) != record.get("bundle"):
        raise WorkflowError("retained Git bundle changed")
    plan = object_value(state, "plan")
    if history(Path(text(plan, "source")), runner) != record["history"]:
        raise WorkflowError("source Git history or refs changed; prepare a new task")
    if (
        plan["mode"] == "existing"
        and history(Path(text(state, "workspace")), runner) != record["history"]
    ):
        raise WorkflowError("workspace Git history or refs changed")


def restore(task: Path, root: Path, runner: Runner) -> None:
    """Load retained objects and exact refs, leaving all worktree files untouched."""
    record = load(task / "repository-git.json")
    expected = object_value(record, "history")
    if record["bundle"] is not None:
        _ = runner.run(["git", "bundle", "unbundle", str(task / "repository.bundle")], root)
    refs = object_value(expected, "refs")
    for name in refs:
        _ = runner.run(["git", "update-ref", name, text(object_value(refs, name), "oid")], root)
    for name in refs:
        symbolic = object_value(refs, name)["symbolic"]
        if isinstance(symbolic, str) and symbolic:
            _ = runner.run(["git", "symbolic-ref", name, symbolic], root)
    if expected["branch"]:
        _ = runner.run(["git", "symbolic-ref", "HEAD", text(expected, "branch")], root)
    elif expected["head"]:
        _ = runner.run(["git", "update-ref", "--no-deref", "HEAD", text(expected, "head")], root)
    if history(root, runner) != expected:
        raise WorkflowError("repository Git context was not faithfully restored")


def stage_candidate(root: Path, runner: Runner, files: Record) -> None:
    """Enroll exact candidate bytes without filters, ignores or source-index writes."""
    if not files:
        raise WorkflowError("empty repository candidate")
    _ = runner.run(["git", "read-tree", "--empty"], root)
    for name in files:
        blob = runner.run(["git", "hash-object", "-w", "--no-filters", "--", name], root)
        mode = int(str(object_value(files, name)["mode"]))
        _ = runner.run(
            [
                "git",
                "update-index",
                "--add",
                "--cacheinfo",
                "100755" if mode & 0o111 else "100644",
                blob,
                name,
            ],
            root,
        )
    _ = runner.run(["git", "ls-files", "-z"], root)
    discovered = runner.last_output.read_text().split("\0")[:-1]
    if set(discovered) != set(files):
        raise WorkflowError("Git discovery differs from the measured candidate")
