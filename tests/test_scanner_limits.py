"""Exercise the scanner recipe, including native-engine success and rejection."""

from __future__ import annotations

import json
import os
import resource
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NotRequired, TypedDict, cast

import pytest
import yaml

from tests.conftest import RenderFn, run_in
from tests.test_generation import MINIMAL

SURFACES = ("maintainer", "helper", "generated", "maintainer-ci", "generated-ci")
FIXTURES = Path(__file__).parent / "fixtures"


class _Step(TypedDict):
    run: NotRequired[str]


class _Job(TypedDict):
    steps: list[_Step]


class _Workflow(TypedDict):
    jobs: dict[str, _Job]


@pytest.fixture
def scan_entrypoint(
    surface: str, template_root: Path, render: RenderFn, tmp_path: Path
) -> list[str]:
    """Drive real just parsing or the actual workflow's shell run block."""
    project = template_root
    if surface.startswith("generated"):
        project = render({**MINIMAL, "enable_scanners": True}, tmp_path / "generated")
    elif surface == "helper":
        project /= "automation"
    if surface.endswith("-ci"):
        name = "scan.yml" if surface == "generated-ci" else "test-template.yml"
        workflow = cast(
            "_Workflow", yaml.safe_load((project / ".github" / "workflows" / name).read_text())
        )
        bodies = [
            step.get("run", "")
            for step in workflow["jobs"]["scan"]["steps"]
            if "semgrep@" in step.get("run", "")
        ]
        assert len(bodies) == 1
        # A later command in the SAME shell is the stricter isolation control;
        # actual CI launches its later gitleaks step in a fresh shell.
        return ["bash", "-eu", "-o", "pipefail", "-c", bodies[0] + "\ngitleaks"]
    return ["just", "--justfile", str(project / "justfile"), "scan"]


