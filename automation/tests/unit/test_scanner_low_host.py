"""The finite-limit property must run, not falsely fail, on a 4 MiB host."""

import os
import resource
import signal
import sys
import time
from pathlib import Path

import pytest


def test_finite_limit_property_on_four_mib_host(tmp_path: Path) -> None:
    before = resource.getrlimit(resource.RLIMIT_STACK)
    if before[1] != resource.RLIM_INFINITY and before[1] < 4194304:
        pytest.skip("the child-only 4 MiB regression cannot raise an inherited hard ceiling")
    script = Path(__file__).resolve().parents[1] / "fixtures" / "scanner_low_host.py"
    output = tmp_path / "reports"
    log = tmp_path / "child.log"
    with log.open("w") as stream:
        pid = os.posix_spawn(
            sys.executable,
            [sys.executable, "-B", str(script), str(output)],
            dict(os.environ),
            file_actions=[
                (os.POSIX_SPAWN_DUP2, stream.fileno(), 1),
                (os.POSIX_SPAWN_DUP2, stream.fileno(), 2),
            ],
            setpgroup=0,
        )
        reaped = False
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                waited, status = os.waitpid(pid, os.WNOHANG)
                if waited:
                    reaped = True
                    assert os.waitstatus_to_exitcode(status) == 0, log.read_text()
                    break
                time.sleep(0.05)
            assert reaped, "selected property child exceeded 90 seconds"
        finally:
            if not reaped:
                os.killpg(pid, signal.SIGKILL)
                _ = os.waitpid(pid, 0)
            assert resource.getrlimit(resource.RLIMIT_STACK) == before
    assert output.read_text().splitlines() == [
        "host\t4194304\t4194304",
        "call\ttests/property/test_scanner_limits.py::test_finite_limits_are_preserved\tpassed",
    ]
