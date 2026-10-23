"""Controlled POSIX tool execution with durable raw results, never shell markers."""

import contextlib
import os
import shutil
import signal
import time
import uuid
from pathlib import Path

from kickstarter_workflow.records import (
    Record,
    Value,
    WorkflowError,
    digest,
    no_links,
    private_directory,
    save,
    text,
)

PINS = {"copier": "copier 9.15.2", "uv": "uv 0.13.4"}


def _wait(pid: int, timeout: int) -> int:
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            child, status = os.waitpid(pid, os.WNOHANG)
            if child:
                return os.waitstatus_to_exitcode(status)
            time.sleep(0.02)
        raise WorkflowError("tool timed out")
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, signal.SIGKILL)
        with contextlib.suppress(ChildProcessError):
            _ = os.waitpid(pid, 0)


class Runner:
    """Resolve an explicit toolbox and retain every invocation before executing it."""

    def __init__(self, tools: Record, evidence: Path, cache: Path) -> None:
        """Create an invocation directory and task-local cache environment."""
        private_directory(evidence)
        self.evidence: Path = evidence
        self.cache: Path = cache
        self.last_exit: int = 0
        self.last_output: Path = evidence / "not-started"
        self.tools: dict[str, str] = {}
        for name in ("git", "copier", "uv", "just"):
            path = Path(text(tools, name))
            if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
                raise WorkflowError(f"missing executable tool: {name}")
            self.tools[name] = str(path.resolve())
        self.env: dict[str, str] = {
            "HOME": str(Path.home()),
            "PATH": os.pathsep.join(
                dict.fromkeys(
                    [*(str(Path(p).parent) for p in self.tools.values()), "/usr/bin", "/bin"]
                )
            ),
            "TMPDIR": os.environ.get("TMPDIR", str(cache / "tmp")),
            "UV_CACHE_DIR": str(cache / "uv"),
            "UV_PYTHON_INSTALL_DIR": str(cache / "python"),
            "UV_NO_CONFIG": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": os.devnull,
            "PYTHONHASHSEED": "0",
        }

    def run(
        self, args: list[str], cwd: Path, *, timeout: int = 600, allow_failure: bool = False
    ) -> str:
        """Run an allowlisted executable, capturing status and unmodified output."""
        if not args or args[0] not in self.tools:
            raise WorkflowError("command executable is not in the approved toolbox")
        _ = no_links(cwd)
        executable = self.tools[args[0]]
        token = uuid.uuid4().hex
        record = self.evidence / f"{token}.json"
        output = self.evidence / f"{token}.log"
        self.last_output = output
        command: list[Value] = [executable, *args[1:]]
        result: Record = {
            "argv": command,
            "cwd": str(cwd),
            "status": "running",
            "output": str(output),
        }
        save(record, result)
        actions = [
            (os.POSIX_SPAWN_OPEN, 1, str(output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600),
            (os.POSIX_SPAWN_DUP2, 1, 2),
        ]
        previous = Path.cwd()
        try:
            os.chdir(cwd)
            pid = os.posix_spawn(
                executable, [executable, *args[1:]], self.env, file_actions=actions, setpgroup=0
            )
        finally:
            os.chdir(previous)
        exit_code = _wait(pid, timeout)
        self.last_exit = exit_code
        result.update(
            {
                "status": "passed" if exit_code == 0 else "failed",
                "exit": exit_code,
                "output_sha256": digest(output.read_bytes()),
            }
        )
        save(record, result)
        content = output.read_text(errors="replace")
        if exit_code and not allow_failure:
            raise WorkflowError(f"{args[0]} failed ({exit_code}); raw result: {record}")
        return content.strip()

    def child(self) -> "Runner":
        """Create a separate immutable evidence namespace for a verification phase."""
        return Runner(
            dict(self.tools),
            self.evidence / uuid.uuid4().hex,
            self.cache,
        )

    def identities(self, cwd: Path) -> Record:
        """Bind executable bytes and versions, enforcing the reviewed tool pins."""
        identities: Record = {}
        for name, path in self.tools.items():
            version = self.run([name, "--version"], cwd)
            if name in PINS and not (version == PINS[name] or version.startswith(PINS[name] + " ")):
                raise WorkflowError(f"unapproved {name} version")
            identities[name] = {
                "path": path,
                "sha256": digest(Path(path).read_bytes()),
                "version": version,
            }
        return identities


def default_tools() -> Record:
    """Discover explicit executable paths for a plan, without installing anything."""
    return {name: shutil.which(name) for name in ("git", "copier", "uv", "just")}