def _observe(
    tmp_path: Path,
    command: list[str],
    soft: str,
    hard: str,
    *,
    scanner_exit: int = 0,
    gitleaks_exit: int = 0,
    fault: str = "",
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    inherited = resource.getrlimit(resource.RLIMIT_STACK)[1]
    if inherited != resource.RLIM_INFINITY and (
        hard == "unlimited" or int(hard) * 1024 > inherited
    ):
        pytest.skip("This host cannot raise its inherited finite hard stack for this case")
    tools = tmp_path / "recorders"
    tools.mkdir()
    for name in ("uvx", "gitleaks"):
        _ = shutil.copyfile(FIXTURES / "scanner_observer.sh", tools / name)
        (tools / name).chmod(0o755)
    events = tmp_path / "events"
    env = dict(os.environ) | {
        "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
        "SCAN_EVENTS": str(events),
        "INITIAL_SOFT": soft,
        "INITIAL_HARD": hard,
        "SCANNER_EXIT": str(scanner_exit),
        "GITLEAKS_EXIT": str(gitleaks_exit),
    }
    if fault:
        env.update(BASH_ENV=str(FIXTURES / "scanner_fault.sh"), LIMIT_FAULT=fault)
    result = subprocess.run(
        ["bash", str(FIXTURES / "scanner_caller.sh"), *command],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return result, [line.split("\t") for line in events.read_text().splitlines()]


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize(
    ("soft", "hard", "scanner_soft", "scanner_hard"),
    [
        ("8192", "unlimited", "8192", "1048576"),
        ("unlimited", "unlimited", "1048576", "1048576"),
        ("2097152", "unlimited", "1048576", "1048576"),
        ("1048576", "unlimited", "1048576", "1048576"),
        ("8192", "16384", "8192", "16384"),
        ("8192", "2097152", "8192", "2097152"),
    ],
)
def test_scanner_limits_are_child_only(
    scan_entrypoint: list[str],
    tmp_path: Path,
    soft: str,
    hard: str,
    scanner_soft: str,
    scanner_hard: str,
) -> None:
    result, events = _observe(tmp_path, scan_entrypoint, soft, hard)
    assert result.returncode == 0, result.stdout + result.stderr
    assert events == [
        ["before", soft, hard],
        ["uvx", scanner_soft, scanner_hard],
        ["gitleaks", soft, hard],
        ["after", soft, hard],
    ]


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("scanner_exit", [1, 2, 17])
def test_scanner_failure_stops_later_stage(
    scan_entrypoint: list[str], tmp_path: Path, scanner_exit: int
) -> None:
    result, events = _observe(
        tmp_path, scan_entrypoint, "8192", "unlimited", scanner_exit=scanner_exit
    )
    assert result.returncode == scanner_exit, result.stdout + result.stderr
    assert events == [
        ["before", "8192", "unlimited"],
        ["uvx", "8192", "1048576"],
        ["after", "8192", "unlimited"],
    ]


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("fault", ["-H -s", "-S -s", "-S -s 1048576", "-H -s 1048576"])
def test_limit_failure_never_starts_scanner(
    scan_entrypoint: list[str], tmp_path: Path, fault: str
) -> None:
    result, events = _observe(tmp_path, scan_entrypoint, "unlimited", "unlimited", fault=fault)
    assert result.returncode == 73, result.stdout + result.stderr
    assert events == [
        ["before", "unlimited", "unlimited"],
        ["after", "unlimited", "unlimited"],
    ]


@pytest.mark.parametrize("surface", SURFACES)
def test_gitleaks_failure_still_propagates(scan_entrypoint: list[str], tmp_path: Path) -> None:
    result, events = _observe(tmp_path, scan_entrypoint, "8192", "unlimited", gitleaks_exit=19)
    assert result.returncode == 19, result.stdout + result.stderr
    assert events[-2:] == [
        ["gitleaks", "8192", "unlimited"],
        ["after", "8192", "unlimited"],
    ]


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize(
    ("soft_bytes", "expected_soft"),
    [(1073741823, 1073741823), (1073741824, 1073741824), (1073741825, 1073741824)],
)
def test_soft_limit_preservation_uses_the_actual_byte_boundary(
    scan_entrypoint: list[str], tmp_path: Path, soft_bytes: int, expected_soft: int
) -> None:
    if resource.getrlimit(resource.RLIMIT_STACK)[1] != resource.RLIM_INFINITY:
        pytest.skip("This case requires an inherited unlimited hard stack")
    tools = tmp_path / "byte-recorders"
    tools.mkdir()
    _ = (tools / "uvx").write_text(
        '#!/usr/bin/env bash\nexec "$PROBE_PYTHON" "$PROBE_SOURCE" observe\n'
    )
    _ = (tools / "gitleaks").write_text("#!/usr/bin/env bash\nexit 0\n")
    for name in ("uvx", "gitleaks"):
        (tools / name).chmod(0o755)
    events = tmp_path / "byte-events"
    helper = FIXTURES / "scanner_bytes.py"
    result = subprocess.run(
        [sys.executable, str(helper), *scan_entrypoint],
        env=dict(os.environ)
        | {
            "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
            "PROBE_PYTHON": sys.executable,
            "PROBE_SOURCE": str(helper),
            "SOFT_BYTES": str(soft_bytes),
            "BYTE_EVENTS": str(events),
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=35,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(events.read_text()) == [expected_soft, 1073741824]


def test_scan_distinguishes_clean_input_from_blocking_finding(
    render: RenderFn, tmp_path: Path
) -> None:
    """An engine startup error must satisfy neither the clean nor violation control."""
    project = render({**MINIMAL, "enable_scanners": True}, tmp_path / "out")
    tools = tmp_path / "tools"
    tools.mkdir()
    # Observe the later stage without requiring gitleaks in the generation harness.
    gitleaks = tools / "gitleaks"
    _ = gitleaks.write_text('#!/usr/bin/env bash\nprintf "gitleaks-reached\\n"\n')
    gitleaks.chmod(0o755)
    env = {"PATH": f"{tools}{os.pathsep}{os.environ['PATH']}"}
    clean = run_in(project, "just", "scan", check=False, env=env)
    assert clean.returncode == 0, clean.stdout + clean.stderr
    assert "gitleaks-reached" in clean.stdout.splitlines()

    _ = (project / "src" / "demo_project" / "danger.py").write_text(
        "def run(expr: str) -> object:\n    return eval(expr)\n"
    )
    blocked = run_in(project, "just", "scan", check=False, env=env)
    assert blocked.returncode == 1, blocked.stdout + blocked.stderr
    assert "no-eval" in blocked.stdout, blocked.stdout + blocked.stderr
    assert "gitleaks-reached" not in blocked.stdout.splitlines()
