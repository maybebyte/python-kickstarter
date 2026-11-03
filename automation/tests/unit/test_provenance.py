"""Literal regressions for cache trust and repository confinement."""

from pathlib import Path

from kickstarter_workflow.records import Record, object_value, text
from kickstarter_workflow.workflow import Workflow
from tests.conftest import command


def test_moving_or_dirty_template_cache_never_provides_readiness(
    tmp_path: Path, plan: Record, template_cache: Path
) -> None:
    cache = tmp_path / "cache"
    command(
        "git", "clone", "--quiet", "--no-hardlinks", str(template_cache), str(cache), cwd=tmp_path
    )
    command(
        "git",
        "remote",
        "set-url",
        "origin",
        text(object_value(plan, "template"), "source"),
        cwd=cache,
    )
    command("git", "checkout", "--quiet", "-b", "moving", cwd=cache)
    changed: Record = {**plan, "template": {**object_value(plan, "template"), "cache": str(cache)}}
    result = Workflow(tmp_path / "state").dispatch("prepare", changed)
    assert result["status"] == "blocked", result
    assert "moving" in text(result, "reason")
    command("git", "checkout", "--quiet", "--detach", cwd=cache)
    _ = (cache / "unreviewed.txt").write_text("Unreviewed template content.\n")
    result = Workflow(tmp_path / "other-state").dispatch("prepare", changed)
    assert result["status"] == "blocked", result
    assert "dirty" in text(result, "reason")
