"""Fail-closed safety and ownership contracts."""

from pathlib import Path

import pytest

from kickstarter_workflow.records import Record, Value, object_value, text
from kickstarter_workflow.workflow import Workflow


def test_external_records_never_modify_the_source_tree(plan: Record) -> None:
    source = Path(text(plan, "source"))
    workflow = Workflow(source / ".workflow-state")
    before = sorted(path.relative_to(source).as_posix() for path in source.rglob("*"))
    result = workflow.dispatch("prepare", plan)
    assert result["status"] == "blocked", result
    after = sorted(path.relative_to(source).as_posix() for path in source.rglob("*"))
    assert after == before


def test_pending_state_write_blocks_resume_instead_of_reusing_old_readiness(tmp_path: Path) -> None:
    workflow = Workflow(tmp_path / "state")
    request: Record = {
        "project": "sample",
        "task": "one",
        "mode": "disposable",
        "reason": "diagnostic",
    }
    assert workflow.dispatch("prepare", request)["status"] == "exempt"
    pending = tmp_path / "state/sample/one/task.pending"
    _ = pending.write_text('{"status": "preparing"}')
    result = workflow.dispatch("resume", request)
    assert result["status"] == "blocked", result
    assert "pending" in text(result, "reason")
    assert pending.exists()


@pytest.mark.parametrize(
    "revision",
    [
        "main",
        "v0.3.0",
        "a" * 39,
        "a" * 41,
        "A" * 40,
        "0" * 40,
        " 37adbeeea53a242ed25db602a35b9d719d95c8ae",
    ],
)
def test_unapproved_or_malformed_revisions_never_fall_back(
    tmp_path: Path, plan: Record, revision: str
) -> None:
    changed: Record = {**plan, "template": {**object_value(plan, "template"), "revision": revision}}
    result = Workflow(tmp_path / "state").dispatch("prepare", changed)
    assert result["status"] == "blocked", result
    assert "template" in text(result, "reason")
    assert not (tmp_path / "state/sample/one/workspace").exists()


@pytest.mark.parametrize(
    "path",
    [
        "../escape.py",
        "/absolute.py",
        "product/../../escape.py",
        "product//app.py",
        "product/./app.py",
        "product/../app.py",
        "product/\\\\app.py",
        ".git/config",
        "product/app.py\n",
    ],
)
def test_unsafe_mapping_paths_are_rejected_before_generation(
    tmp_path: Path, plan: Record, path: str
) -> None:
    mapping: list[Value] = [
        {"source": "app.py", "target": path, "role": "source"},
        {"source": "test_app.py", "target": "product/test_app.py", "role": "test"},
    ]
    result = Workflow(tmp_path / "state").dispatch("prepare", {**plan, "mapping": mapping})
    assert result["status"] == "blocked", result
    assert "unsafe relative path" in text(result, "reason")
    assert not (tmp_path / "state/sample/one/workspace").exists()


def test_symlinks_shared_state_and_missing_tools_are_refused(tmp_path: Path, plan: Record) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    result = Workflow(link / "state").dispatch("prepare", plan)
    assert "symlink" in text(result, "reason")
    real.chmod(0o777)
    result = Workflow(real).dispatch("prepare", plan)
    assert "0700" in text(result, "reason")
    tools = {**object_value(plan, "tools"), "copier": str(tmp_path / "absent-copier")}
    result = Workflow(tmp_path / "good-state").dispatch("prepare", {**plan, "tools": tools})
    assert "missing executable" in text(result, "reason")


def test_exemption_promotion_and_unresolved_cleanup(tmp_path: Path, plan: Record) -> None:
    workflow = Workflow(tmp_path / "state")
    exempt: Record = {"project": "sample", "task": "one", "mode": "disposable", "reason": "one-off"}
    assert workflow.dispatch("prepare", exempt)["status"] == "exempt"
    assert workflow.dispatch("prepare", plan)["status"] == "prepared"
    assert workflow.dispatch("resume", exempt)["status"] == "blocked"
    assert workflow.dispatch("cleanup", plan)["status"] == "blocked"
    assert (tmp_path / "state/sample/one/workspace").is_dir()
    changed: Record = {**plan, "scope_review": "Different task intent."}
    assert workflow.dispatch("prepare", changed)["status"] == "blocked"
    assert list((tmp_path / "state/sample/one").glob("exemption-*.json"))


def test_generated_gate_weakening_and_failed_checks_remain_failures(
    tmp_path: Path, plan: Record
) -> None:
    workflow = Workflow(tmp_path / "state")
    state = workflow.dispatch("prepare", plan)
    workspace = Path(text(state, "workspace"))
    config = workspace / "pyproject.toml"
    original = config.read_text()
    _ = config.write_text(original.replace("fail_under = 85", "fail_under = 1"))
    result = workflow.dispatch("verify", plan)
    assert result["status"] == "blocked"
    assert "weakened" in text(result, "reason")
    _ = config.write_text(original)
    tests = workspace / "product/test_app.py"
    _ = tests.write_text(tests.read_text().replace("== 6", "== 9"))
    failed = workflow.dispatch("verify", plan)
    assert failed["status"] == "blocked", failed
    assert "just failed" in text(failed, "reason")
    assert workflow.dispatch("status", plan)["status"] == "blocked"


def test_new_maintained_regression_paths_can_be_declared_before_creation(
    tmp_path: Path, plan: Record
) -> None:
    original_mapping = plan["mapping"]
    assert isinstance(original_mapping, list)
    request: Record = {
        **plan,
        "mapping": [
            *original_mapping,
            {
                "source": "tests/test_added.py",
                "target": "product/tests/test_added.py",
                "role": "test",
                "new": True,
            },
        ],
    }
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", request)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    assert not (workspace / "product/tests/test_added.py").exists()
    rejected = workflow.dispatch("verify", request)
    assert rejected["status"] == "blocked", rejected
    assert "missing product target" in text(rejected, "reason")


def test_resume_revalidates_workspace_instead_of_returning_stale_readiness(
    tmp_path: Path, plan: Record
) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    (workspace / ".copier-answers.yml").unlink()
    result = workflow.dispatch("resume", plan)
    assert result["status"] == "blocked", result
    assert "workspace" in text(result, "reason")


def test_gate_bodies_cannot_be_replaced_by_success_markers(tmp_path: Path, plan: Record) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    workspace = Path(text(prepared, "workspace"))
    justfile = workspace / "justfile"
    _ = justfile.write_text(justfile.read_text().replace("uv run ruff check .", "true"))
    result = workflow.dispatch("verify", plan)
    assert result["status"] == "blocked", result
    assert "gate configuration" in text(result, "reason")


def test_missing_or_forged_receipt_is_not_success(tmp_path: Path, plan: Record) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    request: Record = {
        "project": "sample",
        "task": "one",
        "review": {
            "receipt": "agent says passed",
            "reviewer": "reviewer",
            "reason": "test",
            "allowlist": ["app.py"],
        },
    }
    result = workflow.dispatch("return", request)
    assert result["status"] == "blocked"
    assert "verification" in text(result, "reason")


def test_source_changes_are_not_certified_as_unchanged(tmp_path: Path, plan: Record) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    source = Path(text(plan, "source"))
    _ = (source / "app.py").write_text('"""Newer source belongs to another task."""\n')
    result = workflow.dispatch("verify", plan)
    assert result["status"] == "blocked", result
    assert "source changed" in text(result, "reason")
