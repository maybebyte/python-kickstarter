"""Keep the helper's generated gates on the maintainer delivery path."""

import argparse
import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import cast

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent


def _preflight(script: str) -> None:
    # Confinement, not the policy oracle: only inert stand-ins and boolean shell
    # composition may execute. No expansions, redirects, backgrounding or paths
    # outside this fixture. Extend this small vocabulary only after review.
    allowed = {
        "uv",
        "sync",
        "--locked",
        "--project",
        "automation",
        "just",
        "--justfile",
        "automation/justfile",
        "ci",
        "automation-ci",
        "true",
        "false",
        "||",
        "&&",
        ";",
        "--project=automation",
        "--justfile=automation/justfile",
    }
    for line in script.splitlines():
        command = line.strip().lstrip("@-")
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
        assert set(tokens) <= allowed, tokens


def _bash_arguments(shell: str) -> list[str]:
    # GitHub's Linux default is `bash -e {0}`; explicit `bash` adds pipefail.
    # Custom templates keep their own options. Admit only inert Bash options,
    # never startup files, command strings, other interpreters or extra operands.
    if shell == "bash":
        shell = "bash --noprofile --norc -e -o pipefail {0}"
    tokens = shlex.split(shell)
    assert tokens
    assert shell.split(maxsplit=1)[0] == "bash"
    assert tokens[-1] == "{0}"
    arguments = tokens[1:-1]
    assert all(
        argument in {"--noprofile", "--norc", "pipefail"}
        or re.fullmatch(r"-[euo]+", argument) is not None
        for argument in arguments
    )
    return arguments


def _effective_shell(
    workflow: dict[str, object], job: dict[str, object], step: dict[str, object]
) -> str:
    shell: object = "bash -e {0}"
    for scope in (workflow, job):
        defaults = cast("dict[str, dict[str, object]]", scope.get("defaults", {}))
        shell = defaults.get("run", {}).get("shell", shell)
    shell = step.get("shell", shell)
    assert isinstance(shell, str)
    return shell


def _constant_boolean(condition: object, *, expected: bool) -> bool:
    # Admit equivalent constant flags, not a general expression interpreter.
    if condition is expected:
        return True
    if not isinstance(condition, str):
        return False
    expression = condition.strip()
    if expression.startswith("${{") and expression.endswith("}}"):
        expression = expression[3:-2].strip()
    return expression == ("true" if expected else "false")


def _probe(
    tmp_path: Path,
    script: str,
    *,
    recipe: bool,
    sync_exit: int,
    gate_exit: int,
    shell: str = "bash -e {0}",
) -> None:
    _preflight(script)
    arguments = _bash_arguments(shell)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # These external-command stand-ins record the real argv, not source spelling.
    # They cannot install dependencies or run the expensive helper gate.
    for name, status in (("uv", sync_exit), ("just", gate_exit)):
        executable = bin_dir / name
        _ = executable.write_text(
            "\n".join(
                [
                    "#!/bin/sh",
                    f'printf "%s\\n" "$@" >> "$PROBE_ROOT/{name}.log"',
                    f'printf "\\n" >> "$PROBE_ROOT/{name}.log"',
                    f"exit {status}",
                    "",
                ]
            )
        )
        executable.chmod(0o700)
    bash = shutil.which("bash")
    just = shutil.which("just")
    assert bash is not None
    assert just is not None
    (bin_dir / "bash").symlink_to(bash)
    env = {
        "PATH": str(bin_dir),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "PROBE_ROOT": str(tmp_path),
    }
    if recipe:
        parsed = cast(
            "dict[str, dict[str, dict[str, object]]]",
            json.loads(
                subprocess.check_output(
                    [just, "--dump", "--dump-format", "json"],
                    cwd=ROOT,
                    env=env,
                    text=True,
                    timeout=10,
                )
            ),
        )
        recipe_shell = parsed["settings"]["shell"]
        assert recipe_shell["command"] == "bash"
        shell_args = cast("list[str]", recipe_shell["arguments"])
        assert set(shell_args) <= {"-e", "-u", "-eu", "-ue", "-c", "-o", "pipefail"}
        setting = "set shell := " + json.dumps(["bash", *shell_args])
        _ = (tmp_path / "justfile").write_text(setting + "\nautomation-ci:\n" + script)
        command = [just, "automation-ci"]
    else:
        script_path = tmp_path / "gate.sh"
        _ = script_path.write_text(script)
        command = [bash, *arguments, str(script_path)]
    result = subprocess.run(
        command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10, check=False
    )
    assert result.returncode == (sync_exit or gate_exit), result
    if recipe:
        sync = argparse.ArgumentParser()
        _ = sync.add_argument("operation", choices=["sync"])
        _ = sync.add_argument("--project")
        _ = sync.add_argument("--locked", action="store_true")
        calls = (tmp_path / "uv.log").read_text().strip().split("\n\n")
        assert calls
        for call in calls:
            options = cast("dict[str, object]", vars(sync.parse_args(call.splitlines())))
            assert options["project"] == "automation"
            assert options["locked"] is True
    gate_log = tmp_path / "just.log"
    if sync_exit:
        assert not gate_log.exists()
    else:
        gate = argparse.ArgumentParser()
        _ = gate.add_argument("--justfile")
        _ = gate.add_argument("target")
        calls = gate_log.read_text().strip().split("\n\n")
        assert calls
        for call in calls:
            options = cast("dict[str, object]", vars(gate.parse_args(call.splitlines())))
            assert options["justfile"] == ("automation/justfile" if recipe else None)
            assert options["target"] == ("ci" if recipe else "automation-ci")


