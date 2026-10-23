"""Pinned template preparation, separate from product verification."""

import json
import re
import shlex
from pathlib import Path

from kickstarter_workflow.environment import adapt_environment, environment_identity
from kickstarter_workflow.files import confined, copy_inventory, copy_mapping, inventory, mappings
from kickstarter_workflow.git_context import restore, retain
from kickstarter_workflow.policy import gate_policy
from kickstarter_workflow.process import Runner
from kickstarter_workflow.records import (
    Record,
    WorkflowError,
    digest,
    no_links,
    object_value,
    save,
    text,
)

CANONICAL = "https://github.com/maybebyte/python-kickstarter.git"
APPROVED = frozenset({"37adbeeea53a242ed25db602a35b9d719d95c8ae"})
ANSWER_KEYS = frozenset(
    {
        "project_name",
        "package_name",
        "author_name",
        "author_email",
        "description",
        "license",
        "python_version",
        "project_type",
    }
)


def git_root(runner: Runner, root: Path) -> None:
    """Require this exact repository, never an enclosing home-wide ancestor."""
    actual = runner.run(["git", "rev-parse", "--show-toplevel"], root)
    if Path(actual).resolve() != root.resolve():
        raise WorkflowError("source must be the exact Git root")


def template(plan: Record, runner: Runner) -> tuple[Path, str]:
    """Validate a clean canonical cache at an explicitly reviewed full commit."""
    selected = object_value(plan, "template")
    revision = text(selected, "revision")
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise WorkflowError("template revision must be an exact lowercase 40-hex commit")
    if revision not in APPROVED or text(selected, "source") != CANONICAL:
        raise WorkflowError("template source/revision has not been approved")
    cache = no_links(Path(text(selected, "cache")))
    git_root(runner, cache)
    _ = runner.run(["git", "symbolic-ref", "--quiet", "HEAD"], cache, allow_failure=True)
    if runner.last_exit == 0:
        raise WorkflowError("moving template checkout; detach the approved commit")
    if runner.run(["git", "rev-parse", "HEAD"], cache) != revision:
        raise WorkflowError("template cache is not at the approved commit")
    if runner.run(["git", "status", "--porcelain", "--untracked-files=all"], cache):
        raise WorkflowError("dirty template source")
    if runner.run(["git", "remote", "get-url", "origin"], cache) != CANONICAL:
        raise WorkflowError("noncanonical template cache")
    config = (cache / "copier.yml").read_text()
    if re.search(r"^_(?:jinja_extensions|migrations|external_data)\s*:", config, re.MULTILINE):
        raise WorkflowError("unsafe executable template features")
    return cache, revision


def _answers(plan: Record) -> list[str]:
    answers = object_value(plan, "answers")
    if frozenset(answers) != ANSWER_KEYS:
        raise WorkflowError("explicit identity, compatibility and app/library answers required")
    args: list[str] = []
    for key in sorted(answers):
        args.extend(["--data", f"{key}={text(answers, key)}"])
    return args


def _preflight(plan: Record, source: Path, workspace: Path) -> None:
    _ = text(plan, "scope_review")
    requirements = plan.get("git_requirements", ["index", "history", "refs"])
    if not isinstance(requirements, list) or any(
        not isinstance(item, str) or item not in {"index", "history", "refs"}
        for item in requirements
    ):
        raise WorkflowError(
            "unsupported Git check requirements; only candidate index, local history and refs are provided"
        )
    if not isinstance(plan.get("repository_checks"), list) or not plan["repository_checks"]:
        raise WorkflowError("explicit mandatory repository check plan required")
    if workspace.is_relative_to(source) or source.is_relative_to(workspace.parent):
        raise WorkflowError("source, task records and workspace must be separate")
    for item in mappings(plan):
        _ = confined(source, text(item, "source"))
        target = text(item, "target")
        _ = confined(workspace, target)
        # just interpolation, Ruff globs and pytest selectors are not literal paths.
        if item["role"] == "test" and any(
            "::" in name or any(char in name for char in "{}[]*?")
            for name in (text(item, "source"), target)
        ):
            raise WorkflowError("unsupported recipe/glob/test-selector syntax in mapped test path")


def _generate(plan: Record, workspace: Path, cache: Path, revision: str, runner: Runner) -> None:
    _ = runner.run(
        [
            "copier",
            "copy",
            "--defaults",
            "--skip-tasks",
            "--vcs-ref",
            revision,
            "--data",
            "enable_precommit_install=false",
            "--data",
            "in_existing_repo=false",
            *_answers(plan),
            str(cache),
            str(workspace),
        ],
        workspace.parent,
    )
    _ = runner.run(
        ["git", "-c", "init.templateDir=", "init", "--quiet", str(workspace)], workspace.parent
    )
    git_root(runner, workspace)


