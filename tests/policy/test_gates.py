"""Config-literal pins: gates cannot be silently weakened. Stdlib only."""

import re
import tomllib
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parent.parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_type_checking_is_recommended() -> None:
    assert PYPROJECT["tool"]["basedpyright"]["typeCheckingMode"] == "recommended"


def test_type_checking_fails_on_warnings() -> None:
    assert PYPROJECT["tool"]["basedpyright"]["failOnWarnings"] is True


def test_ruff_select_present() -> None:
    select = cast("list[str]", PYPROJECT["tool"]["ruff"]["lint"]["select"])
    assert "ALL" in select


def test_agents_md_recipes_exist_in_justfile() -> None:
    """docs-can't-lie: the first `just <recipe>` per fenced invocation is a real recipe."""
    justfile = (ROOT / "justfile").read_text()
    recipes = set(re.findall(r"^([a-z][a-z-]*):", justfile, re.MULTILINE))
    agents = (ROOT / "AGENTS.md").read_text()
    blocks = cast("list[str]", re.findall(r"```.*?```", agents, re.DOTALL))
    referenced: set[str] = set()
    for block in blocks:
        referenced |= set(re.findall(r"just ([a-z][a-z-]*)", block))
    assert referenced <= recipes, f"AGENTS.md names missing recipes: {referenced - recipes}"


def test_gitleaks_pin_matches_template() -> None:
    """The one Renovate-managed literal AGENTS.md requires hand-synced to the template.

    Renovate bumps only the maintainer's mise.toml; it cannot see the template's
    .jinja copy or the AGENTS.md prose, so a bump PR stays red until both follow.
    """
    pin = re.compile(r'^gitleaks = "(\d+\.\d+\.\d+)"$', re.MULTILINE)
    ours = pin.search((ROOT / "mise.toml").read_text())
    theirs = pin.search((ROOT / "template" / "mise.toml.jinja").read_text())
    assert ours is not None
    assert theirs is not None
    assert ours.group(1) == theirs.group(1)
    assert f"gitleaks (`{ours.group(1)}`)" in (ROOT / "AGENTS.md").read_text()


def test_actions_are_sha_pinned() -> None:
    """Every third-party `uses:` is a 40-char SHA + a v-prefixed version comment."""
    # SHA + a version comment (v<major>[.minor[.patch]]); our pins carry the action's
    # exact tag. The maintainer re-verifies the comment matches the SHA at bump time
    # via `gh api .../tags`.
    pattern = re.compile(r"uses:\s*\S+@([0-9a-f]{40})\s+#\s*v\d+(\.\d+){0,2}\b")
    for wf in (ROOT / ".github" / "workflows").glob("*.yml"):
        for line in wf.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith(("- uses:", "uses:")):
                assert pattern.search(stripped), f"unpinned action in {wf.name}: {stripped}"
