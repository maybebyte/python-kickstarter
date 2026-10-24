"""Substantive execution evidence bound to candidate, configuration and tools."""

import re
import uuid
from pathlib import Path

from kickstarter_workflow.environment import environment_identity
from kickstarter_workflow.files import (
    confined,
    copy_inventory,
    inventory,
    mappings,
    names,
    string_list,
)
from kickstarter_workflow.git_context import identity, restore, stage_candidate
from kickstarter_workflow.policy import coverage_floor, gate_policy
from kickstarter_workflow.process import Runner
from kickstarter_workflow.records import (
    Record,
    WorkflowError,
    digest,
    encoded,
    load,
    object_value,
    private_directory,
    save,
    text,
)
from kickstarter_workflow.setup import git_root


def binding(state: Record, runner: Runner) -> Record:
    """Bind all candidate bytes/modes, immutable plan, and actual tool identities."""
    workspace = Path(text(state, "workspace"))
    plan = object_value(state, "plan")
    return {
        "interpreter": environment_identity(workspace),
        "candidate": inventory(workspace, plan),
        "plan": object_value(state, "plan"),
        "tools": runner.identities(workspace),
        "git": identity(workspace, runner),
        "source_git": identity(Path(text(object_value(state, "plan"), "source")), runner),
    }


def validate_receipt(state: Record, task: Path, runner: Runner) -> Record:
    """Refuse changed inputs, missing logs and interrupted or failed receipts."""
    token = text(state, "receipt")
    receipt = load(confined(task, "receipts/" + token + ".json"))
    if receipt.get("status") != "passed" or digest(encoded(receipt)) != token:
        raise WorkflowError("failed or modified verification receipt")
    if receipt.get("binding") != binding(state, runner):
        raise WorkflowError("stale verification: candidate/configuration/tool identity changed")
    for name, expected in object_value(receipt, "artifacts").items():
        path = confined(task, name)
        if not path.is_file() or digest(path.read_bytes()) != expected:
            raise WorkflowError("missing or modified verification evidence")
    return receipt


def _repository(plan: Record, task: Path, workspace: Path, runner: Runner) -> Path:
    if plan["mode"] != "workbench":
        return workspace
    root = task / ("repository-" + uuid.uuid4().hex)
    root.mkdir(mode=0o700)
    copy_inventory(task / "baseline", root, load(task / "source.json"))
    for item in mappings(plan):
        target = confined(root, text(item, "source"))
        target.parent.mkdir(parents=True, exist_ok=True)
        candidate = confined(workspace, text(item, "target"))
        _ = target.write_bytes(candidate.read_bytes())
        target.chmod(candidate.stat().st_mode & 0o777)
    _ = runner.run(["git", "-c", "init.templateDir=", "init", "--quiet", str(root)], task)
    restore(task, root, runner)
    stage_candidate(root, runner, inventory(root, plan, destination=True))
    return root


def repository_checks(plan: Record, root: Path, workspace: Path, runner: Runner) -> None:
    """Run declared checks plus the repository's non-optional CI entrypoint."""
    git_root(runner, root)
    checks = plan.get("repository_checks")
    if not isinstance(checks, list) or not checks:
        raise WorkflowError("missing mandatory repository checks")
    commands: list[list[str]] = []
    for check in checks:
        command = string_list({"argv": check}, "argv")
        commands.append([arg.replace("{workspace}", str(workspace)) for arg in command])
    if (root / "justfile").exists() and ["just", "ci"] not in commands:
        commands.insert(0, ["just", "ci"])
    policy = root / ".kickstarter-checks.json"
    if policy.exists():
        required = load(policy).get("checks")
        if not isinstance(required, list):
            raise WorkflowError("invalid repository check policy")
        commands.extend(string_list({"argv": check}, "argv") for check in required)
    runner.env["PYTHONPATH"] = os_path(root, names(plan, "source", destination=True))
    before: Record = {
        "files": inventory(root, plan, destination=True),
        "git": identity(root, runner),
    }
    save(runner.evidence / ("repository-inputs-" + uuid.uuid4().hex + ".json"), before)
    for command in commands:
        _ = runner.run(command, root)
    if {"files": inventory(root, plan, destination=True), "git": identity(root, runner)} != before:
        raise WorkflowError("repository inputs changed while checks were running")


def os_path(root: Path, files: list[str]) -> str:
    """Build an import path scoped to the concrete execution layout."""
    return ":".join(
        dict.fromkeys(
            [
                str(root),
                *(
                    str(parent)
                    for name in files
                    for parent in confined(root, name).parents
                    if parent.is_relative_to(root)
                ),
            ]
        )
    )


