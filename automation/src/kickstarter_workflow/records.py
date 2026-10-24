"""Private durable records and confined file inventories."""

import fcntl
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import TypeAlias, cast

Value: TypeAlias = str | int | float | bool | list["Value"] | dict[str, "Value"] | None
Record: TypeAlias = dict[str, Value]


class WorkflowError(Exception):
    """A precondition failed; preserve work for an explicit decision."""


def text(record: Record, key: str) -> str:
    """Read a required nonempty string without coercion."""
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise WorkflowError(f"missing or invalid {key}")
    return value


def object_value(record: Record, key: str) -> Record:
    """Read a required JSON object."""
    value = record.get(key)
    if not isinstance(value, dict):
        raise WorkflowError(f"missing or invalid {key}")
    return value


def identifier(record: Record, key: str) -> str:
    """Validate stable identifiers without silently normalizing them."""
    value = text(record, key)
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value):
        raise WorkflowError(f"invalid {key} identifier")
    return value


def no_links(path: Path) -> Path:
    """Reject symlink traversal, including any existing ancestor."""
    if not path.is_absolute() or ".." in path.parts:
        raise WorkflowError("absolute confined paths required")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise WorkflowError("symlink traversal refused")
    return path


def private_directory(path: Path) -> None:
    """Create or validate a user-owned, non-shared state directory."""
    _ = no_links(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = path.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise WorkflowError("state directory must be owned by this user with mode 0700")


def digest(data: bytes) -> str:
    """Fingerprint content using SHA-256."""
    return hashlib.sha256(data).hexdigest()


def encoded(record: Record) -> bytes:
    """Encode deterministic records suitable for content binding."""
    return (json.dumps(record, sort_keys=True, indent=2) + "\n").encode()


def load(path: Path) -> Record:
    """Read an object record without accepting links or malformed data."""
    _ = no_links(path)
    value = cast("Value", json.loads(path.read_bytes()))
    if not isinstance(value, dict):
        raise WorkflowError("record must be an object")
    return value


def sync_directory(path: Path) -> None:
    """Persist directory entries on supported POSIX filesystems."""
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def save(path: Path, record: Record) -> None:
    """Atomically publish a private record and sync its immediate parent."""
    _ = no_links(path)
    temporary = path.with_suffix(".pending")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        _ = stream.write(encoded(record))
        stream.flush()
        os.fsync(stream.fileno())
    _ = temporary.replace(path)
    sync_directory(path.parent)


def project_record(project: Path, record: Record | None = None) -> None:
    """Serialize only shared metadata, preserving interrupted writes for recovery."""
    path = no_links(project / "project.lock")
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w"):
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        if (project / "project.pending").exists():
            raise WorkflowError("pending project write requires explicit recovery; work preserved")
        if record is not None:
            save(project / "project.json", record)
