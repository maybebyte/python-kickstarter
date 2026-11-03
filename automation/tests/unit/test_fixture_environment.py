"""Fixture Git operations stay in disposable repositories despite inherited selectors."""

import json
import sys
from pathlib import Path

import pytest

from tests.conftest import command

SELECTORS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_PREFIX",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_GRAFT_FILE",
    "GIT_SHALLOW_FILE",
    "GIT_NAMESPACE",
    "GIT_REPLACE_REF_BASE",
    "GIT_NO_REPLACE_OBJECTS",
)


@pytest.mark.parametrize("selector", SELECTORS)
def test_fixture_command_clears_repository_selectors_and_preserves_foreign_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    selector: str,
) -> None:
    source, foreign = tmp_path / "fixture", tmp_path / "foreign"
    for root, value in ((source, "fixture payload\n"), (foreign, "foreign sentinel\n")):
        command("git", "init", "--quiet", "--template=", str(root), cwd=tmp_path)
        _ = (root / "sentinel.txt").write_text(value)
        command("git", "add", "sentinel.txt", cwd=root)
    before = {path: path.read_bytes() for path in foreign.rglob("*") if path.is_file()}
    modes = {path: path.stat().st_mode & 0o777 for path in [foreign, *foreign.rglob("*")]}
    for path in modes:
        path.chmod(0o500 if path.is_dir() else 0o400)
    values = {
        "GIT_DIR": str(foreign / ".git"),
        "GIT_WORK_TREE": str(foreign),
        "GIT_INDEX_FILE": str(foreign / ".git/index"),
        "GIT_OBJECT_DIRECTORY": str(foreign / ".git/objects"),
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(foreign / ".git/objects"),
        "GIT_COMMON_DIR": str(foreign / ".git"),
        "GIT_GRAFT_FILE": str(foreign / "grafts"),
        "GIT_SHALLOW_FILE": str(foreign / "shallow"),
        "GIT_IMPLICIT_WORK_TREE": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    _ = capfd.readouterr()
    try:
        with monkeypatch.context() as inherited:
            inherited.setenv(selector, values.get(selector, "foreign"))
            command("git", "add", "sentinel.txt", cwd=source)
            command("git", "show", ":sentinel.txt", cwd=source)
            assert capfd.readouterr().out == "fixture payload\n"
            probe = Path(__file__).resolve().parents[1] / "fixtures/environment_probe.py"
            command(sys.executable, str(probe), selector, cwd=source)
            assert json.loads(capfd.readouterr().out) == {selector: None}
        assert {path: path.read_bytes() for path in foreign.rglob("*") if path.is_file()} == before
    finally:
        for path, mode in modes.items():
            path.chmod(mode)


def test_fixture_command_preserves_controlled_git_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "gitconfig"
    _ = config.write_text("[fixture]\n    origin = global-control\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "fixture.transport")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "offline-control")
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
    command("git", "config", "--get", "fixture.origin", cwd=tmp_path)
    assert capfd.readouterr().out == "global-control\n"
    command("git", "config", "--get", "fixture.transport", cwd=tmp_path)
    assert capfd.readouterr().out == "offline-control\n"
    probe = Path(__file__).resolve().parents[1] / "fixtures/environment_probe.py"
    command(sys.executable, str(probe), "GIT_ALLOW_PROTOCOL", cwd=tmp_path)
    assert json.loads(capfd.readouterr().out) == {"GIT_ALLOW_PROTOCOL": "file"}