def test_automation_gate_is_required_locally_and_in_ci() -> None:
    justfile = (ROOT / "justfile").read_text()
    ci = re.search(r"^ci: (.+)$", justfile, re.MULTILINE)
    assert ci is not None
    assert "automation-ci" in ci.group(1).split()
    workflow = cast(
        "dict[str, object]",
        yaml.safe_load((ROOT / ".github" / "workflows" / "test-template.yml").read_text()),
    )
    jobs = cast("dict[str, object]", workflow["jobs"])
    job = cast("dict[str, object]", jobs["automation"])
    assert _constant_boolean(job.get("continue-on-error", False), expected=False)
    assert _constant_boolean(job.get("if", True), expected=True)
    steps = cast("list[dict[str, object]]", job["steps"])
    gate_steps = [step for step in steps if "automation-ci" in str(step.get("run", ""))]
    assert gate_steps
    for step in gate_steps:
        assert _constant_boolean(step.get("continue-on-error", False), expected=False)
        assert _constant_boolean(step.get("if", True), expected=True)
        env = cast("dict[str, object]", step["env"])
        assert env["TMPDIR"] == "${{ runner.temp }}"
        assert env["HYPOTHESIS_PROFILE"] == "ci"


@pytest.mark.parametrize(("sync_exit", "gate_exit"), [(0, 0), (19, 0), (0, 17)])
def test_local_gate_propagates_failures(tmp_path: Path, sync_exit: int, gate_exit: int) -> None:
    justfile = (ROOT / "justfile").read_text()
    recipe = re.search(r"^automation-ci:\n((?:[ \t]+[^\n]*\n)+)", justfile, re.MULTILINE)
    assert recipe is not None
    _probe(tmp_path, recipe.group(1), recipe=True, sync_exit=sync_exit, gate_exit=gate_exit)


@pytest.mark.parametrize("gate_exit", [0, 17])
def test_ci_gate_propagates_failures(tmp_path: Path, gate_exit: int) -> None:
    workflow = cast(
        "dict[str, object]",
        yaml.safe_load((ROOT / ".github" / "workflows" / "test-template.yml").read_text()),
    )
    jobs = cast("dict[str, dict[str, object]]", workflow["jobs"])
    job = jobs["automation"]
    steps = cast("list[dict[str, object]]", job["steps"])
    gate_steps = [step for step in steps if "automation-ci" in str(step.get("run", ""))]
    assert gate_steps
    for index, step in enumerate(gate_steps):
        shell = _effective_shell(workflow, job, step)
        directory = tmp_path / str(index)
        directory.mkdir()
        _probe(
            directory,
            str(step["run"]),
            recipe=False,
            sync_exit=0,
            gate_exit=gate_exit,
            shell=shell,
        )


@pytest.mark.parametrize(
    ("script", "shell"),
    [
        ("uv sync --project ../outside --locked", "bash"),
        ("just automation-ci > outside", "bash"),
        ("just $(true)", "bash"),
        ("just automation-ci &", "bash"),
        ("just automation-ci", "sh {0}"),
        ("just automation-ci", "bash -c {0}"),
        ("just automation-ci", "bash --rcfile outside {0}"),
        ("just automation-ci", "bash {0} outside"),
    ],
)
def test_gate_probe_refuses_unreviewed_shell_before_execution(
    tmp_path: Path, script: str, shell: str
) -> None:
    with pytest.raises(AssertionError):
        _probe(tmp_path, script, recipe=False, sync_exit=0, gate_exit=0, shell=shell)
    assert not list(tmp_path.iterdir())
