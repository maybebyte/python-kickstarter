"""The interruption fixture terminates its child even when setup or dispatch fails."""

import contextlib
import os
import signal
import time
from pathlib import Path

import pytest

from kickstarter_workflow.workflow import Workflow
from tests.unit.test_transfer import return_child


def wait_for_child(pid: int) -> int:
    status: int | None = None
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            child, observed = os.waitpid(pid, os.WNOHANG)
            if child:
                status = observed
                break
            time.sleep(0.01)
        assert status is not None, "child did not terminate without observer intervention"
        return os.waitstatus_to_exitcode(status)
    finally:
        if status is None:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
            _ = os.waitpid(pid, 0)


@pytest.mark.parametrize("failure", ["setup", "dispatch", "system-exit", "interrupt", "normal"])
def test_return_child_terminates_without_falling_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], failure: str
) -> None:
    workflow = Workflow(tmp_path / "state")
    escaped = tmp_path / "escaped"

    def fail_setup(*_args: object) -> None:
        raise RuntimeError("fixture-setup-fault")

    def dispatch(*_args: object) -> dict[str, str]:
        faults = {"dispatch": RuntimeError("fixture-dispatch-fault"), "system-exit": SystemExit(42)}
        if failure in faults:
            raise faults[failure]
        if failure == "interrupt":
            os.kill(os.getpid(), signal.SIGINT)
        return {"status": "blocked"}

    monkeypatch.setattr(workflow, "dispatch", dispatch)
    if failure == "setup":
        monkeypatch.setattr(signal, "signal", fail_setup)
    pid = os.fork()
    if pid == 0:
        try:
            return_child(workflow, {})
        except BaseException:
            _ = escaped.write_text("child escaped into its caller")
            raise
        finally:
            # Contain a broken subject; this distinct status must fail the test.
            os._exit(99)
    expected = {"interrupt": 73, "normal": 74}.get(failure, 75)
    assert wait_for_child(pid) == expected
    assert not escaped.exists()
    diagnostic = capfd.readouterr().err
    if failure in {"setup", "dispatch"}:
        assert f"RuntimeError: fixture-{failure}-fault" in diagnostic
    elif failure == "system-exit":
        assert "SystemExit: 42" in diagnostic
