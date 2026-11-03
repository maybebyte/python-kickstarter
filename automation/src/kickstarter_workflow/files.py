"""Complete inventories and explicit source/test/context mappings."""

import os
import shutil
import stat
from pathlib import Path, PurePosixPath

from kickstarter_workflow.records import Record, Value, WorkflowError, digest, no_links, text

IGNORED = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        ".hypothesis",
        ".mypy_cache",
        "htmlcov",
        "mutants",
    }
)
REPORTS = frozenset({".coverage", "coverage.xml", "coverage.json", "requirements-audit.txt"})


def confined(root: Path, relative: str) -> Path:
    """Resolve one canonical portable relative path without following links."""
    parsed = PurePosixPath(relative)
    if (
        not relative
        or parsed.is_absolute()
        or str(parsed) != relative
        or any(part in {"..", ".git", ".venv"} for part in parsed.parts)
        or "\\" in relative
        or any(ord(char) < 32 for char in relative)
    ):
        raise WorkflowError("unsafe relative path")
    return no_links(root / relative)


def inventory(root: Path, plan: Record | None = None, *, destination: bool = False) -> Record:
    """Fingerprint regular files, including declared assets excluded from discovery."""
    _ = no_links(root)
    result: Record = {}
    for directory, directories, files in os.walk(
        root, followlinks=False, onerror=_raise_scan_error
    ):
        current = Path(directory)
        for name in [*directories, *files]:
            if (current / name).is_symlink():
                raise WorkflowError("symlink in inventory")
        directories[:] = sorted(name for name in directories if name not in IGNORED)
        for name in sorted(files):
            if name == ".git" or name in REPORTS or name.endswith((".pyc", ".pyo")):
                continue
            path = current / name
            result[path.relative_to(root).as_posix()] = _fingerprint(path)
    if plan is not None:
        for item in mappings(plan):
            name = text(item, "source" if destination else "target")
            path = confined(root, name)
            if path.exists():
                result[name] = _fingerprint(path)
    return result


def _fingerprint(path: Path) -> Record:
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise WorkflowError("inventory requires independent regular files")
    return {"sha256": digest(path.read_bytes()), "mode": stat.S_IMODE(metadata.st_mode)}


def _raise_scan_error(error: OSError) -> None:
    raise error


def mappings(plan: Record) -> list[Record]:
    """Validate nonoverlapping per-file mappings with explicit product roles."""
    value = plan.get("mapping")
    if not isinstance(value, list) or not value:
        raise WorkflowError("complete product mapping required")
    result: list[Record] = []
    sources: set[str] = set()
    targets: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise WorkflowError("mapping entry must be an object")
        source, target, role = (text(item, key) for key in ("source", "target", "role"))
        if source in sources or target in targets or role not in {"source", "test", "context"}:
            raise WorkflowError("duplicate mapping or invalid role")
        sources.add(source)
        targets.add(target)
        result.append(item)
    if not {"source", "test"}.issubset({text(item, "role") for item in result}):
        raise WorkflowError("product source and maintained tests required")
    return result


def copy_inventory(source: Path, destination: Path, files: Record) -> None:
    """Copy an already inventoried tree without copying its Git/environment state."""
    for name in files:
        target = confined(destination, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copy2(confined(source, name), target)


def copy_mapping(plan: Record, source: Path, destination: Path) -> None:
    """Place explicit product files below the generated workbench's product folder."""
    for item in mappings(plan):
        target_name = text(item, "target")
        if not target_name.startswith("product/"):
            raise WorkflowError("workbench mappings must stay below product/")
        target = confined(destination, target_name)
        original = confined(source, text(item, "source"))
        if item.get("new") is True:
            if original.exists():
                raise WorkflowError("new mapping would overwrite an existing source file")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = shutil.copy2(original, target)


def names(plan: Record, role: str, *, destination: bool = False) -> list[str]:
    """Select measured source or test paths from the declared mapping."""
    return [
        text(item, "source" if destination else "target")
        for item in mappings(plan)
        if item["role"] == role
    ]


def string_list(record: Record, key: str) -> list[str]:
    """Validate a nonempty list of strings."""
    value: Value = record.get(key)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise WorkflowError(f"nonempty string list required: {key}")
    return [str(item) for item in value]
