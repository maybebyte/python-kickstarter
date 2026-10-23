"""Destination checks cannot certify a different payload or stale evidence."""

from pathlib import Path

import pytest

from kickstarter_workflow.records import Record, load, text
from kickstarter_workflow.workflow import Workflow
from tests.unit.test_transfer import review


@pytest.mark.parametrize("changed", ["app.py", "README.md", "workspace", "evidence"])
def test_destination_checks_must_preserve_reviewed_inputs(
    tmp_path: Path, plan: Record, changed: str
) -> None:
    source = Path(text(plan, "source"))
    task = tmp_path / "state/sample/one"
    workspace = task / "workspace"
    if changed == "workspace":
        target = repr(str(workspace / "product/app.py"))
    elif changed == "evidence":
        target = (
            f"Path({str(task)!r}) / next(name for name in "
            f"json.loads((Path({str(task)!r}) / 'receipts' / "
            f"(json.loads((Path({str(task)!r}) / 'task.json').read_text())['receipt'] + '.json'))"
            ".read_text())['artifacts'] if name.endswith('.log'))"
        )
    else:
        target = repr(str(source / changed))
    mutation = (
        "from pathlib import Path\nimport json\n"
        f"if Path.cwd() == Path({str(source)!r}):\n"
        f"    p = Path({target})\n"
        "    p.write_bytes(p.read_bytes() + b'\\n# normalized\\n')\n"
    )
    checks = plan["repository_checks"]
    assert isinstance(checks, list)
    checks.append(["uv", "run", "--project", "{workspace}", "python", "-c", mutation])
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    app = workspace / "product/app.py"
    _ = app.write_text(app.read_text().replace("value * 2", "value + value"))
    verified = workflow.dispatch("verify", plan)
    assert verified["status"] == "verified", verified
    result = workflow.dispatch("return", review(text(verified, "receipt"), "app.py"))
    assert result["status"] == "blocked", result
    assert result["destination_validated"] is False
    assert result["transferred"] == ["app.py"]
    assert result["applied"] == ([] if changed == "app.py" else ["app.py"])
    journal = load(task / "return.json")
    assert journal["status"] == "blocked"
    assert "value + value" in (source / "app.py").read_text()
    if changed in {"app.py", "README.md"}:
        assert result["destination_changes"] == [changed]
        assert "normalized" in (source / changed).read_text()


@pytest.mark.parametrize(("field", "replacement"), [("status", "failed"), ("product_tests", 0)])
def test_destination_checks_cannot_modify_the_verification_receipt(
    tmp_path: Path, plan: Record, field: str, replacement: str | int
) -> None:
    source = Path(text(plan, "source"))
    task = tmp_path / "state/sample/one"
    mutation = (
        "from pathlib import Path\nimport json\n"
        f"if Path.cwd() == Path({str(source)!r}):\n"
        f"    task = Path({str(task)!r})\n"
        "    token = json.loads((task / 'task.json').read_text())['receipt']\n"
        "    path = task / 'receipts' / (token + '.json')\n"
        "    receipt = json.loads(path.read_text())\n"
        f"    receipt[{field!r}] = {replacement!r}\n"
        "    path.write_text(json.dumps(receipt))\n"
    )
    checks = plan["repository_checks"]
    assert isinstance(checks, list)
    checks.append(["uv", "run", "--project", "{workspace}", "python", "-c", mutation])
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    app = Path(text(prepared, "workspace")) / "product/app.py"
    _ = app.write_text(app.read_text().replace("value * 2", "value + value"))
    verified = workflow.dispatch("verify", plan)
    assert verified["status"] == "verified", verified
    token = text(verified, "receipt")
    assert load(task / "receipts" / (token + ".json"))["status"] == "passed"
    result = workflow.dispatch("return", review(token, "app.py"))
    assert load(task / "receipts" / (token + ".json"))[field] == replacement
    assert result["status"] == "blocked", result
    assert result["destination_validated"] is False
    assert "receipt" in text(result, "reason")
    assert result["transferred"] == ["app.py"]
    assert result["applied"] == ["app.py"]
    assert load(task / "return.json")["status"] == "blocked"
