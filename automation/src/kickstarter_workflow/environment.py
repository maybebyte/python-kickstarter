"""Small explicit PEP 621 environment adapter; no product runtime migration."""

import json
import re
import tomllib
from pathlib import Path
from typing import cast

from kickstarter_workflow.files import inventory, mappings
from kickstarter_workflow.records import (
    Record,
    Value,
    WorkflowError,
    digest,
    no_links,
    object_value,
    text,
)


def environment_identity(workspace: Path) -> Record:
    """Bind the prepared task-local environment and executed interpreter."""
    environment = no_links(workspace / ".venv")
    interpreter = (environment / "bin/python").resolve(strict=True)
    return {
        "path": str(interpreter),
        "sha256": digest(interpreter.read_bytes()),
        "mode": interpreter.stat().st_mode & 0o777,
        "configuration": digest(no_links(environment / "pyvenv.cfg").read_bytes()),
    }


def _strings(value: Value, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise WorkflowError("unsupported environment list: " + label)
    return cast("list[str]", value)


def _local_package(plan: Record, source: Path, metadata: Record, content: str) -> str:
    build = object_value(metadata, "build-system")
    if build.get("build-backend") != "uv_build" or set(build) != {"build-backend", "requires"}:
        raise WorkflowError("only the static default uv_build package layout is supported")
    _ = _strings(build.get("requires"), "build requirements")
    mapped = {text(item, "source"): text(item, "target") for item in mappings(plan)}
    if any(mapped.get(name) != "product/" + name for name in inventory(source)):
        raise WorkflowError(
            "packaged environment requires complete layout-preserving source/assets mapping"
        )
    name = text(object_value(metadata, "project"), "name")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name) is None:
        raise WorkflowError("invalid product distribution name")
    content = content.replace("dev = [\n", "dev = [\n    " + json.dumps(name) + ",\n", 1)
    return (
        content
        + "\n[tool.uv.sources]\n"
        + json.dumps(name)
        + ' = { path = "product", editable = true }\n'
    )


def adapt_environment(plan: Record, source: Path, workspace: Path) -> None:
    """Import static declared dependencies into development-only workbench setup."""
    if not (source / "pyproject.toml").exists():
        if "environment" in plan or any(
            (source / name).exists() for name in ("requirements.txt", "setup.py", "setup.cfg")
        ):
            raise WorkflowError("environment mapping requires a static PEP 621 pyproject.toml")
        return
    selected = object_value(plan, "environment")
    if selected.get("project") != "pyproject.toml" or set(selected) != {
        "project",
        "groups",
        "extras",
    }:
        raise WorkflowError("environment requires project=pyproject.toml, groups and extras")
    if not any(
        item.get("source") == "pyproject.toml" and item.get("target") == "product/pyproject.toml"
        for item in mappings(plan)
    ):
        raise WorkflowError("environment pyproject.toml must be mapped to product/pyproject.toml")
    metadata = cast("Record", tomllib.loads((source / "pyproject.toml").read_text()))
    project = object_value(metadata, "project")
    tools = metadata.get("tool", {})
    if project.get("dynamic") or (isinstance(tools, dict) and "uv" in tools):
        raise WorkflowError("unsupported dynamic metadata or tool.uv environment configuration")
    dependencies = _strings(project.get("dependencies", []), "dependencies")
    for group in _strings(selected["groups"], "groups"):
        dependencies.extend(_strings(object_value(metadata, "dependency-groups").get(group), group))
    for extra in _strings(selected["extras"], "extras"):
        dependencies.extend(
            _strings(object_value(project, "optional-dependencies").get(extra), extra)
        )
    config = workspace / "pyproject.toml"
    content = re.sub(
        r"^requires-python = .+$",
        "requires-python = " + json.dumps(text(project, "requires-python")),
        config.read_text(),
        count=1,
        flags=re.MULTILINE,
    )
    content = content.replace(
        "dev = [\n",
        "dev = [\n" + "".join("    " + json.dumps(dep) + ",\n" for dep in dependencies),
        1,
    )
    if "build-system" in metadata:
        content = _local_package(plan, source, metadata, content)
    content = content.replace('extraPaths = ["product"]', 'extraPaths = ["product", "product/src"]')
    _ = config.write_text(content)
    justfile = workspace / "justfile"
    _ = justfile.write_text(
        justfile.read_text()
        .replace("ruff check", "ruff check --config pyproject.toml")
        .replace("ruff format", "ruff format --config pyproject.toml")
    )
