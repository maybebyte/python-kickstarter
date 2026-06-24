"""Shared fixtures for the template generation tests."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TypeAlias

import copier
import pytest

REQUIRED_TOOLS = ("uv", "just", "git")

RenderFn: TypeAlias = Callable[[Mapping[str, object], Path], Path]


def _missing_tools() -> list[str]:
    return [t for t in REQUIRED_TOOLS if shutil.which(t) is None]


@pytest.fixture(scope="session")
def template_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def render(template_root: Path) -> RenderFn:
    """Render the template into a fresh dir. Fails closed if tools are missing."""

    missing = _missing_tools()
    if missing:
        pytest.fail(f"required tools not on PATH: {missing}")

    def _render(data: Mapping[str, object], dst: Path) -> Path:
        # Generation renders skip the slow pre-commit hook-install task (the config
        # does not exist until that layer is added). A dedicated test in Task 7
        # exercises the install path with the flag left at its default.
        copier.run_copy(
            str(template_root),
            str(dst),
            data={"enable_precommit_install": False, **data},
            defaults=True,
            unsafe=True,
            overwrite=True,
            quiet=True,
        )
        return dst

    return _render


def run_in(project: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a command inside a rendered project; capture output for assertions."""
    return subprocess.run(  # noqa: S603
        list(args),
        cwd=project,
        check=check,
        capture_output=True,
        text=True,
    )
