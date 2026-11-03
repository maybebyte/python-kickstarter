"""Public workflow regressions for confirmed review findings."""

from pathlib import Path

import pytest

from kickstarter_workflow.files import mappings
from kickstarter_workflow.process import Runner
from kickstarter_workflow.records import Record, object_value, text
from kickstarter_workflow.workflow import Workflow


@pytest.mark.parametrize(
    "directory",
    [
        "ordinary tests",
        "$(touch sr01-shell-marker)",
        "`touch sr01-backtick-marker`",
        "literal 'quote' $x ; &",
    ],
)
def test_mapped_test_paths_remain_literal(tmp_path: Path, plan: Record, directory: str) -> None:
    target = f"product/{directory}/test_app.py"
    mappings(plan)[1]["target"] = target
    prepared = Workflow(tmp_path / "state").dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    runner = Runner(object_value(plan, "tools"), tmp_path / "gate", tmp_path / "cache")
    runner.env["PYTHONPATH"] = str(workspace / "product")
    junit = tmp_path / "tests.xml"
    runner.env["PYTEST_ADDOPTS"] = "--junitxml=" + str(junit)
    _ = runner.run(["just", "test"], workspace, allow_failure=True)
    assert not (workspace / "sr01-shell-marker").exists()
    assert not (workspace / "sr01-backtick-marker").exists()
    assert runner.last_exit == 0, runner.last_output.read_text()
    assert 'name="test_twice"' in junit.read_text()
    assert (workspace / target).read_bytes() == (
        Path(text(plan, "source")) / "test_app.py"
    ).read_bytes()


@pytest.mark.parametrize("directory", ["{{ 'literal' }}", "[", "]", "*", "?", "{a,b}", "a::b"])
def test_recipe_and_selector_syntax_is_refused_before_generation(
    tmp_path: Path, plan: Record, directory: str
) -> None:
    mappings(plan)[1]["target"] = f"product/{directory}/test_app.py"
    result = Workflow(tmp_path / "state").dispatch("prepare", plan)
    assert result["status"] == "blocked", result
    assert not (tmp_path / "state/sample/one/workspace").exists()
    assert not list((tmp_path / "state/sample/one").glob("run-*/*.log"))


@pytest.mark.parametrize("new", [False, True])
def test_preparation_never_supplies_mapped_initializer_bytes(
    tmp_path: Path, plan: Record, *, new: bool
) -> None:
    source = Path(text(plan, "source"))
    payload = (source / "app.py").read_bytes()
    plan["mapping"] = [
        {
            "source": "new_app.py" if new else "app.py",
            "target": "product/__init__.py",
            "role": "source",
            "new": new,
        },
        {
            "source": "new_test.py" if new else "test_app.py",
            "target": "product/test_app.py",
            "role": "test",
            "new": new,
        },
    ]
    workflow = Workflow(tmp_path / "state")
    prepared = workflow.dispatch("prepare", plan)
    assert prepared["status"] == "prepared", prepared
    workspace = Path(text(prepared, "workspace"))
    if new:
        assert not (workspace / "product/__init__.py").exists()
        assert not (workspace / "product/test_app.py").exists()
        assert workflow.dispatch("verify", plan)["status"] == "blocked"
        _ = (workspace / "product/__init__.py").write_bytes(payload)
        _ = (workspace / "product/test_app.py").write_bytes((source / "test_app.py").read_bytes())
    assert (workspace / "product/__init__.py").read_bytes() == payload
    assert (source / "app.py").read_bytes() == payload
    assert workflow.dispatch("resume", plan)["status"] == ("blocked" if new else "prepared")
