"""Real-process, real-Git fixtures; no synthetic Copier output."""

import os
import shutil
from pathlib import Path

import pytest

from kickstarter_workflow.records import Record

PIN = "37adbeeea53a242ed25db602a35b9d719d95c8ae"
CANONICAL = "https://github.com/maybebyte/python-kickstarter.git"


def command(*args: str, cwd: Path) -> None:
    executable = shutil.which(args[0])
    assert executable is not None
    old = Path.cwd()
    os.chdir(cwd)
    try:
        pid = os.posix_spawn(executable, args, dict(os.environ))
        _, status = os.waitpid(pid, 0)
        assert os.waitstatus_to_exitcode(status) == 0
    finally:
        os.chdir(old)


@pytest.fixture(scope="session")
def template_cache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("canonical-template")
    repository = Path(__file__).resolve().parents[2]
    command(
        "git",
        "clone",
        "--quiet",
        "--no-hardlinks",
        str(repository),
        str(root / "template"),
        cwd=root,
    )
    cache = root / "template"
    command("git", "checkout", "--quiet", "--detach", PIN, cwd=cache)
    command("git", "remote", "set-url", "origin", CANONICAL, cwd=cache)
    return cache


@pytest.fixture
def plan(tmp_path: Path, template_cache: Path) -> Record:
    source = tmp_path / "source"
    source.mkdir()
    command("git", "init", "--quiet", str(source), cwd=tmp_path)
    _ = (source / "app.py").write_text(
        '"""A maintained calculation."""\n\n\ndef twice(value: int) -> int:\n    """Double a value."""\n    return value * 2\n'
    )
    _ = (source / "test_app.py").write_text(
        '"""Product regression."""\n\nfrom app import twice\n\n\ndef test_twice() -> None:\n    assert twice(3) == 6\n'
    )
    _ = (source / "README.md").write_text("Product contract: double the input.\n")
    tools: Record = {name: str(shutil.which(name)) for name in ("git", "copier", "uv", "just")}
    return {
        "project": "sample",
        "task": "one",
        "mode": "workbench",
        "source": str(source),
        "template": {"source": CANONICAL, "revision": PIN, "cache": str(template_cache)},
        "tools": tools,
        "answers": {
            "project_name": "Sample",
            "package_name": "sample",
            "author_name": "Test Author",
            "author_email": "test@example.invalid",
            "license": "ISC",
            "python_version": "3.11",
            "project_type": "library",
            "description": "Contract fixture.",
        },
        "mapping": [
            {"source": "app.py", "target": "product/app.py", "role": "source"},
            {"source": "test_app.py", "target": "product/test_app.py", "role": "test"},
            {"source": "README.md", "target": "product/README.md", "role": "context"},
        ],
        "repository_checks": [
            [
                "uv",
                "run",
                "--project",
                "{workspace}",
                "pytest",
                "--override-ini=addopts=",
                "test_app.py",
            ]
        ],
        "scope_review": "Complete source, test and context slice; no other repository gates exist.",
    }
