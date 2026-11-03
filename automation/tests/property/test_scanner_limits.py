"""Finite stack limits must pass through the helper's public scan recipe unchanged."""

import os
import resource
import shutil
import tempfile
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

pytestmark = pytest.mark.property
_HARD = resource.getrlimit(resource.RLIMIT_STACK)[1]
_MAX_KIB = 2097152 if _HARD == resource.RLIM_INFINITY else min(2097152, _HARD // 1024)
if _MAX_KIB < 1:
    pytest.skip("inherited hard stack has no positive whole-KiB domain", allow_module_level=True)
# Keep the usual floor, but leave room to vary both limits on lower-ceiling hosts.
_MIN_KIB = min(8192, max(1, _MAX_KIB // 2))


@given(hard=st.integers(_MIN_KIB, _MAX_KIB), fraction=st.integers(0, 100))
def test_finite_limits_are_preserved(hard: int, fraction: int) -> None:
    soft = _MIN_KIB + (hard - _MIN_KIB) * fraction // 100
    bash = shutil.which("bash")
    assert bash is not None
    justfile = Path(__file__).resolve().parents[2] / "justfile"
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
        root = Path(directory)
        script = Path(__file__).resolve().parents[1] / "fixtures" / "scanner_finite_limits.sh"
        output = root / "events"
        env = dict(os.environ, SOFT=str(soft), HARD=str(hard), EVENTS=str(output))
        pid = os.posix_spawn(bash, [bash, str(script), str(justfile)], env)
        _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        assert output.read_text().splitlines() == [
            f"scanner\t{soft}\t{hard}",
            f"later\t{soft}\t{hard}",
            f"caller\t{soft}\t{hard}",
        ]
