"""Git administrative files are context, never product payload."""

import shutil
from pathlib import Path

import pytest

from kickstarter_workflow.records import Record, load, text
from kickstarter_workflow.workflow import Workflow
from tests.conftest import command


def _contents(*roots: Path) -> dict[Path, tuple[bytes, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mode & 0o777)
        for root in roots
        for path in root.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("layout", ["linked-worktree", "separate-git-dir"])
def test_gitfile_source_prepares_and_resumes_without_copying_administration(
    tmp_path: Path, plan: Record, template_cache: Path, layout: str
) -> None:
    source = tmp_path / "gitfile-source"
    administration = tmp_path / "administration"
    if layout == "linked-worktree":
        command(
            "git",
            "clone",
            "--quiet",
            "--no-hardlinks",
            "--no-checkout",
            "--template=",
            str(template_cache),
            str(administration),
            cwd=tmp_path,
        )
        command(
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "worktree",
            "add",
            "--quiet",
            "--detach",
            "--no-checkout",
            str(source),
            "HEAD",
            cwd=administration,
        )
    else:
        command(
            "git",
            "init",
            "--quiet",
            "--template=",
            "--separate-git-dir",
            str(administration),
            str(source),
            cwd=tmp_path,
        )
    assert (source / ".git").is_file()
    original = Path(text(plan, "source"))
    for name in ("app.py", "test_app.py", "README.md"):
        _ = shutil.copy2(original / name, source / name)
    before = _contents(source, administration)
    request: Record = {**plan, "source": str(source)}
    workflow = Workflow(tmp_path / "gitfile-state")
    prepared = workflow.dispatch("prepare", request)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    assert (workspace / ".git").is_dir()
    assert set(load(workspace.parent / "source.json")) == {"app.py", "test_app.py", "README.md"}
    for name in ("app.py", "test_app.py", "README.md"):
        assert (workspace / "product" / name).read_bytes() == (source / name).read_bytes()
    assert workflow.dispatch("resume", request)["status"] == "prepared"
    assert workflow.dispatch("prepare", request)["workspace"] == str(workspace)
    assert _contents(source, administration) == before
