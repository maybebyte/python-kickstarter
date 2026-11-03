"""Admission of generated gates; existing reviewed configuration is not a default."""

import re
import tomllib
from pathlib import Path
from typing import cast

from kickstarter_workflow.files import string_list
from kickstarter_workflow.records import Record, WorkflowError, object_value


def coverage_floor(workspace: Path) -> float:
    """Read the actual approved project threshold, including existing choices."""
    config = cast("Record", tomllib.loads((workspace / "pyproject.toml").read_text()))
    report = object_value(object_value(object_value(config, "tool"), "coverage"), "report")
    floor = float(str(report.get("fail_under", 0)))
    if not 0 < floor <= 100:
        raise WorkflowError("invalid project coverage threshold")
    return floor


def gate_policy(workspace: Path, *, existing: bool) -> None:
    """Validate CI membership without imposing new-project defaults on reuse."""
    config = cast("Record", tomllib.loads((workspace / "pyproject.toml").read_text()))
    tools = object_value(config, "tool")
    lint = object_value(object_value(tools, "ruff"), "lint")
    types = object_value(tools, "basedpyright")
    floor = coverage_floor(workspace)
    required = {"fmt-check", "lint", "typecheck", "test"}
    optional = {
        "enable_property_tests": "fuzz",
        "enable_policy_tests": "policy",
        "enable_dependency_audit": "audit",
    }
    if existing:
        answers = (workspace / ".copier-answers.yml").read_text()
        for key, gate in optional.items():
            match = re.search(rf"^{key}: (true|false)$", answers, re.MULTILINE)
            if match is None:
                raise WorkflowError("missing generated gate provenance: " + key)
            if match[1] == "true":
                required.add(gate)
    else:
        required.update(optional.values())
        if (
            "ALL" not in string_list(lint, "select")
            or types.get("typeCheckingMode") != "recommended"
            or floor < 85
        ):
            raise WorkflowError("mandatory strict template gates weakened")
    match = re.search(r"^ci:\s*(.+)$", (workspace / "justfile").read_text(), re.MULTILINE)
    if match is None or not required.issubset(match[1].split()):
        raise WorkflowError("mandatory template CI membership missing")