def product_evidence(
    plan: Record, root: Path, workspace: Path, runner: Runner, *, destination: bool = False
) -> Record:
    """Execute declared maintained tests and inspect real branch/line coverage."""
    sources = names(plan, "source", destination=destination)
    tests = names(plan, "test", destination=destination)
    for name in [*sources, *tests]:
        if not confined(root, name).is_file():
            raise WorkflowError("empty or missing product target")
    output = runner.evidence / "product-coverage.json"
    junit = runner.evidence / "product-tests.xml"
    runner.env["PYTHONPATH"] = os_path(root, sources)
    targets = sorted({str(Path(name).parent) for name in sources})
    _ = runner.run(
        [
            "uv",
            "run",
            "--project",
            str(workspace),
            "--locked",
            "pytest",
            "--override-ini=addopts=",
            "--cov-branch",
            "--cov-report=json:" + str(output),
            "--junitxml=" + str(junit),
            *("--cov=" + target for target in targets),
            *tests,
        ],
        root,
    )
    coverage = object_value(load(output), "files")
    for source in sources:
        measured = object_value(coverage, source)
        summary = object_value(measured, "summary")
        if not measured.get("executed_lines") or float(
            str(summary.get("percent_covered", 0))
        ) < coverage_floor(workspace):
            raise WorkflowError("empty or inadequate real product coverage")
    counts = re.findall(r"<testcase\s", junit.read_text())
    if not counts or re.search(r"<(?:skipped|failure|error)(?:\s|>)", junit.read_text()):
        raise WorkflowError("no successful substantive product test execution")
    minimum = min(
        float(str(object_value(object_value(coverage, source), "summary")["percent_covered"]))
        for source in sources
    )
    return {"product_tests": len(counts), "product_coverage": int(minimum)}


def verify(state: Record, task: Path, runner: Runner) -> Record:
    """Run all mandatory gates and publish a candidate-bound receipt only on success."""
    plan = object_value(state, "plan")
    workspace = Path(text(state, "workspace"))
    if plan["mode"] != "new" and inventory(
        Path(text(plan, "source")), plan, destination=True
    ) != load(task / "source.json"):
        raise WorkflowError(
            "source changed since preparation; return reconciliation or a decision is required"
        )
    git_root(runner, workspace)
    gate_policy(workspace, existing=plan["mode"] == "existing")
    baseline = load(task / "scaffold.json")
    current = inventory(workspace, plan)
    protected = {
        name
        for name in baseline
        if name in {"justfile", "pyproject.toml", ".copier-answers.yml"}
        or name.startswith("tests/policy/")
    }
    if any(current.get(name) != baseline[name] for name in protected):
        raise WorkflowError(
            "gate configuration differs from the prepared reviewed policy; prepare a new plan"
        )
    for name in [*names(plan, "source"), *names(plan, "test")]:
        if not confined(workspace, name).is_file():
            raise WorkflowError("empty or missing product target")
    if plan["mode"] == "new":
        scaffold = load(task / "scaffold.json")
        candidate = inventory(workspace, plan)
        if all(scaffold.get(name) == candidate.get(name) for name in names(plan, "test")):
            raise WorkflowError("scaffold-only tests are not product evidence")
    runner.env["PYTHONPATH"] = os_path(workspace, names(plan, "source"))
    _ = runner.run(["uv", "sync", "--locked"], workspace)
    stage_candidate(workspace, runner, inventory(workspace, plan))
    before = binding(state, runner)
    _ = runner.run(["just", "ci"], workspace)
    product = product_evidence(plan, workspace, workspace, runner)
    repository_checks(plan, _repository(plan, task, workspace, runner), workspace, runner)
    if binding(state, runner) != before:
        raise WorkflowError("candidate changed while checks were running")
    if plan["mode"] != "new" and inventory(
        Path(text(plan, "source")), plan, destination=True
    ) != load(task / "source.json"):
        raise WorkflowError("source changed while checks were running")
    receipt: Record = {"binding": before, **product, "status": "passed"}
    receipt["artifacts"] = {
        path.relative_to(task).as_posix(): digest(path.read_bytes())
        for path in runner.evidence.iterdir()
        if path.is_file()
    }
    token = digest(encoded(receipt))
    private_directory(task / "receipts")
    save(task / "receipts" / (token + ".json"), receipt)
    return {**state, **product, "status": "verified", "receipt": token}
