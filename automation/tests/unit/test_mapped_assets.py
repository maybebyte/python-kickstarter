"""Declared fixture bytes remain part of verification and reviewed return."""

from pathlib import Path

import pytest

from kickstarter_workflow.records import Record, text
from kickstarter_workflow.workflow import Workflow
from tests.unit.test_transfer import review

ASSETS = (
    "fixtures/coverage.json",
    "fixtures/coverage.xml",
    "fixtures/.coverage",
    "fixtures/requirements-audit.txt",
    "fixtures/__pycache__/example.pyc",
)


def asset_plan(plan: Record) -> Record:
    source = Path(text(plan, "source"))
    mapping = plan["mapping"]
    assert isinstance(mapping, list)
    for name in ASSETS:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_bytes(b"original fixture\n")
    return {
        **plan,
        "mapping": [
            *mapping,
            *({"source": name, "target": "product/" + name, "role": "context"} for name in ASSETS),
        ],
    }


def test_declared_assets_require_allowlisting_and_are_actually_returned(
    tmp_path: Path, plan: Record
) -> None:
    request = asset_plan(plan)
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", request)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    source = Path(text(plan, "source"))
    for name in ASSETS:
        asset = workspace / "product" / name
        assert asset.read_bytes() == b"original fixture\n"
        _ = asset.write_bytes(b"reviewed fixture\n")
        asset.chmod(0o640)
    verified = workflow.dispatch("verify", request)
    assert verified["status"] == "verified", verified
    receipt = text(verified, "receipt")
    omitted = workflow.dispatch("return", review(receipt, "app.py"))
    assert omitted["status"] == "blocked", omitted
    assert not (workspace.parent / "return.json").exists()
    assert workflow.dispatch("status", request)["receipt"] == receipt
    for name in ASSETS:
        assert (source / name).read_bytes() == b"original fixture\n"
    returned = workflow.dispatch("return", review(receipt, *ASSETS))
    assert returned["status"] == "returned", returned
    assert returned["destination_validated"] is True
    applied = returned["applied"]
    assert isinstance(applied, list)
    assert {str(item) for item in applied} == set(ASSETS)
    for name in ASSETS:
        assert (source / name).read_bytes() == b"reviewed fixture\n"
        assert (source / name).stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize("fault", ["git", "venv", "outside", "symlink", "hardlink"])
def test_declared_assets_do_not_bypass_filesystem_safety(
    tmp_path: Path, plan: Record, fault: str
) -> None:
    source = Path(text(plan, "source"))
    payload = tmp_path / "outside.txt"
    _ = payload.write_bytes(b"untouched outside payload\n")
    name = {
        "git": ".git/fixture.json",
        "venv": ".venv/fixture.json",
        "outside": "../outside.txt",
        "symlink": "fixtures/coverage.json",
        "hardlink": "fixtures/coverage.json",
    }[fault]
    if fault in {"symlink", "hardlink"}:
        asset = source / name
        asset.parent.mkdir(parents=True)
        if fault == "symlink":
            asset.symlink_to(payload)
        else:
            asset.hardlink_to(payload)
    mapping = plan["mapping"]
    assert isinstance(mapping, list)
    request: Record = {
        **plan,
        "mapping": [
            *mapping,
            {"source": name, "target": "product/fixture.json", "role": "context"},
        ],
    }
    result = Workflow(tmp_path / "state").dispatch("prepare", request)
    assert result["status"] == "blocked", result
    assert not (tmp_path / "state/sample/one/workspace").exists()
    assert payload.read_bytes() == b"untouched outside payload\n"
