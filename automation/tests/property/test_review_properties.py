"""Generated path transport through public preparation and the real generated gate."""

import uuid
from pathlib import Path

import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st

from kickstarter_workflow.process import Runner
from kickstarter_workflow.records import Record, object_value, text
from kickstarter_workflow.workflow import Workflow

pytestmark = pytest.mark.property


def test_generated_mapped_paths_arrive_as_one_literal_test_target(
    tmp_path: Path, plan: Record
) -> None:
    workflow = Workflow(tmp_path / "state")

    @given(st.text(alphabet="abc XYZ09é'\"$;&()", min_size=1, max_size=20))
    @example("ordinary tests")
    @example("$(printf literal)")
    @example("`printf literal`")
    def check(suffix: str) -> None:
        task = "case-" + uuid.uuid4().hex
        target = "product/case-" + suffix + "/test_app.py"
        request: Record = {
            **plan,
            "task": task,
            "mapping": [
                {"source": "app.py", "target": "product/app.py", "role": "source"},
                {"source": "test_app.py", "target": target, "role": "test"},
            ],
        }
        prepared = workflow.dispatch("prepare", request)
        assert prepared["status"] == "prepared", prepared
        workspace = Path(text(prepared, "workspace"))
        runner = Runner(object_value(plan, "tools"), tmp_path / task, tmp_path / "cache")
        runner.env["PYTHONPATH"] = str(workspace / "product")
        junit = tmp_path / (task + ".xml")
        runner.env["PYTEST_ADDOPTS"] = "--junitxml=" + str(junit)
        _ = runner.run(["just", "test"], workspace, allow_failure=True)
        assert runner.last_exit == 0, runner.last_output.read_text()
        assert 'name="test_twice"' in junit.read_text()
        assert (workspace / target).read_bytes() == (
            Path(text(plan, "source")) / "test_app.py"
        ).read_bytes()
        for character in set(suffix):
            event(f"observed character {character!r}")

    check()


def test_generated_selector_syntax_never_reaches_tools(tmp_path: Path, plan: Record) -> None:
    @given(
        body=st.text(alphabet="abcXYZ09 '$(){}", max_size=20),
        selector=st.sampled_from(["{{ 'literal' }}", "[", "]", "*", "?", "{a,b}", "::"]),
    )
    @example(body="", selector="[")
    @example(body="", selector="{{ 'literal' }}")
    def check(body: str, selector: str) -> None:
        task = "case-" + uuid.uuid4().hex
        request: Record = {
            **plan,
            "task": task,
            "mapping": [
                {"source": "app.py", "target": "product/app.py", "role": "source"},
                {
                    "source": "test_app.py",
                    "target": "product/case-" + selector + body + "/test_app.py",
                    "role": "test",
                },
            ],
        }
        result = Workflow(tmp_path / "state").dispatch("prepare", request)
        assert result["status"] == "blocked", result
        directory = tmp_path / "state/sample" / task
        assert not (directory / "workspace").exists()
        assert not list(directory.glob("run-*/*.log"))
        event("refused selector " + selector)

    check()
