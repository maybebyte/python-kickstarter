"""Reviewed-return reconciliation and durable interruption regressions."""

import os
import signal
from pathlib import Path

import pytest

from kickstarter_workflow.records import Record, text
from kickstarter_workflow.workflow import Workflow


def review(receipt: str, *files: str) -> Record:
    return {
        "project": "sample",
        "task": "one",
        "review": {
            "receipt": receipt,
            "reviewer": "independent-test-review",
            "reason": "Named product delta reviewed.",
            "allowlist": list(files),
        },
    }


@pytest.mark.parametrize("drift", ["content", "mode"])
def test_return_refuses_unreviewed_payload_and_conflicting_newer_source(
    tmp_path: Path, plan: Record, drift: str
) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    workspace = Path(text(prepared, "workspace"))
    source = Path(text(plan, "source"))
    app = workspace / "product/app.py"
    _ = app.write_text(app.read_text().replace("value * 2", "value + value"))
    if drift == "mode":
        app.chmod(0o600)
    verified = workflow.dispatch("verify", plan)
    assert verified["status"] == "verified", verified
    receipt = text(verified, "receipt")
    for request in (
        review("old-receipt", "app.py"),
        review(receipt, "uv.lock"),
        review(receipt, "app.py", "app.py"),
        review(receipt, "test_app.py"),
    ):
        assert workflow.dispatch("return", request)["status"] == "blocked"
        assert "value * 2" in (source / "app.py").read_text()
    if drift == "content":
        _ = (source / "app.py").write_text(
            (source / "app.py").read_text().replace("value * 2", "value * 3")
        )
    else:
        (source / "app.py").chmod(0o640)
    result = workflow.dispatch("return", review(receipt, "app.py"))
    assert result["status"] == "blocked", result
    assert "conflict" in text(result, "reason")
    if drift == "content":
        assert "value * 3" in (source / "app.py").read_text()
    else:
        assert (source / "app.py").stat().st_mode & 0o777 == 0o640


def test_interrupted_return_reports_actual_effects_and_retry_does_not_rewrite_them(
    tmp_path: Path, plan: Record, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    workspace = Path(text(prepared, "workspace"))
    source = Path(text(plan, "source"))
    app, tests = workspace / "product/app.py", workspace / "product/test_app.py"
    _ = app.write_text(app.read_text().replace("value * 2", "value + value"))
    _ = tests.write_text(tests.read_text().replace("test_twice", "test_double"))
    verified = workflow.dispatch("verify", plan)
    assert verified["status"] == "verified", verified
    request = review(text(verified, "receipt"), "app.py", "test_app.py")
    original = Path.replace

    def interrupt(path: Path, target: Path) -> Path:
        result = original(path, target)
        if target == source / "app.py":
            os.kill(os.getpid(), signal.SIGINT)
        return result

    with monkeypatch.context() as fault:
        fault.setattr(Path, "replace", interrupt)
        pid = os.fork()
        if pid == 0:
            _ = signal.signal(signal.SIGINT, signal.default_int_handler)
            try:
                _ = workflow.dispatch("return", request)
            except KeyboardInterrupt:
                os._exit(73)
            os._exit(74)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 73
    observed = workflow.dispatch("status", plan)
    assert observed["status"] == "returning", observed
    assert observed["applied"] == ["app.py"]
    before_retry = (source / "app.py").stat().st_mtime_ns
    untouched = source / "test_app.py"
    before_test = untouched.read_bytes()
    _ = untouched.write_bytes(before_test + b"\n# A concurrent owner changed this file.\n")
    refused = workflow.dispatch("return", request)
    assert refused["status"] == "blocked", refused
    assert "interrupted return" in text(refused, "reason")
    assert (source / "app.py").stat().st_mtime_ns == before_retry
    _ = untouched.write_bytes(before_test)
    returned = workflow.dispatch("return", request)
    assert returned["status"] == "returned", returned
    assert returned["applied"] == ["app.py", "test_app.py"]
    assert (source / "app.py").stat().st_mtime_ns == before_retry
    assert "test_double" in (source / "test_app.py").read_text()
    assert workflow.dispatch("cleanup", plan)["status"] == "cleaned"
    assert not workspace.exists()
    assert (tmp_path / "state/sample/one/return.json").is_file()


def test_compatible_three_way_merge_preserves_both_edits_and_exact_whitespace(
    tmp_path: Path, plan: Record
) -> None:
    source = Path(text(plan, "source"))
    original = "\nHeading\n\nA\nB\nC\nD\nFooter\n\n"
    _ = (source / "README.md").write_text(original)
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    _ = (workspace / "product/README.md").write_text(original.replace("Heading", "Task heading"))
    verified = workflow.dispatch("verify", plan)
    assert verified["status"] == "verified", verified
    _ = (source / "README.md").write_text(original.replace("Footer", "Other footer"))
    result = workflow.dispatch("return", review(text(verified, "receipt"), "README.md"))
    assert result["status"] == "review_required", result
    assert result["receipt"] != verified["receipt"]
    assert (source / "README.md").read_text() == original.replace("Footer", "Other footer")
    diff = Path(text(result, "reconciliation_diff")).read_text()
    assert "Other footer" in diff
    assert (
        workflow.dispatch("return", review(text(verified, "receipt"), "README.md"))["status"]
        == "blocked"
    )
    assert workflow.dispatch("resume", plan)["status"] == "review_required"
    result = workflow.dispatch("return", review(text(result, "receipt"), "README.md"))
    assert result["status"] == "returned", result
    assert (source / "README.md").read_text() == "\nTask heading\n\nA\nB\nC\nD\nOther footer\n\n"
    assert result["reconciled"] is True
