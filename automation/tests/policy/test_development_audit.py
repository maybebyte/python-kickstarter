"""Helper CI retains runtime auditing and audits its locked development tools."""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import cast

import pytest

from kickstarter_workflow.process import Runner, default_tools
from kickstarter_workflow.records import Value, load, object_value, text

ROOT = Path(__file__).resolve().parents[2]


def test_complete_gate_requires_both_audits(tmp_path: Path) -> None:
    runner = Runner(default_tools(), tmp_path / "evidence", tmp_path / "cache")
    _ = runner.run(["just", "--dump", "--dump-format", "json"], ROOT)
    recipes = object_value(load(runner.last_output), "recipes")
    dependencies = object_value(recipes, "ci")["dependencies"]
    assert isinstance(dependencies, list)
    assert {"fmt-check", "lint", "typecheck", "test", "fuzz", "policy", "audit", "audit-dev"} <= {
        text(item, "recipe") for item in dependencies if isinstance(item, dict)
    }


@pytest.mark.parametrize(("export_exit", "audit_exit"), [(0, 0), (19, 0), (0, 17)])
def test_complete_gate_audits_nonempty_development_export_and_propagates_failure(
    tmp_path: Path, export_exit: int, audit_exit: int
) -> None:
    for name in ("justfile", "pyproject.toml", "uv.lock"):
        _ = shutil.copy2(ROOT / name, tmp_path / name)
    executable = tmp_path / "bin/uv"
    executable.parent.mkdir()
    fixture = ROOT / "tests/fixtures/audit_tool.py"
    _ = executable.write_text(f"#!{sys.executable}\n" + fixture.read_text())
    executable.chmod(0o700)
    observations = tmp_path / "audits.jsonl"
    runner = Runner(default_tools(), tmp_path / "evidence", tmp_path / "cache")
    runner.env.update(
        {
            "PATH": str(executable.parent) + os.pathsep + runner.env["PATH"],
            "REAL_UV": runner.tools["uv"],
            "EXPORT_EXIT": str(export_exit),
            "AUDIT_EXIT": str(audit_exit),
            "AUDIT_OBSERVATIONS": str(observations),
        }
    )
    _ = runner.run(["just", "ci"], tmp_path, allow_failure=True)
    assert runner.last_exit == (export_exit or audit_exit)
    if export_exit:
        assert not observations.exists()
    else:
        audits: list[list[str]] = []
        for line in observations.read_text().splitlines():
            packages = cast("Value", json.loads(line))
            assert isinstance(packages, list)
            assert all(isinstance(item, str) for item in packages)
            audits.append(cast("list[str]", packages))
        if not audit_exit:
            assert [] in audits  # The runtime-only graph remains honestly empty.
        assert any(
            {"copier", "uv", "pytest", "hypothesis", "ruff", "basedpyright"} <= set(packages)
            for packages in audits
        )
