"""Temporary-directory behavior observed by a real runner child."""

import sys
from pathlib import Path

import pytest

from kickstarter_workflow.process import Runner, default_tools
from kickstarter_workflow.records import WorkflowError, load, text

PROBE = Path(__file__).resolve().parents[1] / "fixtures/temporary_probe.py"


def test_absent_tmpdir_is_created_privately_before_child_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TMPDIR", raising=False)
    runner = Runner(
        {**default_tools(), "just": sys.executable}, tmp_path / "evidence", tmp_path / "cache"
    )
    _ = runner.run(["just", str(PROBE), "create"], tmp_path)
    observed = load(runner.last_output)
    directory = Path(text(observed, "TMPDIR"))
    assert directory.is_relative_to(tmp_path / "cache")
    assert observed["parent"] == str(directory)
    assert directory.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("value", ["", "relative directory", "/caller/does-not-exist"])
def test_explicit_tmpdir_is_verbatim_without_touching_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("TMPDIR", value)
    cache = tmp_path / "cache"
    _ = cache.write_bytes(b"Caller-owned obstruction; do not validate or replace.")
    runner = Runner({**default_tools(), "just": sys.executable}, tmp_path / "evidence", cache)
    _ = runner.run(["just", str(PROBE)], tmp_path)
    assert load(runner.last_output)["TMPDIR"] == value
    assert cache.read_bytes() == b"Caller-owned obstruction; do not validate or replace."


@pytest.mark.parametrize("unsafe", ["shared", "symlink", "file"])
def test_absent_tmpdir_refuses_unsafe_fallback_without_repairing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unsafe: str
) -> None:
    monkeypatch.delenv("TMPDIR", raising=False)
    cache = tmp_path / "cache"
    cache.mkdir(mode=0o700)
    fallback = cache / "tmp"
    if unsafe == "shared":
        fallback.mkdir()
        fallback.chmod(0o755)
    elif unsafe == "symlink":
        target = tmp_path / "other"
        target.mkdir(mode=0o700)
        fallback.symlink_to(target, target_is_directory=True)
    else:
        _ = fallback.write_bytes(b"retained")
    before = fallback.lstat()
    with pytest.raises((WorkflowError, FileExistsError)):
        _ = Runner(default_tools(), tmp_path / "evidence", cache)
    assert fallback.lstat() == before
