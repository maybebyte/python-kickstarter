"""Textual merge success does not establish compatibility of intent."""

from pathlib import Path

from kickstarter_workflow.records import Record, text
from kickstarter_workflow.workflow import Workflow
from tests.unit.test_transfer import review


def test_clean_text_merge_cannot_approve_discarded_behavior(tmp_path: Path, plan: Record) -> None:
    source = Path(text(plan, "source"))
    original = '"""Product with a policy multiplier."""\n\nFACTOR = 2\nLABEL = "calculation"\nUNIT = "items"\nVERSION = "1"\n\n\ndef twice(value: int) -> int:\n    """Apply the multiplier."""\n    return value * FACTOR\n'
    _ = (source / "app.py").write_text(original)
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    _ = (workspace / "product/app.py").write_text(
        original.replace("value * FACTOR", "value + value")
    )
    verified = workflow.dispatch("verify", plan)
    assert verified["status"] == "verified", verified
    newer = original.replace("FACTOR = 2", "FACTOR = 3")
    _ = (source / "app.py").write_text(newer)
    result = workflow.dispatch("return", review(text(verified, "receipt"), "app.py"))
    assert result["status"] == "review_required", result
    assert result["receipt"] != verified["receipt"]
    assert (source / "app.py").read_text() == newer
    assert "FACTOR = 3" in (workspace / "product/app.py").read_text()
    assert "return value + value" in (workspace / "product/app.py").read_text()
    assert not (workspace.parent / "return.json").exists()
