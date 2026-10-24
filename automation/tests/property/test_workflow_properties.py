"""Generated public-interface safety invariants, with isolated example state."""

import os
import tempfile
from pathlib import Path

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from kickstarter_workflow.records import Record, load, save, text
from kickstarter_workflow.workflow import Workflow
from tests.unit.test_mapped_assets import ASSETS, asset_plan

pytestmark = pytest.mark.property


@given(
    st.lists(
        st.sampled_from(["prepare", "resume", "status", "verify", "return", "cleanup"]),
        min_size=1,
        max_size=15,
    )
)
def test_disposable_lifecycle_never_grants_production_evidence(operations: list[str]) -> None:
    with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
        workflow = Workflow(Path(directory) / "state")
        request: Record = {
            "project": "example",
            "task": "one",
            "mode": "disposable",
            "reason": "temporary diagnostic",
        }
        status = "absent"
        for operation in operations:
            result = workflow.dispatch(operation, request)
            if operation == "prepare" and status == "absent":
                status = "exempt"
            elif operation == "cleanup" and status != "absent":
                status = "cleaned"
            expected = (
                "blocked" if status == "absent" or operation in {"verify", "return"} else status
            )
            assert result["status"] == expected, (operations, operation, result)
            assert "receipt" not in result
            assert "workspace" not in result


def test_generated_unsafe_paths_cannot_escape_the_task(plan: Record) -> None:
    @given(
        st.sampled_from(["../", "product/../../../", "product//", "product/./"]),
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=12),
    )
    @example(prefix="product//", name="app")
    def check(prefix: str, name: str) -> None:
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as directory:
            root = Path(directory)
            workflow = Workflow(root / "state")
            target = prefix + name + ".py"
            request: Record = {
                **plan,
                "mapping": [
                    {"source": "app.py", "target": target, "role": "source"},
                    {"source": "test_app.py", "target": "product/test_app.py", "role": "test"},
                ],
            }
            result = workflow.dispatch("prepare", request)
            assert result["status"] == "blocked", result
            assert "receipt" not in result
            assert not (root / (name + ".py")).exists()
            assert not (root / "state/sample/one/workspace").exists()

    check()


def test_arbitrary_candidate_config_test_and_mode_changes_invalidate_receipts(
    tmp_path: Path, plan: Record
) -> None:
    plan = asset_plan(plan)
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    accepted = workflow.dispatch("verify", plan)
    assert accepted["status"] == "verified", accepted
    workspace = Path(text(prepared, "workspace"))

    @given(
        name=st.sampled_from(
            [
                "product/app.py",
                "product/test_app.py",
                "pyproject.toml",
                "uv.lock",
                "justfile",
                *("product/" + name for name in ASSETS),
            ]
        ),
        suffix=st.binary(min_size=1, max_size=64),
        mode_change=st.booleans(),
    )
    @example(name="product/fixtures/coverage.json", suffix=b"changed", mode_change=False)
    def check(name: str, suffix: bytes, *, mode_change: bool) -> None:
        path = workspace / name
        original, mode = path.read_bytes(), path.stat().st_mode & 0o777
        try:
            if mode_change:
                path.chmod(mode ^ 0o100)
            else:
                _ = path.write_bytes(original + suffix)
            rejected = workflow.dispatch("status", plan)
            assert rejected["status"] == "blocked", rejected
        finally:
            _ = path.write_bytes(original)
            path.chmod(mode)
        restored = workflow.dispatch("resume", plan)
        assert restored["status"] == "verified", restored
        assert restored["receipt"] == accepted["receipt"]

    check()


def test_prepared_inventory_and_baseline_corruption_never_resumes(
    tmp_path: Path, plan: Record
) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    task = Path(text(prepared, "workspace")).parent

    @given(
        name=st.sampled_from(["source.json", "scaffold.json", "baseline/app.py"]),
        suffix=st.binary(min_size=1, max_size=64),
        change_mode=st.booleans(),
    )
    def check(name: str, suffix: bytes, *, change_mode: bool) -> None:
        path = task / name
        original, mode = path.read_bytes(), path.stat().st_mode & 0o777
        try:
            if change_mode:
                path.chmod(mode ^ 0o100)
            else:
                _ = path.write_bytes(original + suffix)
            for operation in ("resume", "prepare"):
                result = workflow.dispatch(operation, plan)
                assert result["status"] == "blocked", (name, result)
        finally:
            _ = path.write_bytes(original)
            path.chmod(mode)
        assert workflow.dispatch("resume", plan)["status"] == "prepared"

    check()


def test_receipt_metadata_changes_invalidate_public_status(tmp_path: Path, plan: Record) -> None:
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    accepted = workflow.dispatch("verify", plan)
    assert accepted["status"] == "verified", accepted
    token = text(accepted, "receipt")
    receipt = tmp_path / "state/sample/one/receipts" / (token + ".json")
    original = receipt.read_bytes()

    @given(
        field=st.sampled_from(["product_tests", "product_coverage", "annotation"]),
        replacement=st.text(min_size=1, max_size=32),
    )
    @example(field="product_tests", replacement="0")
    def check(field: str, replacement: str) -> None:
        changed = load(receipt)
        assert changed.get(field) != replacement
        changed[field] = replacement
        try:
            save(receipt, changed)
            assert load(receipt)[field] == replacement
            result = workflow.dispatch("status", plan)
            assert result["status"] == "blocked", result
            assert "receipt" in text(result, "reason")
        finally:
            _ = receipt.write_bytes(original)
        restored = workflow.dispatch("resume", plan)
        assert restored["status"] == "verified", restored
        assert restored["receipt"] == token

    check()
