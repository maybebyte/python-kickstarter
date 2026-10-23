"""Keep the helper's generated gates on the maintainer delivery path."""

import re
from pathlib import Path
from typing import cast

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent


def test_automation_gate_is_required_locally_and_in_ci() -> None:
    justfile = (ROOT / "justfile").read_text()
    ci = re.search(r"^ci: (.+)$", justfile, re.MULTILINE)
    assert ci is not None
    assert "automation-ci" in ci.group(1).split()
    recipe = re.search(r"^automation-ci:\n((?:    .+\n)+)", justfile, re.MULTILINE)
    assert recipe is not None
    assert "uv sync --locked --project automation" in recipe.group(1)
    assert "just --justfile automation/justfile ci" in recipe.group(1)
    workflow = cast(
        "dict[str, object]",
        yaml.safe_load((ROOT / ".github" / "workflows" / "test-template.yml").read_text()),
    )
    jobs = cast("dict[str, object]", workflow["jobs"])
    assert "automation" in jobs
    job = cast("dict[str, object]", jobs["automation"])
    assert "continue-on-error" not in job
    steps = cast("list[dict[str, object]]", job["steps"])
    assert any(
        step.get("run") == "just automation-ci"
        and step.get("env") == {"TMPDIR": "${{ runner.temp }}", "HYPOTHESIS_PROFILE": "ci"}
        for step in steps
    )
