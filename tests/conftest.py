"""Shared fixtures for the template generation tests."""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
from collections.abc import Callable, Generator, Mapping
from pathlib import Path
from typing import TypeAlias

import copier
import pytest
from plumbum import local

REQUIRED_TOOLS = ("uv", "just", "git")

RenderFn: TypeAlias = Callable[[Mapping[str, object], Path], Path]

# A real `copier copy` resolves the generated project's interpreter from its own
# requires-python, downloading one when none compatible is installed. The harness must
# reproduce that environment, not its own: `just test` runs under `uv run` (which exports
# VIRTUAL_ENV) and the CI matrix's astral-sh/setup-uv exports UV_PYTHON=<matrix python>.
# Either, inherited by copier's copy-time `uv lock`/`uv sync` _tasks, pins the rendered
# project to the maintainer's interpreter and aborts every matrix Python below the rendered
# python_version (default 3.13). copier runs those _tasks through plumbum's local.env -- a
# SNAPSHOT of os.environ taken at import, not the live os.environ -- so the pins must be
# cleared from BOTH, with managed downloads enabled so uv can fetch the interpreter the
# rendered project actually needs.
_INTERPRETER_PINS = ("UV_PYTHON", "VIRTUAL_ENV")
_MANAGED_VARS = (*_INTERPRETER_PINS, "UV_PYTHON_DOWNLOADS")


def _clean_env() -> dict[str, str]:
    """os.environ for a subprocess driving a rendered project: pins out, uv downloads on."""
    env = {name: value for name, value in os.environ.items() if name not in _INTERPRETER_PINS}
    env["UV_PYTHON_DOWNLOADS"] = "automatic"
    return env


def _restore_pins(saved_os: Mapping[str, str | None], saved_pl: Mapping[str, str | None]) -> None:
    for name, value in saved_os.items():
        if value is None:
            _ = os.environ.pop(name, None)
        else:
            os.environ[name] = value
    for name, value in saved_pl.items():
        if value is None:
            if name in local.env:
                del local.env[name]
        else:
            local.env[name] = value


@contextlib.contextmanager
def without_interpreter_pins() -> Generator[None]:
    """Build or drive a rendered project as a real `copier copy` would.

    The interpreter pins are cleared and managed downloads enabled, in os.environ AND
    plumbum's local.env (copier's task channel).
    """
    saved_os = {name: os.environ.get(name) for name in _MANAGED_VARS}
    saved_pl = {name: local.env.get(name) for name in _MANAGED_VARS}
    for name in _INTERPRETER_PINS:
        _ = os.environ.pop(name, None)
        if name in local.env:
            del local.env[name]
    os.environ["UV_PYTHON_DOWNLOADS"] = "automatic"
    local.env["UV_PYTHON_DOWNLOADS"] = "automatic"
    try:
        yield
    finally:
        _restore_pins(saved_os, saved_pl)


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
        # The copy-time `uv lock`/`uv sync` _tasks must resolve against the generated
        # project's requires-python, not a leaked UV_PYTHON/VIRTUAL_ENV (see the pins note).
        with without_interpreter_pins():
            _ = copier.run_copy(
                str(template_root),
                str(dst),
                data={"enable_precommit_install": False, **data},
                # Copy the working template (HEAD), not copier's default of the latest
                # release tag — otherwise the suite would validate the released template
                # and silently ignore every change since. (run_update tests pin their ref.)
                vcs_ref="HEAD",
                defaults=True,
                unsafe=True,
                overwrite=True,
                quiet=True,
            )
        return dst

    return _render


def run_in(project: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a command inside a rendered project; capture output for assertions."""
    # A rendered project's own tooling (`just ci`, `uv run ...`) must not inherit the
    # maintainer's interpreter pins, or uv rebuilds its venv against the wrong Python.
    return subprocess.run(
        list(args),
        cwd=project,
        check=check,
        capture_output=True,
        text=True,
        env=_clean_env(),
    )