def _reuse(source: Path, workspace: Path, cache: Path, revision: str, runner: Runner) -> None:
    answers = (source / ".copier-answers.yml").read_text()
    origin = re.search(r"^_src_path: (.+)$", answers, re.MULTILINE)
    commit = re.search(r"^_commit: ([a-zA-Z0-9.\-]+)$", answers, re.MULTILINE)
    if origin is None or origin[1] not in {CANONICAL, str(cache)} or commit is None:
        raise WorkflowError("existing project lacks canonical Copier provenance")
    if runner.run(["git", "rev-parse", "--verify", commit[1] + "^{commit}"], cache) != revision:
        raise WorkflowError("existing project revision differs; upgrades are separate")
    workspace.mkdir(mode=0o700)
    copy_inventory(source, workspace, inventory(source))
    _ = runner.run(
        ["git", "-c", "init.templateDir=", "init", "--quiet", str(workspace)], workspace.parent
    )
    git_root(runner, workspace)


def _adapt_workbench(plan: Record, workspace: Path) -> None:
    package = text(object_value(plan, "answers"), "package_name")
    config_path = workspace / "pyproject.toml"
    config = config_path.read_text()
    config = config.replace(
        'include = ["src", "tests"]',
        'include = ["src", "tests", "product"]\nextraPaths = ["product"]',
    )
    config = config.replace(f'source = ["{package}"]', f'source = ["{package}", "product"]')
    test_ignores = '["S101", "PLR2004", "ANN", "D", "INP001", "SLF001"]'
    additions = "".join(
        f"{json.dumps(text(item, 'target'))} = {test_ignores}\n"
        for item in mappings(plan)
        if item["role"] == "test"
    )
    config = config.replace(
        "[tool.ruff.lint.per-file-ignores]\n", "[tool.ruff.lint.per-file-ignores]\n" + additions
    )
    _ = config_path.write_text(config)
    (workspace / "product").mkdir(exist_ok=True)
    if not any(item["target"] == "product/__init__.py" for item in mappings(plan)):
        _ = (workspace / "product/__init__.py").write_text(
            '"""External product workspace, not a return payload."""\n'
        )
    justfile = workspace / "justfile"
    tests = " ".join(
        shlex.quote(text(item, "target")) for item in mappings(plan) if item["role"] == "test"
    )
    _ = justfile.write_text(
        justfile.read_text().replace("tests/unit\n", "tests/unit " + tests + "\n")
    )


def prepare(plan: Record, task: Path, runner: Runner) -> Record:
    """Prepare a new project, reuse an existing one or generate a workbench."""
    source = no_links(Path(text(plan, "source")))
    mode = text(plan, "mode")
    if mode not in {"new", "existing", "workbench"}:
        raise WorkflowError("unknown preparation mode")
    workspace = source if mode == "new" else task / "workspace"
    _preflight(plan, source, task / "workspace")
    cache, revision = template(plan, runner)
    identities = runner.identities(task)
    if mode == "new":
        if source.exists():
            raise WorkflowError("new project destination already exists")
        _ = runner.run(["git", "rev-parse", "--show-toplevel"], source.parent, allow_failure=True)
        if runner.last_exit == 0 and plan.get("isolate_git") is not True:
            raise WorkflowError(
                "new project has an enclosing Git root; explicit isolate_git authorization required"
            )
        _generate(plan, workspace, cache, revision, runner)
        before: Record = {}
    else:
        git_root(runner, source)
        before = inventory(source)
        snapshot = task / "baseline"
        snapshot.mkdir(mode=0o700)
        copy_inventory(source, snapshot, before)
        if mode == "existing":
            _reuse(source, workspace, cache, revision, runner)
        else:
            if (source / ".copier-answers.yml").exists():
                raise WorkflowError("generated project must use existing mode")
            _generate(plan, workspace, cache, revision, runner)
            copy_mapping(plan, source, workspace)
            _adapt_workbench(plan, workspace)
            adapt_environment(plan, source, workspace)
        if inventory(source) != before:
            raise WorkflowError("source changed during preparation")
    gate_policy(workspace, existing=mode == "existing")
    git_sha256 = retain(source, task, runner)
    if mode == "existing":
        restore(task, workspace, runner)
    _ = runner.run(
        ["uv", "sync", "--locked"] if (workspace / "uv.lock").exists() else ["uv", "sync"],
        workspace,
    )
    save(task / "source.json", before)
    save(task / "scaffold.json", inventory(workspace))
    return {
        "status": "prepared",
        "plan": plan,
        "workspace": str(workspace),
        "template_revision": revision,
        "tools": identities,
        "environment": environment_identity(workspace),
        "git_sha256": git_sha256,
        "source_sha256": digest((task / "source.json").read_bytes()),
        "scaffold_sha256": digest((task / "scaffold.json").read_bytes()),
    }
